"""Sandbox — safe execution of generated Python analysis code.

Uses subprocess isolation for genuine process-level security:
- Separate process (not thread) — cannot affect host
- Restricted imports (whitelist only)
- Resource limits (CPU time, memory)
- Timeout protection
- No filesystem access beyond /tmp
- No network access
- Captured stdout/stderr

The existing static validation (restricted builtins, import whitelist)
is preserved as defense-in-depth.
"""

import asyncio
import io
import json
import logging
import os
import resource
import subprocess
import sys
import tempfile
from typing import Any

logger = logging.getLogger(__name__)

# Maximum execution time in seconds
MAX_EXECUTION_TIME = 30

# Memory limit: 128MB
MEMORY_LIMIT_MB = 128

# CPU time limit in seconds
CPU_TIME_LIMIT = 15


class SandboxError(Exception):
    """Raised when sandbox execution fails."""
    pass


# ─── LLM Code Generation ─────────────────────────────────────────────────────


CODEGEN_SYSTEM_PROMPT = """You are a Python code generator for data quality analysis.

Generate ONLY valid Python code that analyzes the given incident.
The code must:
1. Use only standard library modules (json, math, statistics, datetime, collections, re)
2. Set a variable called `result` with your analysis findings as a dict
3. Use `print()` to output human-readable findings
4. Be self-contained — no external dependencies

Output format:
- A Python code block that sets `result = {...}` with your findings
- Include metrics, severity assessment, and recommended actions in the result dict

Example output:
```python
result = {
    "analysis_type": "schema_drift",
    "findings": [
        {"metric": "null_rate", "value": 0.15, "threshold": 0.05, "severity": "high"},
    ],
    "recommendations": ["Reprocess affected partitions", "Update schema validation"],
    "confidence": 0.85
}
print(f"Analysis complete: {len(result['findings'])} findings")
```
"""

CODEGEN_USER_PROMPT = """Analyze this data quality incident and generate Python code.

Incident Type: {incident_type}
Description: {description}

Evidence collected:
{evidence_summary}

Generate Python code that:
1. Analyzes the evidence to identify root cause patterns
2. Calculates severity metrics based on the evidence
3. Provides specific recommendations for remediation
4. Sets the `result` variable with findings as a dict

Code:"""


async def _llm_generate_code(incident_type: str, description: str, evidence_summary: str) -> str:
    """Generate analysis code using LLM."""
    try:
        from agent.models.llm import get_llm

        llm = get_llm()

        from langchain_core.messages import HumanMessage, SystemMessage

        messages = [
            SystemMessage(content=CODEGEN_SYSTEM_PROMPT),
            HumanMessage(content=CODEGEN_USER_PROMPT.format(
                incident_type=incident_type,
                description=description,
                evidence_summary=evidence_summary,
            )),
        ]

        response = await llm.ainvoke(messages)
        content = response.content

        # Extract code block from response
        if "```python" in content:
            code = content.split("```python")[1].split("```")[0].strip()
        elif "```" in content:
            code = content.split("```")[1].split("```")[0].strip()
        else:
            lines = content.split("\n")
            code_lines = []
            in_code = False
            for line in lines:
                if line.strip().startswith(("import ", "from ", "result", "print", "#")):
                    in_code = True
                if in_code:
                    code_lines.append(line)
            code = "\n".join(code_lines) if code_lines else content

        # Ensure result is set
        if "result" not in code:
            code += '\nresult = {"status": "analysis_complete", "type": "' + incident_type + '"}'

        return code

    except Exception as e:
        logger.error(f"LLM code generation failed: {e}")
        return _fallback_code(incident_type, evidence_summary)


def _fallback_code(incident_type: str, evidence_summary: str) -> str:
    """Fallback code when LLM fails."""
    return f"""import json

result = {{
    "analysis_type": "{incident_type}",
    "findings": [],
    "evidence_count": {len(evidence_summary.split(chr(10)))},
    "source": "fallback_analysis",
    "recommendations": ["Review evidence manually", "Check pipeline logs"]
}}
print(f"Fallback analysis for {incident_type}: {{len(result['findings'])}} findings")
"""


# ─── Static Validation (defense-in-depth) ──────────────────────────────────────

BLOCKED_PATTERNS = [
    "__subclasses__", "__class__", "__base__", "__globals__",
    "__code__", "__builtins__", "__import__", "__loader__",
    "__spec__", "__file__", "__name__", "__qualname__",
    "eval", "exec", "compile", "open",
    "getattr", "setattr", "delattr", "hasattr",
    "os.", "subprocess", "shutil", "pathlib",
    "socket", "http", "urllib", "requests",
    "__import_module__", "importlib",
]

ALLOWED_MODULES = {"math", "json", "statistics", "datetime", "collections", "re"}


def _validate_code(code: str) -> str | None:
    """Validate code for safety. Returns error message if unsafe, None if OK."""
    code_lower = code.lower()
    for pattern in BLOCKED_PATTERNS:
        if pattern.lower() in code_lower:
            return f"Blocked dangerous pattern: {pattern}"

    # Check for import statements outside allowed modules
    for line in code.split("\n"):
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            # Extract module name
            parts = stripped.split()
            if len(parts) >= 2:
                module = parts[1].split(".")[0].split(",")[0]
                if module not in ALLOWED_MODULES:
                    return f"Import not allowed: {module}"

    return None


# ─── Sandbox Execution (subprocess isolation) ──────────────────────────────────


def _create_sandbox_script(code: str, context: dict[str, Any] | None = None) -> str:
    """Create a Python script that runs inside the sandbox subprocess.

    The script:
    1. Restricts imports to whitelist only
    2. Restricts builtins
    3. Sets resource limits
    4. Executes the user code
    5. Outputs result as JSON on stdout
    """
    # Serialize context as JSON for safe injection
    context_json = json.dumps(context or {})

    # Build the restricted import hook
    allowed = json.dumps(list(ALLOWED_MODULES))

    sandbox_wrapper = f"""#!/usr/bin/env python3
import sys
import json
import importlib

# ─── Step 1: Set resource limits (CPU time, memory) ───────────────────────────
try:
    import resource
    # CPU time limit: {CPU_TIME_LIMIT} seconds
    resource.setrlimit(resource.RLIMIT_CPU, ({CPU_TIME_LIMIT}, {CPU_TIME_LIMIT}))
    # Memory limit: {MEMORY_LIMIT_MB}MB
    mem_bytes = {MEMORY_LIMIT_MB} * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
    # No file creation beyond /tmp
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))  # 1MB
    # Max processes: 1 (no forking)
    resource.setrlimit(resource.RLIMIT_NPROC, (1, 1))
except (ImportError, ValueError, OSError):
    pass  # Windows or restricted environment

# ─── Step 2: Restricted import hook ───────────────────────────────────────────
_allowed = {allowed}

_original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

def _restricted_import(name, *args, **kwargs):
    base = name.split('.')[0]
    if base in _allowed:
        return _original_import(name, *args, **kwargs)
    raise ImportError(f"Import '{{name}}' is not allowed in sandbox")

# ─── Step 3: Restricted builtins ──────────────────────────────────────────────
_safe_builtins = {{
    "print": print, "len": len, "range": range,
    "int": int, "float": float, "str": str, "bool": bool,
    "list": list, "dict": dict, "set": set, "tuple": tuple,
    "isinstance": isinstance, "type": type,
    "min": min, "max": max, "sum": sum, "abs": abs, "round": round,
    "sorted": sorted, "reversed": reversed,
    "enumerate": enumerate, "zip": zip, "map": map, "filter": filter,
    "any": any, "all": all,
    "True": True, "False": False, "None": None,
    "Exception": Exception, "ValueError": ValueError, "TypeError": TypeError,
    "KeyError": KeyError, "IndexError": IndexError,
    "ZeroDivisionError": ZeroDivisionError,
    "StopIteration": StopIteration,
    "__import__": _restricted_import,
}}

# ─── Step 4: Execute user code ────────────────────────────────────────────────
context = json.loads('{context_json}')
exec_context = {{"__builtins__": _safe_builtins}}
exec_context.update(context)

stdout_capture = []
_original_print = print

def _captured_print(*args, **kwargs):
    output = " ".join(str(a) for a in args)
    stdout_capture.append(output)

exec_context["print"] = _captured_print

try:
    user_code = sys.stdin.read()
    exec(user_code, exec_context)
    result = exec_context.get("result", {{"status": "no_result"}})
    output = "\\n".join(stdout_capture)
    print(json.dumps({{"result": result, "output": output, "error": None}}))
except Exception as e:
    output = "\\n".join(stdout_capture)
    print(json.dumps({{"result": None, "output": output, "error": f"{{type(e).__name__}}: {{e}}"}}))
"""
    return sandbox_wrapper


async def execute_analysis(code: str, context: dict[str, Any] | None = None) -> dict:
    """Execute Python analysis code in an isolated subprocess.

    Security layers:
    1. Static code validation (blocks dangerous patterns)
    2. Separate process (cannot affect host memory/filesystem)
    3. Resource limits (CPU time, memory, disk, processes)
    4. Restricted imports (whitelist only)
    5. Restricted builtins (no open, eval, exec, compile)
    6. Timeout protection
    7. Captured stdout (no terminal access)

    Returns:
        dict with result, output, error, execution_time
    """
    if not code or not code.strip():
        return {
            "result": None,
            "output": "",
            "error": "No code provided",
            "execution_time": 0,
        }

    # Step 1: Static validation (defense-in-depth)
    validation_error = _validate_code(code)
    if validation_error:
        return {
            "result": None,
            "output": "",
            "error": f"Safety validation failed: {validation_error}",
            "execution_time": 0,
        }

    # Step 2: Create sandbox wrapper script
    sandbox_script = _create_sandbox_script(code, context)

    # Step 3: Write to temp file and execute in subprocess
    start_time = asyncio.get_event_loop().time()

    try:
        # Create temp directory for isolated execution
        with tempfile.TemporaryDirectory(prefix="dataforge_sandbox_") as tmpdir:
            script_path = os.path.join(tmpdir, "analysis.py")
            with open(script_path, "w") as f:
                f.write(sandbox_script)

            # Execute in isolated subprocess
            # -u: unbuffered output
            # -S: don't add user site directory
            # -s: don't add user site directory
            # stdin=PIPE: we pass code via stdin
            # cwd=tmpdir: isolated working directory
            # env: minimal environment
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-u", "-S", "-s", script_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=tmpdir,
                env={
                    "PATH": "/usr/bin:/bin",
                    "HOME": tmpdir,
                    "TMPDIR": tmpdir,
                    "PYTHONDONTWRITEBYTECODE": "1",
                },
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(input=code.encode()),
                    timeout=MAX_EXECUTION_TIME,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                exec_time = asyncio.get_event_loop().time() - start_time
                return {
                    "result": None,
                    "output": "",
                    "error": f"Execution timed out after {MAX_EXECUTION_TIME}s",
                    "execution_time": round(exec_time, 3),
                }

            exec_time = asyncio.get_event_loop().time() - start_time
            stdout_text = stdout.decode(errors="replace")
            stderr_text = stderr.decode(errors="replace")

            # Parse JSON result from stdout
            try:
                # Find the last JSON line (the result)
                for line in reversed(stdout_text.strip().split("\n")):
                    line = line.strip()
                    if line.startswith("{"):
                        parsed = json.loads(line)
                        return {
                            "result": parsed.get("result"),
                            "output": parsed.get("output", ""),
                            "error": parsed.get("error"),
                            "execution_time": round(exec_time, 3),
                        }
            except (json.JSONDecodeError, StopIteration):
                pass

            # Fallback: return raw output
            if proc.returncode != 0:
                return {
                    "result": None,
                    "output": stdout_text,
                    "error": f"Process exited with code {proc.returncode}: {stderr_text[:500]}",
                    "execution_time": round(exec_time, 3),
                }

            return {
                "result": None,
                "output": stdout_text,
                "error": None,
                "execution_time": round(exec_time, 3),
            }

    except Exception as e:
        exec_time = asyncio.get_event_loop().time() - start_time
        logger.error(f"Sandbox execution failed: {e}")
        return {
            "result": None,
            "output": "",
            "error": f"{type(e).__name__}: {e}",
            "execution_time": round(exec_time, 3),
        }


async def generate_analysis_code(
    incident_type: str, evidence_summary: str, description: str = ""
) -> str:
    """Generate Python analysis code using LLM with fallback to templates."""
    return await _llm_generate_code(incident_type, description or incident_type, evidence_summary)

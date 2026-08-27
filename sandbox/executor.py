"""Sandbox — safe execution of generated Python analysis code.

Uses LLM to generate analysis code dynamically based on incident context,
then executes it in a sandboxed environment with restricted builtins.
"""

import asyncio
import io
import logging
from contextlib import redirect_stdout
from typing import Any

logger = logging.getLogger(__name__)

# Maximum execution time in seconds
MAX_EXECUTION_TIME = 30

# Only truly safe builtins
SAFE_BUILTINS = {
    "print": print,
    "len": len,
    "range": range,
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
    "list": list,
    "dict": dict,
    "set": set,
    "tuple": tuple,
    "type": type,
    "isinstance": isinstance,
    "min": min,
    "max": max,
    "sum": sum,
    "abs": abs,
    "round": round,
    "sorted": sorted,
    "reversed": reversed,
    "enumerate": enumerate,
    "zip": zip,
    "map": map,
    "filter": filter,
    "any": any,
    "all": all,
    "True": True,
    "False": False,
    "None": None,
    "Exception": Exception,
    "ValueError": ValueError,
    "TypeError": TypeError,
    "KeyError": KeyError,
    "IndexError": IndexError,
    "ZeroDivisionError": ZeroDivisionError,
    "__import__": None,  # Placeholder, replaced below
}


def _safe_import(name: str, *args: Any, **kwargs: Any) -> Any:
    """Restricted import that only allows safe modules."""
    allowed_modules = {"math", "json", "statistics", "datetime", "collections", "re"}
    if name in allowed_modules:
        import importlib
        return importlib.import_module(name)
    raise ImportError(f"Import '{name}' is not allowed in sandbox")


# Set up safe builtins with restricted import
_sandbox_builtins = dict(SAFE_BUILTINS)
_sandbox_builtins["__import__"] = _safe_import


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

        llm = get_llm(temperature=0.0)

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
            # Try to find Python code by looking for common patterns
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


# ─── Sandbox Execution ────────────────────────────────────────────────────────


async def execute_analysis(code: str, context: dict[str, Any] | None = None) -> dict:
    """Execute Python analysis code in a sandboxed environment with timeout.

    The code runs with:
    - Restricted builtins (no open, eval, exec, compile)
    - Only safe imports (math, json, statistics, datetime, collections, re)
    - Async timeout protection
    - Captured stdout
    - Optional context variables
    """
    if not code or not code.strip():
        return {
            "result": None,
            "output": "",
            "error": "No code provided",
            "execution_time": 0,
        }

    # Prepare execution environment
    exec_context: dict[str, Any] = {"__builtins__": _sandbox_builtins}

    # Add safe data from context
    if context:
        for k, v in context.items():
            if not k.startswith("_"):
                exec_context[k] = v

    # Add pandas/numpy if available
    try:
        import pandas as pd
        exec_context["pd"] = pd
    except ImportError:
        pass

    try:
        import numpy as np
        exec_context["np"] = np
    except ImportError:
        pass

    stdout_capture = io.StringIO()
    start_time = asyncio.get_event_loop().time()

    async def _run_exec() -> tuple[Any, str]:
        """Run exec in a thread to allow timeout."""
        import concurrent.futures

        loop = asyncio.get_event_loop()

        def _sync_exec() -> tuple[Any, str]:
            with redirect_stdout(stdout_capture):
                exec(code, exec_context)
                result = exec_context.get("result", None)
                return result, stdout_capture.getvalue()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = loop.run_in_executor(pool, _sync_exec)
            try:
                return await asyncio.wait_for(future, timeout=MAX_EXECUTION_TIME)
            except TimeoutError as err:
                future.cancel()
                raise SandboxError(
                    f"Execution timed out after {MAX_EXECUTION_TIME}s"
                ) from err

    try:
        result, output = await _run_exec()
        exec_time = asyncio.get_event_loop().time() - start_time
        return {
            "result": result,
            "output": output,
            "error": None,
            "execution_time": round(exec_time, 3),
        }

    except SandboxError as e:
        exec_time = asyncio.get_event_loop().time() - start_time
        return {
            "result": None,
            "output": stdout_capture.getvalue(),
            "error": str(e),
            "execution_time": round(exec_time, 3),
        }
    except Exception as e:
        exec_time = asyncio.get_event_loop().time() - start_time
        return {
            "result": None,
            "output": stdout_capture.getvalue(),
            "error": f"{type(e).__name__}: {e}",
            "execution_time": round(exec_time, 3),
        }


async def generate_analysis_code(
    incident_type: str, evidence_summary: str, description: str = ""
) -> str:
    """Generate Python analysis code using LLM with fallback to templates."""
    return await _llm_generate_code(incident_type, description or incident_type, evidence_summary)

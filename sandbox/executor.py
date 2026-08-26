"""Sandbox — safe execution of generated Python analysis code."""

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
    incident_type: str, evidence_summary: str
) -> str:
    """Generate Python analysis code for the given incident."""
    templates = {
        "schema_drift": (
            "import json\n"
            "results = {'analysis_type': 'schema_drift', 'findings': []}\n"
            "results['findings'].append({'metric': 'null_rate_change', "
            "'description': 'Schema drift caused null rate increase', 'severity': 'high'})\n"
            "results['findings'].append({'metric': 'revenue_impact', "
            "'description': 'APAC revenue dropped 42%%', 'severity': 'critical'})\n"
            "result = results\n"
            "print(f'Schema drift analysis: {len(results[\"findings\"])} findings')\n"
        ),
        "pipeline_failure": (
            "results = {'analysis_type': 'pipeline_failure', 'findings': []}\n"
            "results['findings'].append({'metric': 'pipeline_status', "
            "'description': 'Pipeline PL-001 failed', 'severity': 'high'})\n"
            "result = results\n"
            "print(f'Pipeline failure analysis: {len(results[\"findings\"])} findings')\n"
        ),
    }
    return templates.get(incident_type, templates["schema_drift"])

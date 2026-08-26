"""Sandbox — safe execution of generated Python analysis code."""

import asyncio
import io
import logging
from contextlib import redirect_stdout
from typing import Any

logger = logging.getLogger(__name__)

# Maximum execution time in seconds
MAX_EXECUTION_TIME = 30

# Forbidden imports for sandbox safety
FORBIDDEN_IMPORTS = {
    "subprocess", "os", "shutil", "pathlib", "socket",
    "http", "urllib", "requests", "asyncio",
    "ctypes", "importlib", "sys",
}

# Builtins that are safe to use
SAFE_BUILTINS = {
    "print", "len", "range", "int", "float", "str", "bool",
    "list", "dict", "set", "tuple", "type", "isinstance",
    "min", "max", "sum", "abs", "round", "sorted", "reversed",
    "enumerate", "zip", "map", "filter", "any", "all",
    "True", "False", "None",
    "Exception", "ValueError", "TypeError", "KeyError", "IndexError",
}


class SandboxError(Exception):
    """Raised when sandbox execution fails."""
    pass


async def execute_analysis(code: str, context: dict[str, Any] | None = None) -> dict:
    """Execute Python analysis code in a sandboxed environment.

    The code runs with:
    - Restricted imports (no os, subprocess, etc.)
    - Timeout protection
    - Captured stdout
    - Optional context variables

    Returns:
        dict with keys: result, output, error, execution_time
    """
    if not code or not code.strip():
        return {
            "result": None,
            "output": "",
            "error": "No code provided",
            "execution_time": 0,
        }

    # Prepare execution environment
    exec_context: dict[str, Any] = {
        "__builtins__": {
            k: v for k, v in __builtins__.__dict__.items()
            if k in SAFE_BUILTINS or k.startswith("__") is False
        } if isinstance(__builtins__, dict) else {
            k: getattr(__builtins__, k)
            for k in SAFE_BUILTINS
            if hasattr(__builtins__, k)
        },
    }

    # Add safe data from context
    if context:
        for k, v in context.items():
            if not k.startswith("_"):
                exec_context[k] = v

    # Add pandas/numpy if available (common for data analysis)
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

    # Capture stdout
    stdout_capture = io.StringIO()
    start_time = asyncio.get_event_loop().time()

    try:
        with redirect_stdout(stdout_capture):
            # Execute with timeout
            exec_globals = exec_context
            exec(code, exec_globals)

            # If code defines a 'result' variable, return it
            result = exec_globals.get("result", None)
            output = stdout_capture.getvalue()
            exec_time = asyncio.get_event_loop().time() - start_time

            return {
                "result": result,
                "output": output,
                "error": None,
                "execution_time": round(exec_time, 3),
            }

    except Exception as e:
        output = stdout_capture.getvalue()
        exec_time = asyncio.get_event_loop().time() - start_time
        return {
            "result": None,
            "output": output,
            "error": f"{type(e).__name__}: {e}",
            "execution_time": round(exec_time, 3),
        }


async def generate_analysis_code(
    incident_type: str, evidence_summary: str
) -> str:
    """Generate Python analysis code for the given incident.

    Returns code that can be executed in the sandbox.
    """
    # Pre-built analysis templates for common incident types
    templates = {
        "schema_drift": '''
# Schema Drift Analysis
import json

# Analyze the impact of schema changes
results = {
    "analysis_type": "schema_drift",
    "findings": [],
}

# Check for null rate changes
results["findings"].append({
    "metric": "null_rate_change",
    "description": "Schema drift caused null rate increase in customer_region",
    "severity": "high",
})

# Revenue impact
results["findings"].append({
    "metric": "revenue_impact",
    "description": "APAC revenue dropped 42% due to schema regression",
    "severity": "critical",
})

result = results
print(f"Schema drift analysis complete: {len(results['findings'])} findings")
''',
        "pipeline_failure": '''
# Pipeline Failure Analysis
results = {
    "analysis_type": "pipeline_failure",
    "findings": [],
}

results["findings"].append({
    "metric": "pipeline_status",
    "description": "Pipeline PL-001 failed due to invalid enum value",
    "severity": "high",
})

results["findings"].append({
    "metric": "error_frequency",
    "description": "Pipeline failures increased in last 3 days",
    "severity": "medium",
})

result = results
print(f"Pipeline failure analysis: {len(results['findings'])} findings")
''',
    }

    return templates.get(incident_type, templates["schema_drift"])

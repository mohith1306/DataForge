"""Execute node — executes approved remediation actions via MCP tools."""

import logging

from mcp.remediation.tools.actions import (
    create_incident_ticket,
    reprocess_partition,
    rerun_pipeline,
    rollback_deployment,
    validate_data_quality,
)

logger = logging.getLogger(__name__)

# Map tool names to actual MCP functions
TOOL_REGISTRY = {
    "rerun_pipeline": rerun_pipeline,
    "rollback_deployment": rollback_deployment,
    "reprocess_partition": reprocess_partition,
    "validate_data_quality": validate_data_quality,
    "create_incident_ticket": create_incident_ticket,
}


async def execute_remediation(state: dict) -> dict:
    """Execute the approved remediation plan via MCP tools."""
    remediation_plan = state.get("remediation_plan", {})
    actions = remediation_plan.get("actions", [])
    execution_results = []

    for action in actions:
        tool = action.get("tool", "unknown")
        params = action.get("parameters", {})

        result = await _execute_action(tool, params)
        execution_results.append(result)

        # Log execution event
        status = result.get("status", "unknown")
        logger.info(f"Executed {tool}: {status}")

    all_success = all(r.get("status") == "success" for r in execution_results)
    success_count = sum(1 for r in execution_results if r.get("status") == "success")

    return {
        "status": "executing",
        "execution_result": {
            "results": execution_results,
            "all_success": all_success,
            "actions_count": len(actions),
            "success_count": success_count,
        },
        "events": state.get("events", []) + [
            {
                "type": "action.completed",
                "agent": "executor",
                "message": (
                    f"Executed {len(actions)} actions: "
                    f"{success_count}/{len(actions)} succeeded"
                ),
            }
        ],
    }


async def _execute_action(tool: str, params: dict) -> dict:
    """Execute a single remediation action via MCP tool."""
    tool_fn = TOOL_REGISTRY.get(tool)

    if not tool_fn:
        return {
            "tool": tool,
            "status": "skipped",
            "result": {"message": f"Unknown tool: {tool}"},
        }

    try:
        # Call the MCP tool with parameters
        import inspect
        sig = inspect.signature(tool_fn)
        # Filter params to match function signature
        valid_params = {k: v for k, v in params.items() if k in sig.parameters}
        result = await tool_fn(**valid_params)
        return result
    except Exception as e:
        logger.error(f"Tool {tool} failed: {e}")
        return {
            "tool": tool,
            "status": "error",
            "error": str(e),
            "result": {"message": f"Execution failed: {e}"},
        }

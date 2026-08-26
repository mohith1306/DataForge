"""Execute node — executes approved remediation actions."""

import logging

logger = logging.getLogger(__name__)


async def execute_remediation(state: dict) -> dict:
    """Execute the approved remediation plan.

    In a real system, this would call MCP tools to:
    - Rerun pipelines
    - Rollback deployments
    - Reprocess partitions
    - Create tickets

    For the hackathon, we simulate execution and record results.
    """
    remediation_plan = state.get("remediation_plan", {})
    actions = remediation_plan.get("actions", [])
    execution_results = []

    for action in actions:
        tool = action.get("tool", "unknown")
        params = action.get("parameters", {})

        result = await _execute_action(tool, params)
        execution_results.append(result)

    all_success = all(r.get("status") == "success" for r in execution_results)

    return {
        "status": "executing",
        "execution_result": {
            "results": execution_results,
            "all_success": all_success,
            "actions_count": len(actions),
        },
        "events": state.get("events", []) + [
            {
                "type": "action.completed",
                "agent": "executor",
                "message": (
                    f"Executed {len(actions)} actions: "
                    f"{'all succeeded' if all_success else 'some failed'}"
                ),
            }
        ],
    }


async def _execute_action(tool: str, params: dict) -> dict:
    """Execute a single remediation action."""
    if tool == "validate_data_quality":
        return {
            "tool": tool,
            "status": "success",
            "result": {
                "message": "Data quality validation completed",
                "checks_passed": 12,
                "checks_total": 12,
            },
        }
    elif tool == "rerun_pipeline":
        pipeline_id = params.get("pipeline_id", "PL-001")
        return {
            "tool": tool,
            "status": "success",
            "result": {
                "pipeline_id": pipeline_id,
                "message": f"Pipeline {pipeline_id} rerun completed successfully",
                "rows_processed": 150000,
            },
        }
    elif tool == "reprocess_partition":
        table = params.get("table", "customer_orders")
        return {
            "tool": tool,
            "status": "success",
            "result": {
                "table": table,
                "message": f"Table {table} partitions reprocessed",
                "partitions_affected": 5,
            },
        }
    elif tool == "rollback_deployment":
        return {
            "tool": tool,
            "status": "success",
            "result": {"message": "Deployment rolled back to v2.8.0"},
        }
    elif tool == "create_incident_ticket":
        return {
            "tool": tool,
            "status": "success",
            "result": {"ticket_id": "TICKET-2024-001", "message": "Incident ticket created"},
        }
    else:
        return {
            "tool": tool,
            "status": "skipped",
            "result": {"message": f"Action {tool} simulated (not implemented)"},
        }

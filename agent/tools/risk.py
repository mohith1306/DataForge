"""Risk classification for MCP tools.

Classifies tools by risk level:
- LOW: Read-only operations (queries, logs, metrics)
- MEDIUM: Non-destructive actions (rerun, ticket)
- HIGH: Destructive/reversible actions (rollback, reprocess)
- CRITICAL: Irreversible destructive operations (delete, schema modify)
"""

TOOL_RISK_LEVELS = {
    # Database MCP
    "list_tables": "LOW",
    "describe_table": "LOW",
    "execute_select": "LOW",
    "profile_column": "LOW",
    "get_recent_records": "LOW",
    # Monitoring MCP
    "get_pipeline_status": "LOW",
    "get_pipeline_runs": "LOW",
    "get_pipeline_logs": "LOW",
    "get_failed_jobs": "LOW",
    "get_metrics": "LOW",
    # GitHub MCP
    "get_recent_commits": "LOW",
    "get_commit": "LOW",
    "get_pull_request": "LOW",
    "get_changed_files": "LOW",
    "search_commits": "LOW",
    # Remediation MCP
    "rerun_pipeline": "MEDIUM",
    "create_incident_ticket": "MEDIUM",
    "rollback_deployment": "HIGH",
    "reprocess_partition": "HIGH",
    # Critical (never allowed without explicit approval)
    "delete_data": "CRITICAL",
    "modify_schema": "CRITICAL",
}

APPROVAL_REQUIRED_LEVELS = {"HIGH", "CRITICAL"}


def get_risk_level(tool_name: str) -> str:
    """Get the risk level for a tool."""
    return TOOL_RISK_LEVELS.get(tool_name, "MEDIUM")


def requires_approval(tool_name: str) -> bool:
    """Check if a tool requires human approval."""
    level = get_risk_level(tool_name)
    return level in APPROVAL_REQUIRED_LEVELS


def classify_remediation_risk(actions: list[dict]) -> str:
    """Classify the overall risk of a remediation plan.

    Returns the highest risk level among all actions.
    """
    risk_priority = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    highest = "LOW"

    for action in actions:
        tool = action.get("tool", "")
        level = get_risk_level(tool)
        if risk_priority.get(level, 0) > risk_priority.get(highest, 0):
            highest = level

    return highest

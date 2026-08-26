import logging

from agent.agents.evidence_merger import merge_evidence

logger = logging.getLogger(__name__)


async def investigate(state: dict) -> dict:
    """Coordinate parallel investigation across database, pipeline, and GitHub."""
    incident_type = state.get("incident_type", "unknown")
    description = state.get("description", state.get("user_request", ""))

    # Lazy imports to avoid circular dependencies
    from agent.agents.github_agent import investigate_github
    from agent.agents.pipeline_agent import investigate_pipeline

    pipeline_result = {"findings": [], "errors": []}
    github_result = {"findings": [], "errors": []}

    try:
        pipeline_result = await investigate_pipeline(incident_type, description)
    except Exception as e:
        logger.error(f"Pipeline investigation failed: {e}")
        pipeline_result["errors"].append(str(e))

    try:
        github_result = await investigate_github(incident_type, description)
    except Exception as e:
        logger.error(f"GitHub investigation failed: {e}")
        github_result["errors"].append(str(e))

    database_findings = state.get("database_findings", [])
    pipeline_findings = pipeline_result.get("findings", [])
    github_findings = github_result.get("findings", [])

    merged_evidence = merge_evidence(database_findings, pipeline_findings, github_findings)

    return {
        "status": "investigating",
        "pipeline_findings": pipeline_findings,
        "github_findings": github_findings,
        "evidence": merged_evidence,
        "events": state.get("events", []) + [
            {
                "type": "tool.completed",
                "agent": "investigator",
                "tool": "parallel_investigation",
                "message": (
                    f"Parallel investigation: {len(pipeline_findings)} pipeline + "
                    f"{len(github_findings)} github findings merged into "
                    f"{len(merged_evidence)} evidence items"
                ),
            }
        ],
    }

import logging

from agent.agents.database_agent import investigate_database

logger = logging.getLogger(__name__)


async def investigate_database_node(state: dict) -> dict:
    """Investigate database using the Database Agent."""
    incident_type = state.get("incident_type", "unknown")
    description = state.get("description", state.get("user_request", ""))

    try:
        db_result = await investigate_database(incident_type, description)
        database_findings = db_result.get("findings", [])

        return {
            "status": "investigating",
            "database_findings": database_findings,
            "events": state.get("events", []) + [
                {
                    "type": "tool.completed",
                    "agent": "database_agent",
                    "tool": "database_investigation",
                    "message": f"Database investigation: {db_result.get('summary', '')}",
                }
            ],
        }
    except Exception as e:
        logger.error(f"Database investigation failed: {e}")
        return {
            "status": "investigating",
            "database_findings": [],
            "events": state.get("events", []) + [
                {
                    "type": "agent.error",
                    "agent": "database_agent",
                    "message": f"Database investigation failed: {e}",
                }
            ],
        }

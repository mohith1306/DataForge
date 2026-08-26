import json
import logging

from agent.models.llm import get_llm
from agent.prompts.database import CLASSIFY_PROMPT

logger = logging.getLogger(__name__)


async def classify(state: dict) -> dict:
    """Classify the incident using LLM: type, severity, business impact."""
    llm = get_llm()

    title = state.get("user_request", state.get("title", ""))
    description = state.get("description", "")

    try:
        chain = CLASSIFY_PROMPT | llm
        response = await chain.ainvoke({
            "title": title,
            "description": description,
        })

        content = response.content if hasattr(response, "content") else str(response)
        parsed = json.loads(content)

        return {
            "status": "classifying",
            "incident_type": parsed.get("incident_type", "unknown"),
            "severity": parsed.get("severity", "medium"),
            "business_impact": parsed.get("business_impact", ""),
            "events": state.get("events", []) + [
                {
                    "type": "agent.started",
                    "agent": "classifier",
                    "message": (
                        f"Classified as {parsed.get('incident_type', 'unknown')} "
                        f"/ {parsed.get('severity', 'medium')}"
                    ),
                }
            ],
        }
    except Exception as e:
        logger.error(f"Classification failed: {e}")
        return {
            "status": "classifying",
            "incident_type": "unknown",
            "severity": "medium",
            "business_impact": "Unable to classify automatically",
            "events": state.get("events", []) + [
                {
                    "type": "agent.error",
                    "agent": "classifier",
                    "message": f"Classification error: {e}",
                }
            ],
        }

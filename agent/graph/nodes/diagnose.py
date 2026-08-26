"""Diagnose node — analyzes evidence and determines root cause."""

import logging

from agent.agents.root_cause_agent import analyze_root_cause

logger = logging.getLogger(__name__)


async def diagnose(state: dict) -> dict:
    """Run root cause analysis on collected evidence."""
    try:
        result = await analyze_root_cause(state)
        return result
    except Exception as e:
        logger.error(f"Diagnosis failed: {e}")
        return {
            "status": "diagnosing",
            "root_cause": {
                "description": f"Diagnosis failed: {e}",
                "confidence": 0.0,
                "alternatives": [],
                "business_impact": {},
            },
            "confidence": 0.0,
            "events": state.get("events", []) + [
                {
                    "type": "agent.error",
                    "agent": "root_cause_analyst",
                    "message": f"Diagnosis failed: {e}",
                }
            ],
        }

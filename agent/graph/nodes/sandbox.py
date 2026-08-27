"""Sandbox node — runs generated analysis in a safe execution environment."""

import logging

from sandbox.executor import execute_analysis, generate_analysis_code

logger = logging.getLogger(__name__)


async def sandbox_analysis(state: dict) -> dict:
    """Generate and execute analysis code in the sandbox."""
    incident_type = state.get("incident_type", "unknown")
    description = state.get("description", state.get("user_request", ""))
    evidence = state.get("evidence", [])

    # Build evidence summary for code generation
    evidence_summary = "\n".join(
        f"- [{e.get('source', '?')}] {e.get('summary', '')}"
        for e in evidence[:10]
    )

    try:
        # Generate analysis code using LLM
        code = await generate_analysis_code(incident_type, evidence_summary, description)

        # Prepare context with evidence data
        context = {
            "incident_type": incident_type,
            "description": description,
            "evidence": evidence,
            "evidence_summary": evidence_summary,
        }

        # Execute in sandbox
        result = await execute_analysis(code, context)

        return {
            "status": "analyzing",
            "analysis_results": {
                "code_output": result.get("output", ""),
                "result": result.get("result"),
                "error": result.get("error"),
                "execution_time": result.get("execution_time", 0),
                "analysis_type": incident_type,
            },
            "events": state.get("events", []) + [
                {
                    "type": "sandbox.completed",
                    "agent": "sandbox",
                    "message": (
                        f"Sandbox analysis ({incident_type}): "
                        f"{'success' if not result.get('error') else 'error'} "
                        f"in {result.get('execution_time', 0):.1f}s"
                    ),
                }
            ],
        }

    except Exception as e:
        logger.error(f"Sandbox analysis failed: {e}")
        return {
            "status": "analyzing",
            "analysis_results": {
                "code_output": "",
                "result": None,
                "error": str(e),
                "execution_time": 0,
                "analysis_type": incident_type,
            },
            "events": state.get("events", []) + [
                {
                    "type": "sandbox.error",
                    "agent": "sandbox",
                    "message": f"Sandbox analysis failed: {e}",
                }
            ],
        }

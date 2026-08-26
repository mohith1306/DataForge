"""Plan node — generates remediation plan based on root cause analysis."""

import json
import logging

from agent.models.llm import get_llm
from agent.tools.risk import classify_remediation_risk

logger = logging.getLogger(__name__)

PLAN_PROMPT_TEXT = """You are DataForge's Remediation Planner.
Based on the root cause analysis, create a remediation plan.

Root cause: {root_cause}
Confidence: {confidence}
Incident type: {incident_type}
Severity: {severity}

Available remediation actions:
- rerun_pipeline: Re-run a failed pipeline (MEDIUM risk)
- rollback_deployment: Roll back to previous version (HIGH risk)
- reprocess_partition: Reprocess affected data partitions (HIGH risk)
- create_incident_ticket: Create a tracking ticket (MEDIUM risk)
- validate_data_quality: Run data quality checks (LOW risk)

Return JSON with:
{{
  "actions": [
    {{
      "tool": "action_name",
      "description": "what this action does",
      "parameters": {{}},
      "reason": "why this action is needed",
      "expected_result": "what we expect after execution"
    }}
  ],
  "overall_risk": "LOW|MEDIUM|HIGH",
  "requires_approval": true/false
}}
"""


async def plan_remediation(state: dict) -> dict:
    """Generate a remediation plan based on root cause."""
    llm = get_llm()

    root_cause = state.get("root_cause", {})
    incident_type = state.get("incident_type", "unknown")
    severity = state.get("severity", "medium")

    rc_desc = root_cause.get("description", "Unknown root cause")
    confidence = root_cause.get("confidence", 0.5)

    try:
        from langchain_core.prompts import ChatPromptTemplate

        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are DataForge's Remediation Planner. Return JSON only."),
            ("human", PLAN_PROMPT_TEXT),
        ])
        chain = prompt | llm
        response = await chain.ainvoke({
            "root_cause": rc_desc,
            "confidence": f"{confidence:.0%}",
            "incident_type": incident_type,
            "severity": severity,
        })

        content = response.content if hasattr(response, "content") else str(response)
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            parsed = json.loads(content[start:end])
        else:
            parsed = json.loads(content)
    except Exception as e:
        logger.error(f"LLM plan generation failed: {e}, using heuristic")
        parsed = _heuristic_plan(incident_type, root_cause)

    actions = parsed.get("actions", [])
    risk_level = classify_remediation_risk(actions)
    requires_approval = risk_level in ("HIGH", "CRITICAL")

    plan = {
        "actions": actions,
        "risk_level": risk_level,
        "requires_approval": requires_approval,
        "root_cause_confidence": confidence,
        "summary": parsed.get("summary", f"Remediation plan with {len(actions)} actions"),
        "estimated_recovery_time": parsed.get("estimated_recovery_time", "unknown"),
    }

    return {
        "status": "planning",
        "remediation_plan": plan,
        "risk_level": risk_level,
        "approval_required": requires_approval,
        "events": state.get("events", []) + [
            {
                "type": "plan.created",
                "agent": "remediation_planner",
                "message": (
                    f"Remediation plan: {len(actions)} actions, "
                    f"risk={risk_level}"
                ),
                "metadata_": plan,
            }
        ],
    }


def _heuristic_plan(incident_type: str, root_cause: dict) -> dict:
    """Fallback heuristic plan."""
    actions = [
        {
            "tool": "validate_data_quality",
            "description": "Run data quality validation checks",
            "parameters": {},
            "reason": "Verify current data state before remediation",
            "expected_result": "Data quality report",
        }
    ]

    if incident_type in ("schema_drift", "pipeline_failure"):
        actions.append({
            "tool": "rerun_pipeline",
            "description": "Re-run the failed pipeline with corrected schema handling",
            "parameters": {"pipeline_id": "PL-001"},
            "reason": "Pipeline failure detected, rerun after schema fix",
            "expected_result": "Pipeline succeeds with correct data",
        })

    if incident_type == "schema_drift":
        actions.append({
            "tool": "reprocess_partition",
            "description": "Reprocess affected data partitions from the incident window",
            "parameters": {"table": "customer_orders", "date_range": "last_5_days"},
            "reason": "Schema drift corrupted recent partitions",
            "expected_result": "Corrected records in affected partitions",
        })

    return {"actions": actions}

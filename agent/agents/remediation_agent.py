"""Remediation Agent — generates and manages remediation plans."""

import json
import logging
from typing import Any

from agent.models.llm import get_llm
from agent.tools.risk import classify_remediation_risk, requires_approval

logger = logging.getLogger(__name__)

REMEDIATION_PROMPT = """You are DataForge's Remediation Agent.
Based on the root cause analysis, create a detailed remediation plan.

Root cause: {root_cause}
Confidence: {confidence}
Incident type: {incident_type}
Severity: {severity}

Available MCP tools:
- rerun_pipeline(pipeline_id): Re-run a failed pipeline (MEDIUM risk)
- rollback_deployment(deployment_id): Roll back to previous version (HIGH risk)
- reprocess_partition(table, date_range): Reprocess affected data (HIGH risk)
- validate_data_quality(): Run data quality checks (LOW risk)
- create_incident_ticket(title, description): Create tracking ticket (MEDIUM risk)

Return a JSON remediation plan:
{{
  "actions": [
    {{
      "tool": "tool_name",
      "parameters": {{}},
      "description": "what this does",
      "reason": "why needed",
      "expected_result": "expected outcome",
      "order": 1
    }}
  ],
  "summary": "brief plan summary",
  "estimated_recovery_time": "e.g. 15 minutes"
}}
"""


async def plan_remediation(state: dict) -> dict:
    """Generate a remediation plan using LLM."""
    llm = get_llm()

    root_cause = state.get("root_cause", {})
    incident_type = state.get("incident_type", "unknown")
    severity = state.get("severity", "medium")

    rc_desc = root_cause.get("description", "Unknown root cause")
    confidence = root_cause.get("confidence", 0.5)

    try:
        from langchain_core.prompts import ChatPromptTemplate

        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are DataForge's Remediation Agent. Return JSON only."),
            ("human", REMEDIATION_PROMPT),
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
        logger.error(f"LLM remediation planning failed: {e}, using heuristic")
        parsed = _heuristic_plan(incident_type, root_cause)

    actions = parsed.get("actions", [])

    # Classify risk and check approval requirements
    risk_level = classify_remediation_risk(actions)
    approval_required = any(requires_approval(a.get("tool", "")) for a in actions)

    plan = {
        "actions": actions,
        "risk_level": risk_level,
        "requires_approval": approval_required,
        "summary": parsed.get("summary", "Remediation plan generated"),
        "estimated_recovery_time": parsed.get("estimated_recovery_time", "unknown"),
        "root_cause_confidence": confidence,
    }

    return {
        "status": "planning",
        "remediation_plan": plan,
        "risk_level": risk_level,
        "approval_required": approval_required,
        "events": state.get("events", []) + [
            {
                "type": "plan.created",
                "agent": "remediation_planner",
                "message": (
                    f"Remediation plan: {len(actions)} actions, "
                    f"risk={risk_level}"
                ),
            }
        ],
    }


def _heuristic_plan(incident_type: str, root_cause: dict) -> dict[str, Any]:
    """Fallback heuristic plan when LLM fails."""
    actions = [
        {
            "tool": "validate_data_quality",
            "parameters": {},
            "description": "Run comprehensive data quality validation",
            "reason": "Verify current data state before remediation",
            "expected_result": "Data quality report with all checks",
            "order": 1,
        }
    ]

    if incident_type in ("schema_drift", "pipeline_failure"):
        actions.append({
            "tool": "rerun_pipeline",
            "parameters": {"pipeline_id": "PL-001"},
            "description": "Re-run failed pipeline PL-001",
            "reason": "Pipeline failure detected, rerun after schema fix",
            "expected_result": "Pipeline succeeds with correct data",
            "order": 2,
        })

    if incident_type == "schema_drift":
        actions.append({
            "tool": "reprocess_partition",
            "parameters": {"table": "customer_orders", "date_range": "last_5_days"},
            "description": "Reprocess affected partitions from incident window",
            "reason": "Schema drift corrupted recent partitions",
            "expected_result": "Corrected records in affected partitions",
            "order": 3,
        })

    actions.append({
        "tool": "create_incident_ticket",
        "parameters": {
            "title": f"Incident: {incident_type}",
            "description": root_cause.get("description", "Auto-created by DataForge"),
        },
        "description": "Create incident tracking ticket",
        "reason": "Track incident for post-mortem",
        "expected_result": "Ticket created",
        "order": len(actions) + 1,
    })

    return {"actions": actions, "summary": f"Auto-generated plan for {incident_type}"}

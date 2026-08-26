"""Approval node — handles human approval gate for risky remediation actions."""

import logging

logger = logging.getLogger(__name__)


async def approval_gate(state: dict) -> dict:
    """Approval gate — pause and wait for human approval if required.

    In the autonomous workflow, this node sets approval_required=True
    and the workflow pauses until approval is received via the API.
    """
    approval_required = state.get("approval_required", False)
    remediation_plan = state.get("remediation_plan", {})
    risk_level = state.get("risk_level", "LOW")

    if not approval_required:
        return {
            "status": "approved",
            "approval_status": "auto_approved",
            "events": state.get("events", []) + [
                {
                    "type": "approval.auto_approved",
                    "agent": "approval_gate",
                    "message": f"Auto-approved: risk level {risk_level} does not require approval",
                }
            ],
        }

    actions = remediation_plan.get("actions", [])
    action_descriptions = "\n".join(
        f"  - {a.get('tool', 'unknown')}: {a.get('description', '')}"
        for a in actions
    )

    return {
        "status": "awaiting_approval",
        "approval_status": "pending",
        "events": state.get("events", []) + [
            {
                "type": "approval.required",
                "agent": "approval_gate",
                "message": (
                    f"HUMAN APPROVAL REQUIRED (risk: {risk_level})\n"
                    f"Proposed actions:\n{action_descriptions}"
                ),
            }
        ],
    }


async def process_approval(state: dict) -> dict:
    """Process the approval decision (called after human responds)."""
    approval_status = state.get("approval_status", "pending")

    if approval_status == "approved":
        return {
            "status": "approved",
            "events": state.get("events", []) + [
                {
                    "type": "approval.approved",
                    "agent": "approval_gate",
                    "message": "Remediation approved by human reviewer",
                }
            ],
        }
    elif approval_status == "rejected":
        return {
            "status": "rejected",
            "events": state.get("events", []) + [
                {
                    "type": "approval.rejected",
                    "agent": "approval_gate",
                    "message": "Remediation rejected — incident will be re-investigated",
                }
            ],
        }
    else:
        return {
            "status": "awaiting_approval",
            "events": state.get("events", []) + [
                {
                    "type": "approval.pending",
                    "agent": "approval_gate",
                    "message": "Still awaiting human approval",
                }
            ],
        }

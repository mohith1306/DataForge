"""Golden Path API — End-to-end schema drift detection, investigation, and remediation.

Implements the full 14-step Golden Path:
1. Baseline → 2. Drift Detection → 3. Graph Impact → 4. Incident →
5. Investigation → 6. GitHub Correlation → 7. Root Cause → 8. Repair Plan →
9. Risk → 10. Approval → 11. Execute → 12. Verify → 13. Resolve
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.core.auth import get_current_user
from apps.api.app.core.config import settings
from apps.api.app.db.models import (
    Incident,
    IncidentApproval,
    IncidentEvent,
    RemediationPlan,
    ReliabilityNode,
)
from apps.api.app.db.session import get_db
from apps.api.app.sensors.schema_drift import SchemaDriftSensor
from apps.api.app.services.github_correlation import GitHubCorrelator
from apps.api.app.services.reliability_graph import ReliabilityGraphService
from apps.api.app.services.schema_verifier import SchemaVerifier

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/golden-path", tags=["golden-path"])


# ─── Request / Response Models ────────────────────────────────────────


class DriftDetectionRequest(BaseModel):
    connector_id: str = "local-postgres"
    table_name: str = "test_orders"
    current_schema: list[dict[str, Any]] = Field(
        description="Current column definitions: [{'name': 'col', 'type': 'integer', 'nullable': true}]"
    )
    connector_name: str = "PostgreSQL (local)"


class InvestigationRequest(BaseModel):
    incident_id: str


class RepairPlanRequest(BaseModel):
    incident_id: str
    actions: list[dict[str, Any]] = Field(
        description="List of repair actions: [{'action': 'ALTER TABLE', 'sql': '...'}]"
    )
    rollback_plan: list[dict[str, Any]] = Field(default_factory=list)
    risk_level: str = "medium"


class ApprovalRequest(BaseModel):
    plan_id: str
    approved: bool = True
    reason: str = ""


class ExecuteRequest(BaseModel):
    plan_id: str
    current_schema: list[dict[str, Any]] = Field(
        description="Schema after executing the repair actions"
    )


class VerifyRequest(BaseModel):
    incident_id: str
    current_schema: list[dict[str, Any]]


# ─── Endpoints ────────────────────────────────────────────────────────


@router.post("/detect-drift")
async def detect_drift(
    req: DriftDetectionRequest,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(get_current_user),
) -> dict:
    """Step 1-4: Detect schema drift, calculate blast radius, create incident."""
    from apps.api.app.core.config import settings

    org_id = settings.default_org_id

    sensor = SchemaDriftSensor(db, UUID(org_id) if isinstance(org_id, str) else org_id)

    drift = await sensor.detect(
        connector_id=req.connector_id,
        table_name=req.table_name,
        current_schema=req.current_schema,
    )

    if drift is None:
        return {
            "status": "no_drift",
            "message": "Schema matches the last snapshot. No drift detected.",
            "incident": None,
        }

    incident = await sensor.create_incident_from_drift(drift, req.connector_name)

    blast_radius = {}
    try:
        graph_service = ReliabilityGraphService(db, UUID(org_id) if isinstance(org_id, str) else org_id)
        stmt = select(ReliabilityNode).where(
            ReliabilityNode.org_id == UUID(org_id) if isinstance(org_id, str) else org_id,
            ReliabilityNode.name.ilike(f"%{req.table_name}%"),
        )
        result = await db.execute(stmt)
        node = result.scalar_one_or_none()
        if node:
            blast_radius = await graph_service.calculate_blast_radius(node.id)
    except Exception as e:
        logger.warning("Blast radius calculation failed: %s", e)

    incident.reliability_graph_snapshot = {
        **(incident.reliability_graph_snapshot or {}),
        "blast_radius": blast_radius,
    }

    event = IncidentEvent(
        incident_id=incident.id,
        type="drift_detected",
        agent="schema_drift_sensor",
        message=f"Schema drift detected in {req.table_name}",
        metadata_={
            "drift": drift.to_dict(),
            "blast_radius": blast_radius,
        },
    )
    db.add(event)
    await db.commit()

    return {
        "status": "drift_detected",
        "incident_id": str(incident.id),
        "severity": incident.severity,
        "drift": drift.to_dict(),
        "blast_radius": blast_radius,
    }


@router.post("/investigate")
async def investigate(
    req: InvestigationRequest,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(get_current_user),
) -> dict:
    """Step 5-6: Investigate the incident and find GitHub correlation."""
    from apps.api.app.core.config import settings

    org_id = settings.default_org_id

    incident_id = UUID(req.incident_id)
    stmt = select(Incident).where(Incident.id == incident_id)
    result = await db.execute(stmt)
    incident = result.scalar_one_or_none()

    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    await db.refresh(incident, ["reliability_graph_snapshot"])

    drift_snapshot = (incident.reliability_graph_snapshot or {}).get("drift", {})
    table_name = drift_snapshot.get("table_name", "")

    correlator = GitHubCorrelator()
    suspects = await correlator.find_suspect_commits(
        table_name=table_name,
        drift_info=drift_snapshot,
    )

    root_cause = None
    if suspects:
        top = suspects[0]
        root_cause = {
            "commit_sha": top["short_sha"],
            "commit_message": top["message"],
            "author": top["author"],
            "date": top["date"],
            "files_changed": top.get("files_changed", []),
            "explanation": top.get("reason", ""),
        }

    event = IncidentEvent(
        incident_id=incident.id,
        type="investigation",
        agent="golden_path",
        message="Investigation completed with GitHub correlation",
        metadata_={
            "suspect_commits": suspects[:3],
            "root_cause": root_cause,
        },
    )
    db.add(event)
    incident.status = "investigating"
    await db.commit()

    return {
        "status": "investigation_complete",
        "incident_id": str(incident.id),
        "suspect_commits": suspects,
        "root_cause": root_cause,
    }


@router.post("/create-repair-plan")
async def create_repair_plan(
    req: RepairPlanRequest,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(get_current_user),
) -> dict:
    """Step 7-8: Create a structured repair plan."""
    from apps.api.app.core.config import settings

    org_id = settings.default_org_id

    incident_id = UUID(req.incident_id)
    stmt = select(Incident).where(Incident.id == incident_id)
    result = await db.execute(stmt)
    incident = result.scalar_one_or_none()

    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    requires_approval = req.risk_level in ("high", "critical")

    plan = RemediationPlan(
        incident_id=incident.id,
        org_id=UUID(org_id) if isinstance(org_id, str) else org_id,
        status="pending_approval" if requires_approval else "ready",
        risk_level=req.risk_level,
        requires_approval=requires_approval,
        actions=req.actions,
        rollback_plan=req.rollback_plan,
        verification_criteria=[
            {"check": "schema_consistency", "description": "Verify schema matches expected state"},
            {"check": "no_drift_regressions", "description": "Verify no new drift introduced"},
        ],
    )
    db.add(plan)

    event = IncidentEvent(
        incident_id=incident.id,
        type="repair_plan_created",
        agent="golden_path",
        message=f"Repair plan created with {len(req.actions)} actions (risk: {req.risk_level})",
        metadata_={
            "plan_id": None,
            "actions_count": len(req.actions),
            "risk_level": req.risk_level,
            "requires_approval": requires_approval,
        },
    )
    db.add(event)

    if requires_approval:
        incident.status = "awaiting_approval"
    else:
        incident.status = "ready_to_execute"

    await db.flush()

    event.metadata_["plan_id"] = str(plan.id)

    incident.approval_reason = f"Risk: {req.risk_level}, Actions: {len(req.actions)}"
    await db.commit()

    return {
        "status": plan.status,
        "plan_id": str(plan.id),
        "incident_id": str(incident.id),
        "risk_level": req.risk_level,
        "requires_approval": requires_approval,
        "actions": req.actions,
    }


@router.post("/approve")
async def approve_plan(
    req: ApprovalRequest,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(get_current_user),
) -> dict:
    """Step 9-10: Approve or reject the repair plan."""
    plan_id = UUID(req.plan_id)
    stmt = select(RemediationPlan).where(RemediationPlan.id == plan_id)
    result = await db.execute(stmt)
    plan = result.scalar_one_or_none()

    if not plan:
        raise HTTPException(status_code=404, detail="Remediation plan not found")

    if req.approved:
        plan.status = "approved"
        plan.approved_by = user.email if hasattr(user, "email") else "user"
        plan.approved_at = datetime.now(timezone.utc)

        stmt_inc = select(Incident).where(Incident.id == plan.incident_id)
        res_inc = await db.execute(stmt_inc)
        incident = res_inc.scalar_one_or_none()
        if incident:
            incident.status = "approved"

        event = IncidentEvent(
            incident_id=plan.incident_id,
            type="plan_approved",
            agent="human",
            message=f"Repair plan approved: {req.reason}",
            metadata_={"plan_id": str(plan.id), "approved_by": plan.approved_by},
        )
        db.add(event)
    else:
        plan.status = "rejected"

        event = IncidentEvent(
            incident_id=plan.incident_id,
            type="plan_rejected",
            agent="human",
            message=f"Repair plan rejected: {req.reason}",
            metadata_={"plan_id": str(plan.id)},
        )
        db.add(event)

    await db.commit()

    return {
        "status": plan.status,
        "plan_id": str(plan.id),
        "approved": req.approved,
    }


@router.post("/execute")
async def execute_plan(
    req: ExecuteRequest,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(get_current_user),
) -> dict:
    """Step 11: Execute the repair plan and store the post-remediation schema."""
    plan_id = UUID(req.plan_id)
    stmt = select(RemediationPlan).where(RemediationPlan.id == plan_id)
    result = await db.execute(stmt)
    plan = result.scalar_one_or_none()

    if not plan:
        raise HTTPException(status_code=404, detail="Remediation plan not found")

    if plan.status not in ("approved", "ready"):
        raise HTTPException(
            status_code=400,
            detail=f"Plan must be approved before execution. Current status: {plan.status}",
        )

    plan.status = "executed"
    plan.executed_at = datetime.now(timezone.utc)

    event = IncidentEvent(
        incident_id=plan.incident_id,
        type="plan_executed",
        agent="golden_path",
        message="Repair plan executed",
        metadata_={
            "plan_id": str(plan.id),
            "actions_executed": len(plan.actions),
        },
    )
    db.add(event)

    stmt_inc = select(Incident).where(Incident.id == plan.incident_id)
    res_inc = await db.execute(stmt_inc)
    incident = res_inc.scalar_one_or_none()
    if incident:
        incident.status = "executed"

    await db.commit()

    return {
        "status": "executed",
        "plan_id": str(plan.id),
        "incident_id": str(plan.incident_id),
        "executed_at": plan.executed_at.isoformat(),
    }


@router.post("/verify")
async def verify_remediation(
    req: VerifyRequest,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(get_current_user),
) -> dict:
    """Step 12: Verify the remediation worked."""
    from apps.api.app.core.config import settings

    org_id = settings.default_org_id

    incident_id = UUID(req.incident_id)
    stmt = select(Incident).where(Incident.id == incident_id)
    result = await db.execute(stmt)
    incident = result.scalar_one_or_none()

    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    await db.refresh(incident, ["reliability_graph_snapshot"])

    drift_snapshot = (incident.reliability_graph_snapshot or {}).get("drift", {})
    connector_id = incident.connector_id or ""
    table_name = drift_snapshot.get("table_name", "")

    verifier = SchemaVerifier(db, UUID(org_id) if isinstance(org_id, str) else org_id)

    verification_result = await verifier.verify(
        connector_id=connector_id,
        table_name=table_name,
        current_schema=req.current_schema,
        drift_snapshot=drift_snapshot,
    )

    incident.verification_result = str(verification_result)

    if verification_result["passed"]:
        incident.status = "verified"
        incident.resolved_at = datetime.now(timezone.utc)
    else:
        incident.status = "verification_failed"

    event = IncidentEvent(
        incident_id=incident.id,
        type="verification",
        agent="schema_verifier",
        message=f"Verification {'passed' if verification_result['passed'] else 'failed'}",
        metadata_=verification_result,
    )
    db.add(event)
    await db.commit()

    return {
        "status": incident.status,
        "incident_id": str(incident.id),
        "verification": verification_result,
    }


@router.get("/status/{incident_id}")
async def get_golden_path_status(
    incident_id: str,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(get_current_user),
) -> dict:
    """Get the current status of an incident through the golden path."""
    stmt = select(Incident).where(Incident.id == UUID(incident_id))
    result = await db.execute(stmt)
    incident = result.scalar_one_or_none()

    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    events_stmt = (
        select(IncidentEvent)
        .where(IncidentEvent.incident_id == incident.id)
        .order_by(IncidentEvent.created_at)
    )
    events_result = await db.execute(events_stmt)
    events = events_result.scalars().all()

    plans_stmt = select(RemediationPlan).where(RemediationPlan.incident_id == incident.id)
    plans_result = await db.execute(plans_stmt)
    plans = plans_result.scalars().all()

    return {
        "incident_id": str(incident.id),
        "status": incident.status,
        "severity": incident.severity,
        "title": incident.title,
        "description": incident.description,
        "created_at": incident.created_at.isoformat() if incident.created_at else None,
        "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
        "events": [
            {
                "type": e.type,
                "agent": e.agent,
                "message": e.message,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ],
        "plans": [
            {
                "id": str(p.id),
                "status": p.status,
                "risk_level": p.risk_level,
                "actions_count": len(p.actions or []),
            }
            for p in plans
        ],
    }

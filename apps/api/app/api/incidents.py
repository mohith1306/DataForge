"""Incidents API — CRUD, workflow triggers, approval, and SSE publishing."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.api.stream import publish_event
from apps.api.app.db.models import Incident, IncidentEvent
from apps.api.app.db.session import get_db
from apps.api.app.schemas.incident import (
    ApprovalRequest,
    IncidentCreate,
    IncidentResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/incidents", tags=["incidents"])


def _incident_to_dict(inc: Incident) -> dict:
    return {
        "id": str(inc.id),
        "title": inc.title,
        "severity": inc.severity,
        "status": inc.status,
        "incident_type": inc.incident_type,
    }


@router.post("/", response_model=IncidentResponse, status_code=201)
async def create_incident(payload: IncidentCreate, db: AsyncSession = Depends(get_db)) -> Incident:
    incident = Incident(
        title=payload.title,
        description=payload.description,
        severity=payload.severity,
        incident_type=payload.incident_type,
        status="created",
    )
    db.add(incident)
    await db.flush()
    await db.refresh(incident)
    await db.commit()
    return incident


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)) -> dict:
    """Return aggregate stats independent of list filters."""
    result = await db.execute(select(Incident))
    all_incidents = list(result.scalars().all())
    return {
        "total": len(all_incidents),
        "open": sum(1 for i in all_incidents if i.status not in ("resolved", "failed")),
        "resolved": sum(1 for i in all_incidents if i.status == "resolved"),
        "critical": sum(1 for i in all_incidents if i.severity == "critical"),
    }


@router.get("/", response_model=list[IncidentResponse])
async def list_incidents(
    status: str | None = None,
    severity: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> list[Incident]:
    query = select(Incident).order_by(Incident.created_at.desc()).limit(limit)
    if status:
        query = query.where(Incident.status == status)
    if severity:
        query = query.where(Incident.severity == severity)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(incident_id: str, db: AsyncSession = Depends(get_db)) -> Incident:
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@router.post("/{incident_id}/start")
async def start_investigation(incident_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    """Transition incident to investigating status and publish SSE event."""
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    if incident.status != "created":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot start investigation from status: {incident.status}",
        )

    incident.status = "investigating"

    event = IncidentEvent(
        incident_id=incident.id,
        type="investigation.started",
        agent="system",
        message="Investigation started",
    )
    db.add(event)
    await db.flush()
    await db.commit()

    await publish_event(str(incident_id), {
        "type": "incident.updated",
        "data": _incident_to_dict(incident),
    })

    return {"status": "started", "incident_id": str(incident_id)}


@router.post("/{incident_id}/remediate")
async def execute_remediation(incident_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    """Transition incident to executing status and publish SSE event."""
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    if incident.status != "awaiting_approval":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot remediate from status: {incident.status}",
        )

    incident.status = "executing"

    event = IncidentEvent(
        incident_id=incident.id,
        type="remediation.executing",
        agent="system",
        message="Remediation execution started",
    )
    db.add(event)
    await db.flush()
    await db.commit()

    await publish_event(str(incident_id), {
        "type": "incident.updated",
        "data": _incident_to_dict(incident),
    })

    return {"status": "executing", "incident_id": str(incident_id)}


@router.post("/{incident_id}/approval")
async def handle_approval(
    incident_id: str,
    payload: ApprovalRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Approve or reject a remediation plan."""
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    if incident.status != "awaiting_approval":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve from status: {incident.status}",
        )

    if payload.action == "approve":
        incident.status = "executing"
        message = f"Approved by {payload.reviewer}"
    elif payload.action == "reject":
        incident.status = "failed"
        message = f"Rejected by {payload.reviewer}"
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {payload.action}")

    event = IncidentEvent(
        incident_id=incident.id,
        type=f"approval.{payload.action}d",
        agent="system",
        message=message,
    )
    db.add(event)
    await db.flush()
    await db.commit()

    await publish_event(str(incident_id), {
        "type": "incident.updated",
        "data": _incident_to_dict(incident),
    })

    return {"status": incident.status, "action": payload.action}

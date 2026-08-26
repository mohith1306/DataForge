"""Chaos engineering endpoints for fault injection."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.api.stream import publish_event
from apps.api.app.db.models import Incident, IncidentEvent
from apps.api.app.db.session import get_db

router = APIRouter(prefix="/chaos", tags=["chaos"])


class ChaosRequest(BaseModel):
    fault_type: str
    target: str | None = None


class ChaosResponse(BaseModel):
    status: str
    fault_type: str
    message: str
    incident_id: str | None = None


# Map chaos fault types to canonical incident types used by agents
CHAOS_TO_CANONICAL = {
    "schema_drift": "schema_drift",
    "null_injection": "null_explosion",
    "volume_drop": "volume_drop",
    "duplicate_injection": "duplicate_records",
    "freshness_lag": "freshness_lag",
    "distribution_shift": "distribution_shift",
    "pipeline_failure": "pipeline_failure",
}

FAULT_DESCRIPTIONS = {
    "schema_drift": "Schema drift detected — unexpected column types in customer_orders",
    "null_injection": "Null values injected into amount column",
    "volume_drop": "Data volume dropped 60% in last 24 hours",
    "duplicate_injection": "Duplicate order records detected",
    "freshness_lag": "Data freshness lag — 3 hours behind schedule",
    "distribution_shift": "Regional distribution shifted — APAC share dropped to 5%",
    "pipeline_failure": "Pipeline spark-ingest-orders failed",
}

FAULT_SEVERITY = {
    "schema_drift": "high",
    "null_injection": "medium",
    "volume_drop": "high",
    "duplicate_injection": "medium",
    "freshness_lag": "low",
    "distribution_shift": "high",
    "pipeline_failure": "critical",
}


def _incident_to_dict(inc: Incident) -> dict:
    return {
        "id": str(inc.id),
        "title": inc.title,
        "severity": inc.severity,
        "status": inc.status,
        "incident_type": inc.incident_type,
    }


@router.post("/{fault_type}", response_model=ChaosResponse)
async def inject_fault(
    fault_type: str,
    payload: ChaosRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> ChaosResponse:
    """Inject a chaos fault, create incident, and auto-start investigation."""
    if fault_type not in FAULT_DESCRIPTIONS:
        available = list(FAULT_DESCRIPTIONS.keys())
        return ChaosResponse(
            status="error",
            fault_type=fault_type,
            message=f"Unknown fault type: {fault_type}. Available: {available}",
        )

    description = FAULT_DESCRIPTIONS[fault_type]
    severity = FAULT_SEVERITY.get(fault_type, "medium")
    # Use canonical type (no chaos_ prefix) so agents can dispatch correctly
    canonical_type = CHAOS_TO_CANONICAL.get(fault_type, fault_type)

    incident = Incident(
        title=f"Chaos: {fault_type.replace('_', ' ').title()}",
        description=f"[CHAOS INJECTION] {description}",
        severity=severity,
        status="investigating",
        incident_type=canonical_type,
        created_at=datetime.now(UTC),
    )
    db.add(incident)
    await db.flush()
    await db.refresh(incident)

    # Create investigation started event
    event = IncidentEvent(
        incident_id=incident.id,
        type="investigation.started",
        agent="system",
        message=f"Auto-started investigation for chaos fault: {fault_type}",
    )
    db.add(event)
    await db.flush()
    await db.commit()

    # Publish SSE events
    incident_data = _incident_to_dict(incident)
    await publish_event(str(incident.id), {
        "type": "incident.updated",
        "data": incident_data,
    })
    await publish_event(str(incident.id), {
        "type": "event.created",
        "data": {
            "type": "investigation.started",
            "agent": "system",
            "message": f"Auto-started investigation for chaos fault: {fault_type}",
        },
    })

    return ChaosResponse(
        status="injected",
        fault_type=fault_type,
        message=description,
        incident_id=str(incident.id),
    )


@router.get("/faults")
async def list_faults() -> dict:
    """List available chaos fault types."""
    return {
        "faults": [
            {
                "type": ft,
                "description": FAULT_DESCRIPTIONS[ft],
                "severity": FAULT_SEVERITY.get(ft, "medium"),
            }
            for ft in FAULT_DESCRIPTIONS
        ]
    }

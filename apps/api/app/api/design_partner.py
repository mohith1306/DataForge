"""Design Partner API — endpoints for design partner management and KPI tracking.

Provides endpoints for:
- Partner onboarding and lifecycle management
- Baseline measurement
- KPI tracking
- Progressive autonomy control
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from apps.api.app.core.auth import get_current_user
from apps.api.app.services.design_partner import (
    DesignPartnerManager,
    BaselineMetrics,
    PartnerStatus,
    AutonomyStage,
)
from apps.api.app.services.kpi_tracker import KPITracker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/design-partner", tags=["design-partner"])

manager = DesignPartnerManager()
kpi_tracker = KPITracker()


# ─── Request Models ────────────────────────────────────────────────────


class AddPartnerRequest(BaseModel):
    name: str
    industry: str = ""
    data_platforms: list[str] = Field(default_factory=list)
    pipeline_count: int = 0
    contact_name: str = ""
    contact_email: str = ""


class BaselineRequest(BaseModel):
    partner_id: str
    incident_count: int = 0
    mttr_hours: float = 0.0
    time_to_diagnosis_hours: float = 0.0
    time_to_remediation_hours: float = 0.0
    false_positive_rate: float = 0.0
    missed_incidents: int = 0
    engineer_hours_per_week: float = 0.0


class DetectionEventRequest(BaseModel):
    incident_id: str
    detection_latency_ms: float
    detected: bool = True
    true_positive: bool | None = None


class DiagnosisEventRequest(BaseModel):
    incident_id: str
    diagnosis_time_ms: float
    root_cause_correct: bool | None = None
    evidence_relevant: bool | None = None


class RemediationEventRequest(BaseModel):
    incident_id: str
    plan_accepted: bool
    execution_success: bool
    rolled_back: bool = False
    remediation_time_ms: float = 0.0


class VerificationEventRequest(BaseModel):
    incident_id: str
    verification_passed: bool
    false_resolution: bool = False


class NoteRequest(BaseModel):
    note: str
    author: str = ""


# ─── Partner Management Endpoints ─────────────────────────────────────


@router.post("/partner")
async def add_partner(
    req: AddPartnerRequest,
    user: Any = Depends(get_current_user),
) -> dict:
    """Add a new design partner."""
    partner_id = str(uuid4())[:8]
    partner = manager.add_partner(
        partner_id=partner_id,
        name=req.name,
        industry=req.industry,
        data_platforms=req.data_platforms,
        pipeline_count=req.pipeline_count,
        contact_name=req.contact_name,
        contact_email=req.contact_email,
    )
    return {"status": "created", "partner": partner.to_dict()}


@router.post("/partner/{partner_id}/onboard")
async def start_onboarding(
    partner_id: str,
    user: Any = Depends(get_current_user),
) -> dict:
    """Start onboarding for a design partner."""
    partner = manager.start_onboarding(partner_id)
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")
    return {"status": "onboarding", "partner": partner.to_dict()}


@router.post("/partner/{partner_id}/stage/{stage}")
async def set_stage(
    partner_id: str,
    stage: str,
    user: Any = Depends(get_current_user),
) -> dict:
    """Set the autonomy stage for a design partner."""
    stage_map = {
        "read_only": manager.enable_read_only,
        "recommended": manager.enable_recommended_remediation,
        "approval_controlled": manager.enable_approval_controlled,
        "autonomous": manager.enable_autonomous,
    }
    setter = stage_map.get(stage)
    if not setter:
        raise HTTPException(status_code=400, detail=f"Invalid stage: {stage}")

    partner = setter(partner_id)
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")
    return {"status": "stage_updated", "partner": partner.to_dict()}


@router.get("/partner/{partner_id}")
async def get_partner(
    partner_id: str,
    user: Any = Depends(get_current_user),
) -> dict:
    """Get a design partner."""
    partner = manager.get_partner(partner_id)
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")
    return partner.to_dict()


@router.get("/partners")
async def list_partners(
    status: str | None = None,
    user: Any = Depends(get_current_user),
) -> dict:
    """List all design partners."""
    partner_status = PartnerStatus(status) if status else None
    partners = manager.list_partners(status=partner_status)
    return {
        "count": len(partners),
        "partners": [p.to_dict() for p in partners],
    }


@router.post("/partner/{partner_id}/note")
async def add_note(
    partner_id: str,
    req: NoteRequest,
    user: Any = Depends(get_current_user),
) -> dict:
    """Add a note to a partner's record."""
    success = manager.add_note(partner_id, req.note, req.author)
    if not success:
        raise HTTPException(status_code=404, detail="Partner not found")
    return {"status": "note_added"}


# ─── Baseline Endpoints ───────────────────────────────────────────────


@router.post("/baseline")
async def record_baseline(
    req: BaselineRequest,
    user: Any = Depends(get_current_user),
) -> dict:
    """Record baseline metrics for a design partner."""
    partner = manager.get_partner(req.partner_id)
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")

    baseline = BaselineMetrics(
        partner_id=req.partner_id,
        incident_count=req.incident_count,
        mttr_seconds=req.mttr_hours * 3600,
        time_to_diagnosis_seconds=req.time_to_diagnosis_hours * 3600,
        time_to_remediation_seconds=req.time_to_remediation_hours * 3600,
        false_positive_rate=req.false_positive_rate,
        missed_incidents=req.missed_incidents,
        engineer_hours_per_week=req.engineer_hours_per_week,
    )
    manager.record_baseline(baseline)
    return {"status": "baseline_recorded", "baseline": baseline.to_dict()}


@router.get("/baseline/{partner_id}")
async def get_baseline(
    partner_id: str,
    user: Any = Depends(get_current_user),
) -> dict:
    """Get baseline metrics for a design partner."""
    baseline = manager.get_baseline(partner_id)
    if not baseline:
        raise HTTPException(status_code=404, detail="Baseline not found")
    return baseline.to_dict()


# ─── KPI Tracking Endpoints ───────────────────────────────────────────


@router.post("/kpi/detection")
async def record_detection(
    req: DetectionEventRequest,
    user: Any = Depends(get_current_user),
) -> dict:
    """Record a detection event."""
    kpi_tracker.record_detection(
        incident_id=req.incident_id,
        detection_latency_ms=req.detection_latency_ms,
        detected=req.detected,
        true_positive=req.true_positive,
    )
    return {"status": "recorded"}


@router.post("/kpi/diagnosis")
async def record_diagnosis(
    req: DiagnosisEventRequest,
    user: Any = Depends(get_current_user),
) -> dict:
    """Record a diagnosis event."""
    kpi_tracker.record_diagnosis(
        incident_id=req.incident_id,
        diagnosis_time_ms=req.diagnosis_time_ms,
        root_cause_correct=req.root_cause_correct,
        evidence_relevant=req.evidence_relevant,
    )
    return {"status": "recorded"}


@router.post("/kpi/remediation")
async def record_remediation(
    req: RemediationEventRequest,
    user: Any = Depends(get_current_user),
) -> dict:
    """Record a remediation event."""
    kpi_tracker.record_remediation(
        incident_id=req.incident_id,
        plan_accepted=req.plan_accepted,
        execution_success=req.execution_success,
        rolled_back=req.rolled_back,
        remediation_time_ms=req.remediation_time_ms,
    )
    return {"status": "recorded"}


@router.post("/kpi/verification")
async def record_verification(
    req: VerificationEventRequest,
    user: Any = Depends(get_current_user),
) -> dict:
    """Record a verification event."""
    kpi_tracker.record_verification(
        incident_id=req.incident_id,
        verification_passed=req.verification_passed,
        false_resolution=req.false_resolution,
    )
    return {"status": "recorded"}


@router.get("/kpi/all")
async def get_all_kpis(
    user: Any = Depends(get_current_user),
) -> dict:
    """Get all KPI statistics."""
    return kpi_tracker.get_all_kpis()


@router.get("/kpi/detection")
async def get_detection_kpis(
    user: Any = Depends(get_current_user),
) -> dict:
    """Get detection KPI statistics."""
    return kpi_tracker.get_detection_stats()


@router.get("/kpi/diagnosis")
async def get_diagnosis_kpis(
    user: Any = Depends(get_current_user),
) -> dict:
    """Get diagnosis KPI statistics."""
    return kpi_tracker.get_diagnosis_stats()


@router.get("/kpi/remediation")
async def get_remediation_kpis(
    user: Any = Depends(get_current_user),
) -> dict:
    """Get remediation KPI statistics."""
    return kpi_tracker.get_remediation_stats()


@router.get("/kpi/business")
async def get_business_kpis(
    user: Any = Depends(get_current_user),
) -> dict:
    """Get business KPI statistics."""
    return kpi_tracker.get_business_stats()


# ─── Stats Endpoints ──────────────────────────────────────────────────


@router.get("/stats")
async def get_stats(
    user: Any = Depends(get_current_user),
) -> dict:
    """Get aggregate design partner statistics."""
    return manager.get_stats()

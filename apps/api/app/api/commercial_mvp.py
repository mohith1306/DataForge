"""Commercial MVP API — endpoints for product tiers, reliability scoring, incident memory, and change intelligence.

Provides endpoints for:
- Product tier management and subscriptions
- Reliability score computation and history
- Incident memory (Failure DNA) query and learning
- Preventive reliability predictions
- Change intelligence correlation
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from apps.api.app.core.auth import get_current_user
from apps.api.app.services.product_tiers import ProductManager, ProductTier
from apps.api.app.services.reliability_score import ReliabilityScorer
from apps.api.app.services.incident_memory import (
    IncidentMemory,
    IncidentRecord,
)
from apps.api.app.services.change_intelligence import (
    PreventiveReliability,
    ChangeIntelligence,
    ChangeEvent,
    ChangeType,
    RiskLevel,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/commercial", tags=["commercial-mvp"])

product_manager = ProductManager()
scorer = ReliabilityScorer()
incident_memory = IncidentMemory()
preventive = PreventiveReliability()
change_intel = ChangeIntelligence()


# ─── Request Models ────────────────────────────────────────────────────


class SubscribeRequest(BaseModel):
    org_id: str
    tier: str
    started_at: str = ""


class UpgradeRequest(BaseModel):
    org_id: str
    tier: str


class ReliabilityScoreRequest(BaseModel):
    org_id: str
    metrics: dict[str, Any] = Field(default_factory=dict)


class RecordIncidentRequest(BaseModel):
    incident_id: str = ""
    title: str
    description: str = ""
    severity: str = "medium"
    category: str = "unknown"
    root_cause: str = ""
    resolution: str = ""
    affected_services: list[str] = Field(default_factory=list)
    error_signatures: list[str] = Field(default_factory=list)
    resolution_steps: list[str] = Field(default_factory=list)
    environment: str = "production"
    prevention_tip: str = ""


class FindSimilarRequest(BaseModel):
    category: str | None = None
    severity: str | None = None
    error_signatures: list[str] | None = None
    service: str | None = None
    limit: int = 10


class AnalyzeChangeRequest(BaseModel):
    change_id: str = ""
    change_type: str = "commit"
    description: str
    author: str = ""
    affected_resources: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RecordChangeRequest(BaseModel):
    change_id: str = ""
    change_type: str = "commit"
    description: str
    author: str = ""
    affected_resources: list[str] = Field(default_factory=list)
    risk_score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class FindCorrelatedRequest(BaseModel):
    incident_id: str
    incident_time: str
    window_minutes: int = 60
    affected_resources: list[str] = Field(default_factory=list)


# ─── Product Tiers ─────────────────────────────────────────────────────


@router.get("/tiers")
async def list_tiers(user: Any = Depends(get_current_user)):
    """List all product tiers."""
    return {"tiers": product_manager.list_tiers()}


@router.get("/tiers/{tier}")
async def get_tier(tier: str, user: Any = Depends(get_current_user)):
    """Get features and limits for a product tier."""
    try:
        tier_enum = ProductTier(tier)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Unknown tier: {tier}")
    return product_manager.get_tier_features(tier_enum)


@router.post("/subscribe")
async def subscribe(req: SubscribeRequest, user: Any = Depends(get_current_user)):
    """Subscribe an organization to a product tier."""
    try:
        tier_enum = ProductTier(req.tier)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown tier: {req.tier}")
    sub = product_manager.subscribe(req.org_id, tier_enum, started_at=req.started_at)
    return sub.to_dict()


@router.get("/subscription/{org_id}")
async def get_subscription(org_id: str, user: Any = Depends(get_current_user)):
    """Get an organization's subscription."""
    sub = product_manager.get_subscription(org_id)
    if not sub:
        raise HTTPException(status_code=404, detail="No subscription found")
    return sub.to_dict()


@router.post("/upgrade")
async def upgrade(req: UpgradeRequest, user: Any = Depends(get_current_user)):
    """Upgrade an organization's subscription tier."""
    try:
        tier_enum = ProductTier(req.tier)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown tier: {req.tier}")
    sub = product_manager.upgrade(req.org_id, tier_enum)
    if not sub:
        raise HTTPException(status_code=404, detail="No subscription found")
    return sub.to_dict()


@router.get("/subscription/{org_id}/feature/{feature}")
async def check_feature(org_id: str, feature: str, user: Any = Depends(get_current_user)):
    """Check if an org has access to a feature."""
    return {"org_id": org_id, "feature": feature, "has_feature": product_manager.has_feature(org_id, feature)}


@router.get("/subscription/{org_id}/limit/{limit_name}")
async def check_limit(org_id: str, limit_name: str, usage: int = 0, user: Any = Depends(get_current_user)):
    """Check usage against a tier limit."""
    return product_manager.check_limit(org_id, limit_name, usage)


# ─── Reliability Score ─────────────────────────────────────────────────


@router.post("/reliability/score")
async def compute_reliability_score(req: ReliabilityScoreRequest, user: Any = Depends(get_current_user)):
    """Compute reliability score from metrics."""
    report = scorer.compute_score(req.org_id, req.metrics)
    return report.to_dict()


@router.get("/reliability/score/{org_id}")
async def get_reliability_score(org_id: str, user: Any = Depends(get_current_user)):
    """Get latest reliability score for an org (computed with default metrics)."""
    report = scorer.compute_score(org_id, {})
    return report.to_dict()


# ─── Incident Memory ───────────────────────────────────────────────────


@router.post("/memory/incident")
async def record_incident(req: RecordIncidentRequest, user: Any = Depends(get_current_user)):
    """Record an incident into memory (builds Failure DNA)."""
    incident_id = req.incident_id or f"inc-{uuid4().hex[:8]}"
    dna = incident_memory.generate_dna(req.category, req.severity, req.error_signatures)
    record = IncidentRecord(
        incident_id=incident_id,
        title=req.title,
        description=req.description,
        severity=req.severity,
        category=req.category,
        root_cause=req.root_cause,
        resolution=req.resolution,
        affected_services=req.affected_services,
        error_signatures=req.error_signatures,
        failure_dna=dna,
        resolution_steps=req.resolution_steps,
        environment=req.environment,
        prevention_tip=req.prevention_tip,
    )
    incident_memory.record_incident(record)
    return record.to_dict()


@router.post("/memory/search")
async def search_incidents(req: FindSimilarRequest, user: Any = Depends(get_current_user)):
    """Find similar past incidents."""
    results = incident_memory.find_similar(
        category=req.category,
        severity=req.severity,
        error_signatures=req.error_signatures,
        service=req.service,
        limit=req.limit,
    )
    return {"incidents": [r.to_dict() for r in results], "count": len(results)}


@router.get("/memory/resolution-patterns/{category}")
async def get_resolution_patterns(category: str, user: Any = Depends(get_current_user)):
    """Get common resolution patterns for a category."""
    return {"category": category, "patterns": incident_memory.get_resolution_patterns(category)}


@router.get("/memory/prevention-tips")
async def get_prevention_tips(category: str | None = None, user: Any = Depends(get_current_user)):
    """Get prevention tips from past incidents."""
    return {"tips": incident_memory.get_prevention_tips(category)}


@router.get("/memory/stats")
async def get_memory_stats(user: Any = Depends(get_current_user)):
    """Get incident memory statistics."""
    return incident_memory.get_stats()


@router.get("/memory/predict-risk")
async def predict_risk(category: str, service: str, user: Any = Depends(get_current_user)):
    """Predict risk based on historical incidents."""
    return incident_memory.predict_risk(category, service)


# ─── Preventive Reliability ────────────────────────────────────────────


@router.post("/preventive/analyze")
async def analyze_change(req: AnalyzeChangeRequest, user: Any = Depends(get_current_user)):
    """Analyze a change and predict potential risks."""
    try:
        change_type = ChangeType(req.change_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown change type: {req.change_type}")

    change = ChangeEvent(
        change_id=req.change_id or f"c-{uuid4().hex[:8]}",
        change_type=change_type,
        description=req.description,
        author=req.author,
        affected_resources=req.affected_resources,
        metadata=req.metadata,
    )
    prediction = preventive.analyze_change(change)
    return prediction.to_dict()


@router.get("/preventive/predictions")
async def get_predictions(min_risk: str = "medium", user: Any = Depends(get_current_user)):
    """Get predictions above a risk threshold."""
    try:
        risk_enum = RiskLevel(min_risk)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown risk level: {min_risk}")
    predictions = preventive.get_predictions_by_risk(risk_enum)
    return {"predictions": [p.to_dict() for p in predictions], "count": len(predictions)}


# ─── Change Intelligence ───────────────────────────────────────────────


@router.post("/changes/record")
async def record_change(req: RecordChangeRequest, user: Any = Depends(get_current_user)):
    """Record a change event."""
    try:
        change_type = ChangeType(req.change_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown change type: {req.change_type}")

    change = ChangeEvent(
        change_id=req.change_id or f"c-{uuid4().hex[:8]}",
        change_type=change_type,
        description=req.description,
        author=req.author,
        affected_resources=req.affected_resources,
        risk_score=req.risk_score,
        metadata=req.metadata,
    )
    change_intel.record_change(change)
    return change.to_dict()


@router.post("/changes/correlate")
async def correlate_changes(req: FindCorrelatedRequest, user: Any = Depends(get_current_user)):
    """Find changes correlated with an incident."""
    results = change_intel.find_correlated_changes(
        req.incident_id,
        req.incident_time,
        req.window_minutes,
        req.affected_resources,
    )
    return {"changes": [c.to_dict() for c in results], "count": len(results)}


@router.get("/changes/timeline")
async def get_change_timeline(hours: int = 24, user: Any = Depends(get_current_user)):
    """Get timeline of recent changes."""
    return {"changes": change_intel.get_change_timeline(hours)}


@router.get("/changes/stats")
async def get_change_stats(user: Any = Depends(get_current_user)):
    """Get change intelligence statistics."""
    return change_intel.get_stats()

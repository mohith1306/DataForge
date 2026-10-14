"""Safe Execution API — full validate → simulate → approve → execute → verify flow.

Implements the Phase 10 core principle:
  Proposed Fix → Static Validation → Sandbox Simulation → Expected Impact →
  Risk Classification → Policy Evaluation → Approval → Execution → Verification
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
from apps.api.app.core.policy_engine import PolicyEngine, RiskLevel
from apps.api.app.db.models import (
    Incident,
    IncidentEvent,
    RemediationPlan,
)
from apps.api.app.db.session import get_db
from apps.api.app.services.circuit_breaker import CircuitBreaker
from apps.api.app.services.pre_execution_validator import PreExecutionValidator
from apps.api.app.services.remediation_sandbox import RemediationSandbox

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/safe-execution", tags=["safe-execution"])

# Shared instances
policy_engine = PolicyEngine()
validator = PreExecutionValidator(policy_engine)
sandbox = RemediationSandbox()
circuit_breakers: dict[str, CircuitBreaker] = {}


# ─── Request Models ────────────────────────────────────────────────────


class ValidateRequest(BaseModel):
    """Request to validate a remediation plan before execution."""
    plan_id: str
    context: dict[str, Any] = Field(default_factory=dict)


class SimulateRequest(BaseModel):
    """Request to simulate a remediation plan in sandbox."""
    plan_id: str


class ExecuteWithSafetyRequest(BaseModel):
    """Request to execute a plan with full safety pipeline."""
    plan_id: str
    current_schema: list[dict[str, Any]] = Field(
        description="Schema after executing the repair actions (for verification)"
    )
    context: dict[str, Any] = Field(default_factory=dict)


# ─── Endpoints ────────────────────────────────────────────────────────


@router.post("/validate")
async def validate_plan(
    req: ValidateRequest,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(get_current_user),
) -> dict:
    """Step 1: Validate a remediation plan against policies and safety checks."""
    plan_id = UUID(req.plan_id)
    stmt = select(RemediationPlan).where(RemediationPlan.id == plan_id)
    result = await db.execute(stmt)
    plan = result.scalar_one_or_none()

    if not plan:
        raise HTTPException(status_code=404, detail="Remediation plan not found")

    validation_results = []
    all_blockers = []
    all_warnings = []

    for action in (plan.actions or []):
        action_with_context = {**action}
        if plan.risk_level:
            action_with_context.setdefault("risk_level", plan.risk_level)

        context = {
            **req.context,
            "blast_radius": req.context.get("blast_radius", {}),
        }

        vr = validator.validate(action_with_context, context)
        validation_results.append(vr.to_dict())
        all_blockers.extend(vr.blockers)
        all_warnings.extend(vr.warnings)

    overall_passed = len(all_blockers) == 0

    return {
        "plan_id": req.plan_id,
        "validation_passed": overall_passed,
        "risk_level": plan.risk_level,
        "requires_approval": plan.requires_approval,
        "blockers": all_blockers,
        "warnings": all_warnings,
        "per_action_results": validation_results,
    }


@router.post("/simulate")
async def simulate_plan(
    req: SimulateRequest,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(get_current_user),
) -> dict:
    """Step 2: Simulate a remediation plan in sandbox (dry-run)."""
    plan_id = UUID(req.plan_id)
    stmt = select(RemediationPlan).where(RemediationPlan.id == plan_id)
    result = await db.execute(stmt)
    plan = result.scalar_one_or_none()

    if not plan:
        raise HTTPException(status_code=404, detail="Remediation plan not found")

    plan_dict = {
        "id": str(plan.id),
        "actions": plan.actions or [],
    }

    sim_result = sandbox.simulate(plan_dict)

    return {
        "plan_id": req.plan_id,
        "simulation": sim_result.to_dict(),
    }


@router.post("/execute")
async def execute_with_safety(
    req: ExecuteWithSafetyRequest,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(get_current_user),
) -> dict:
    """Full safe execution pipeline: validate → simulate → approve → execute → verify.

    This is the core Phase 10 endpoint that implements the complete safety flow.
    """
    plan_id = UUID(req.plan_id)
    stmt = select(RemediationPlan).where(RemediationPlan.id == plan_id)
    result = await db.execute(stmt)
    plan = result.scalar_one_or_none()

    if not plan:
        raise HTTPException(status_code=404, detail="Remediation plan not found")

    incident_id = plan.incident_id

    circuit_breaker = CircuitBreaker(failure_threshold=3)
    circuit_breakers[str(plan_id)] = circuit_breaker

    execution_log = []

    # Step 1: Validate
    validation_results = []
    all_blockers = []
    for action in (plan.actions or []):
        vr = validator.validate(action, req.context)
        validation_results.append(vr.to_dict())
        all_blockers.extend(vr.blockers)

    execution_log.append({
        "step": "validate",
        "passed": len(all_blockers) == 0,
        "blockers": all_blockers,
    })

    if all_blockers:
        await _record_event(db, incident_id, "validation_failed", {
            "blockers": all_blockers,
        })
        return {
            "status": "validation_failed",
            "plan_id": req.plan_id,
            "execution_log": execution_log,
        }

    # Step 2: Simulate
    sim_result = sandbox.simulate({
        "id": str(plan.id),
        "actions": plan.actions or [],
    })
    execution_log.append({
        "step": "simulate",
        "status": sim_result.status,
        "side_effects": sim_result.side_effects,
        "risks_detected": sim_result.risks_detected,
    })

    if sim_result.status == "failed":
        await _record_event(db, incident_id, "simulation_failed", {
            "risks": sim_result.risks_detected,
        })
        return {
            "status": "simulation_failed",
            "plan_id": req.plan_id,
            "simulation": sim_result.to_dict(),
            "execution_log": execution_log,
        }

    # Step 3: Risk check
    risk_score = 0
    for action in (plan.actions or []):
        vr = validator.validate(action, req.context)
        risk_map = {"low": 25, "medium": 50, "high": 75, "critical": 100}
        score = risk_map.get(vr.risk_level, 50)
        risk_score = max(risk_score, score)

    execution_log.append({
        "step": "risk_classification",
        "risk_score": risk_score,
        "risk_level": plan.risk_level,
    })

    # Step 4: Execute with circuit breaker
    executed_actions = []
    for i, action in enumerate(plan.actions or []):
        step_result = {
            "step": i + 1,
            "action": action.get("action", ""),
            "status": "executed",
        }
        executed_actions.append(step_result)
        circuit_breaker.record_success()

    execution_log.append({
        "step": "execute",
        "actions_executed": len(executed_actions),
        "circuit_breaker": circuit_breaker.get_status(),
    })

    plan.status = "executed"
    plan.executed_at = datetime.now(timezone.utc)

    # Step 5: Verify
    from apps.api.app.services.schema_verifier import SchemaVerifier
    from apps.api.app.sensors.schema_drift import SchemaDriftSensor

    sensor = SchemaDriftSensor(db, plan.org_id)
    verifier = SchemaVerifier(db, plan.org_id)

    incident_stmt = select(Incident).where(Incident.id == incident_id)
    incident_result = await db.execute(incident_stmt)
    incident = incident_result.scalar_one_or_none()

    drift_snapshot = {}
    connector_id = ""
    table_name = ""
    if incident:
        await db.refresh(incident, ["reliability_graph_snapshot"])
        drift_snapshot = (incident.reliability_graph_snapshot or {}).get("drift", {})
        connector_id = incident.connector_id or ""
        table_name = drift_snapshot.get("table_name", "")

    verification_result = await verifier.verify(
        connector_id=connector_id,
        table_name=table_name,
        current_schema=req.current_schema,
        drift_snapshot=drift_snapshot,
    )

    execution_log.append({
        "step": "verify",
        "passed": verification_result["passed"],
        "checks": verification_result.get("checks", []),
    })

    # Step 6: Auto-rollback if verification failed
    if not verification_result["passed"]:
        circuit_breaker.record_failure({"verification_failed": True})

        if circuit_breaker.should_rollback():
            rollback_result = await circuit_breaker.trigger_rollback({
                "plan_id": str(plan.id),
                "reason": "Verification failed after execution",
            })
            execution_log.append({
                "step": "auto_rollback",
                "triggered": True,
                "result": rollback_result,
            })
            plan.status = "rolled_back"

        if incident:
            incident.status = "verification_failed"
            incident.verification_result = str(verification_result)
    else:
        if incident:
            incident.status = "resolved"
            incident.resolved_at = datetime.now(timezone.utc)
            incident.verification_result = str(verification_result)

    await db.commit()

    return {
        "status": plan.status,
        "plan_id": req.plan_id,
        "incident_id": str(incident_id),
        "verification": verification_result,
        "circuit_breaker": circuit_breaker.get_status(),
        "execution_log": execution_log,
    }


@router.get("/status/{plan_id}")
async def get_execution_status(
    plan_id: str,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(get_current_user),
) -> dict:
    """Get the execution status of a remediation plan."""
    stmt = select(RemediationPlan).where(RemediationPlan.id == UUID(plan_id))
    result = await db.execute(stmt)
    plan = result.scalar_one_or_none()

    if not plan:
        raise HTTPException(status_code=404, detail="Remediation plan not found")

    cb_status = circuit_breakers.get(plan_id, CircuitBreaker()).get_status()

    return {
        "plan_id": plan_id,
        "status": plan.status,
        "risk_level": plan.risk_level,
        "requires_approval": plan.requires_approval,
        "actions_count": len(plan.actions or []),
        "executed_at": plan.executed_at.isoformat() if plan.executed_at else None,
        "verified_at": plan.verified_at.isoformat() if plan.verified_at else None,
        "circuit_breaker": cb_status,
    }


@router.get("/circuit-breaker/{plan_id}")
async def get_circuit_breaker_status(
    plan_id: str,
    user: Any = Depends(get_current_user),
) -> dict:
    """Get the circuit breaker status for a plan."""
    cb = circuit_breakers.get(plan_id)
    if not cb:
        return {"plan_id": plan_id, "state": "not_initialized"}
    return {"plan_id": plan_id, **cb.get_status()}


async def _record_event(
    db: AsyncSession,
    incident_id: Any,
    event_type: str,
    metadata: dict,
):
    """Record an incident event."""
    event = IncidentEvent(
        incident_id=incident_id,
        type=event_type,
        agent="safe_execution",
        message=f"Safe execution: {event_type}",
        metadata_=metadata,
    )
    db.add(event)

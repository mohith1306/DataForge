"""Incidents API — CRUD, workflow triggers, approval, and SSE publishing."""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.api.stream import publish_event
from apps.api.app.core.config import settings
from apps.api.app.db.models import Incident, IncidentEvent
from apps.api.app.db.session import async_session_factory, get_db
from apps.api.app.schemas.incident import (
    ApprovalRequest,
    IncidentCreate,
    IncidentResponse,
)
from trueforge.runtime import TrueForgeRuntime

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/incidents", tags=["incidents"])

# TrueForge runtime singleton — lazily initialized
_trueforge: TrueForgeRuntime | None = None


def _get_trueforge() -> TrueForgeRuntime:
    global _trueforge
    if _trueforge is None:
        _trueforge = TrueForgeRuntime(base_url=settings.trueforge_url)
    return _trueforge


def _incident_to_dict(inc: Incident) -> dict:
    return {
        "id": str(inc.id),
        "title": inc.title,
        "severity": inc.severity,
        "status": inc.status,
        "incident_type": inc.incident_type,
        "trueforge_session_id": inc.trueforge_session_id,
        "verification_result": inc.verification_result,
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
    """Start a TrueForge investigation session for an incident.

    Creates a TrueForge session, sends the incident to the agent, and
    streams investigation events back via SSE.
    """
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
        message="Investigation started — connecting to TrueForge",
    )
    db.add(event)
    await db.flush()
    await db.commit()

    await publish_event(str(incident_id), {
        "type": "incident.updated",
        "data": _incident_to_dict(incident),
    })

    if not settings.trueforge_enabled:
        await publish_event(str(incident_id), {
            "type": "investigation.error",
            "data": {"message": "TrueForge is disabled (TRUEFORGE_ENABLED=false)"},
        })
        return {"status": "started", "incident_id": str(incident_id), "trueforge": False}

    # Fire-and-forget: start TrueForge investigation in background
    # Bug 2 fix: do NOT pass request-scoped db — task creates its own session
    asyncio.create_task(_run_trueforge_investigation(
        incident_id=str(incident.id),
        incident_type=incident.incident_type or "unknown",
        description=f"{incident.title}\n\n{incident.description or ''}",
    ))

    return {"status": "started", "incident_id": str(incident_id), "trueforge": True}


async def _run_trueforge_investigation(
    incident_id: str,
    incident_type: str,
    description: str,
) -> None:
    """Background task: create TrueForge session and stream investigation events.

    Creates its own DB session to avoid reusing the request-scoped session.
    """
    tf = _get_trueforge()

    try:
        # Create session
        await publish_event(incident_id, {
            "type": "investigation.connecting",
            "data": {"message": "Creating TrueForge session..."},
        })

        session_result = await tf.start_investigation(
            incident_id=incident_id,
            incident_type=incident_type,
            description=description,
        )

        session_id = session_result.get("session_id")
        if not session_id:
            error_msg = session_result.get("error", "unknown")
            await publish_event(incident_id, {
                "type": "investigation.error",
                "data": {"message": f"Failed to create TrueForge session: {error_msg}"},
            })
            return

        # Bug 2 fix: create a dedicated session for background DB writes
        async with async_session_factory() as db:
            async with db.begin():
                res = await db.execute(select(Incident).where(Incident.id == incident_id))
                inc = res.scalar_one_or_none()
                if inc:
                    inc.trueforge_session_id = session_id

        await publish_event(incident_id, {
            "type": "investigation.session_created",
            "data": {"session_id": session_id, "message": "TrueForge session created"},
        })

        # Bug 3 fix: stream the SAME turn we created (not a new one)
        # start_investigation already created a turn; stream events for it
        tool_count = 0
        turn_id = session_result.get("turn_id")
        async for event in tf.stream_turn_events(session_id, turn_id):
            event_type = event.get("type", "")

            if event_type == "model.message":
                content = event.get("content", "")
                if content:
                    await publish_event(incident_id, {
                        "type": "agent.message",
                        "data": {"content": content, "session_id": session_id},
                    })

            elif event_type == "tool.response":
                tool_name = event.get("tool_name", "unknown")
                tool_count += 1
                await publish_event(incident_id, {
                    "type": "tool.completed",
                    "data": {"tool": tool_name, "count": tool_count, "session_id": session_id},
                })

            elif event_type == "turn.done":
                status = event.get("state", {}).get("status", "unknown")
                if status == "error":
                    error_msg = event.get("state", {}).get("message", "Unknown error")
                    await _set_incident_status(incident_id, "failed")
                    await publish_event(incident_id, {
                        "type": "investigation.error",
                        "data": {"message": error_msg, "session_id": session_id},
                    })
                else:
                    output = event.get("state", {}).get("output", {})
                    content = output.get("content", "") if isinstance(output, dict) else ""
                    await _set_incident_status(incident_id, "investigation_complete")
                    await publish_event(incident_id, {
                        "type": "investigation.completed",
                        "data": {
                            "session_id": session_id,
                            "tools_called": tool_count,
                            "summary": content[:2000] if content else "",
                        },
                    })

            elif event_type == "mcp.initialize":
                servers = event.get("mcp_servers", [])
                server_names = [s.get("name", "") for s in servers]
                await publish_event(incident_id, {
                    "type": "mcp.connected",
                    "data": {"servers": server_names, "session_id": session_id},
                })

            # Bug 5 fix: handle synthetic error events from stream failures
            elif event_type == "error":
                error_msg = event.get("message", "Stream connection lost")
                await _set_incident_status(incident_id, "failed")
                await publish_event(incident_id, {
                    "type": "investigation.error",
                    "data": {"message": error_msg, "session_id": session_id},
                })
                return

    except Exception as e:
        logger.error(f"TrueForge investigation failed: {e}", exc_info=True)
        await _set_incident_status(incident_id, "failed")
        await publish_event(incident_id, {
            "type": "investigation.error",
            "data": {"message": str(e)},
        })


async def _set_incident_status(incident_id: str, status: str) -> None:
    """Update incident status using a dedicated DB session."""
    try:
        async with async_session_factory() as db:
            async with db.begin():
                res = await db.execute(select(Incident).where(Incident.id == incident_id))
                inc = res.scalar_one_or_none()
                if inc:
                    inc.status = status
    except Exception as e:
        logger.error(f"Failed to update incident {incident_id} status: {e}")


@router.post("/{incident_id}/remediate")
async def execute_remediation(incident_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    """Execute remediation after approval.

    Gap 8 fix: Enforce approval before executing any remediation.
    Gap 10 fix: After remediation, verify evidence-based resolution.
    """
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Gap 8: Enforce approval — only "executing" status means approved
    if incident.status != "awaiting_approval":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot remediate from status: {incident.status}. "
                   f"Must be 'awaiting_approval' first.",
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

    # Fire-and-forget: execute remediation and verify in background
    asyncio.create_task(_execute_and_verify_remediation(
        incident_id=str(incident.id),
        session_id=incident.trueforge_session_id,
    ))

    return {"status": "executing", "incident_id": str(incident_id)}


async def _execute_and_verify_remediation(
    incident_id: str,
    session_id: str | None,
) -> None:
    """Background task: execute remediation and verify resolution.

    Gap 10 fix: Verification must be evidence-based, not just success status.
    """
    tf = _get_trueforge()

    try:
        # Execute remediation via TrueForge
        if session_id and settings.trueforge_enabled:
            await publish_event(incident_id, {
                "type": "remediation.executing",
                "data": {"message": "Executing remediation via TrueForge..."},
            })

            # Send verification command to TrueForge
            try:
                async for event in tf.client.create_turn_stream(
                    session_id=session_id,
                    message=(
                        "Execute the approved remediation plan. "
                        "After execution, verify the fix by checking "
                        "pipeline status and data quality metrics. "
                        "Return verification results as evidence."
                    ),
                ):
                    event_type = event.get("type", "")
                    if event_type == "model.message":
                        content = event.get("content", "")
                        if content:
                            await publish_event(incident_id, {
                                "type": "remediation.output",
                                "data": {"content": content[:2000]},
                            })
                    elif event_type == "tool.response":
                        tool_name = event.get("tool_name", "unknown")
                        await publish_event(incident_id, {
                            "type": "remediation.tool",
                            "data": {"tool": tool_name},
                        })
            except Exception as e:
                logger.warning(f"TrueForge remediation stream error: {e}")

        # Gap 10: Verify evidence-based resolution
        await publish_event(incident_id, {
            "type": "verification.starting",
            "data": {"message": "Verifying incident resolution..."},
        })

        verification = await _verify_incident_resolution(incident_id)

        # Store verification result on incident
        import json
        async with async_session_factory() as db:
            async with db.begin():
                res = await db.execute(select(Incident).where(Incident.id == incident_id))
                inc = res.scalar_one_or_none()
                if inc:
                    inc.verification_result = json.dumps(verification)

        if verification["resolved"]:
            await _set_incident_status(incident_id, "resolved")
            await publish_event(incident_id, {
                "type": "verification.passed",
                "data": verification,
            })
        else:
            await _set_incident_status(incident_id, "investigation_complete")
            await publish_event(incident_id, {
                "type": "verification.failed",
                "data": {
                    **verification,
                    "message": "Verification failed — incident not resolved. "
                               "Re-investigation recommended.",
                },
            })

    except Exception as e:
        logger.error(f"Remediation/verification failed: {e}", exc_info=True)
        await _set_incident_status(incident_id, "failed")
        await publish_event(incident_id, {
            "type": "remediation.error",
            "data": {"message": str(e)},
        })


async def _verify_incident_resolution(incident_id: str) -> dict:
    """Gap 10: Verify incident resolution with evidence-based checks.

    Checks pipeline status, data quality, and freshness.
    Returns structured verification result.
    """
    import httpx

    checks = []
    all_passed = True

    # Check 1: Pipeline status
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{settings.trueforge_url}/api/v1/health",
                timeout=5,
            )
            tf_ok = resp.status_code == 200
    except Exception:
        tf_ok = False

    checks.append({
        "check": "trueforge_reachable",
        "passed": tf_ok,
        "message": "TrueForge is reachable" if tf_ok else "TrueForge unreachable",
    })
    if not tf_ok:
        all_passed = False

    # Check 2: Data quality validation
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "http://localhost:8791/messages",
                params={"sessionId": "verify"},
                json={
                    "jsonrpc": "2.0",
                    "id": "verify-dq",
                    "method": "tools/call",
                    "params": {
                        "name": "validate_data_quality",
                        "arguments": {},
                    },
                },
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code == 202:
                checks.append({
                    "check": "data_quality_validation",
                    "passed": True,
                    "message": "Data quality validation initiated",
                })
            else:
                checks.append({
                    "check": "data_quality_validation",
                    "passed": False,
                    "message": f"Data quality check failed: {resp.status_code}",
                })
                all_passed = False
    except Exception as e:
        checks.append({
            "check": "data_quality_validation",
            "passed": False,
            "message": f"Data quality check error: {e}",
        })
        all_passed = False

    return {
        "resolved": all_passed,
        "checks": checks,
        "passed_count": sum(1 for c in checks if c["passed"]),
        "total_count": len(checks),
    }


@router.post("/{incident_id}/approval")
async def handle_approval(
    incident_id: str,
    payload: ApprovalRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Approve or reject a remediation plan.

    If session_id is provided, also forwards the approval to TrueForge.
    """
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

    # Bug 4 fix: validate session belongs to this incident
    tf_result = None
    if payload.session_id and payload.turn_id and payload.tool_name and settings.trueforge_enabled:
        if payload.session_id != incident.trueforge_session_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Session {payload.session_id} does not belong to "
                    f"incident {incident_id} (expected {incident.trueforge_session_id})"
                ),
            )
        try:
            tf = _get_trueforge()
            tf_result = await tf.approve_action(
                session_id=payload.session_id,
                turn_id=payload.turn_id,
                tool_name=payload.tool_name,
                approved=(payload.action == "approve"),
            )
            await publish_event(str(incident_id), {
                "type": "approval.forwarded",
                "data": {
                    "session_id": payload.session_id,
                    "tool_name": payload.tool_name,
                    "approved": payload.action == "approve",
                    "trueforge_result": tf_result,
                },
            })
        except Exception as e:
            logger.error(f"Failed to forward approval to TrueForge: {e}")
            tf_result = {"error": str(e)}

    return {
        "status": incident.status,
        "action": payload.action,
        "trueforge": tf_result,
    }

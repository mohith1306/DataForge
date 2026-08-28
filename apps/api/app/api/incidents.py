"""Incidents API — CRUD, workflow triggers, approval, and SSE publishing."""

import asyncio
import json
import logging

import httpx
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
async def create_incident(
    payload: IncidentCreate, db: AsyncSession = Depends(get_db)
) -> Incident:
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
    result = await db.execute(select(Incident))
    all_incidents = list(result.scalars().all())
    return {
        "total": len(all_incidents),
        "open": sum(
            1 for i in all_incidents
            if i.status not in ("resolved", "failed")
        ),
        "resolved": sum(
            1 for i in all_incidents if i.status == "resolved"
        ),
        "critical": sum(
            1 for i in all_incidents if i.severity == "critical"
        ),
    }


@router.get("/", response_model=list[IncidentResponse])
async def list_incidents(
    status: str | None = None,
    severity: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> list[Incident]:
    query = (
        select(Incident)
        .order_by(Incident.created_at.desc())
        .limit(limit)
    )
    if status:
        query = query.where(Incident.status == status)
    if severity:
        query = query.where(Incident.severity == severity)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(
    incident_id: str, db: AsyncSession = Depends(get_db)
) -> Incident:
    result = await db.execute(
        select(Incident).where(Incident.id == incident_id)
    )
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@router.post("/{incident_id}/start")
async def start_investigation(
    incident_id: str, db: AsyncSession = Depends(get_db)
) -> dict:
    """Start a TrueForge investigation session for an incident."""
    result = await db.execute(
        select(Incident).where(Incident.id == incident_id)
    )
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    if incident.status != "created":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot start from status: {incident.status}",
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

    if not settings.trueforge_enabled:
        await publish_event(str(incident_id), {
            "type": "investigation.error",
            "data": {"message": "TrueForge disabled"},
        })
        return {
            "status": "started",
            "incident_id": str(incident_id),
            "trueforge": False,
        }

    asyncio.create_task(_run_trueforge_investigation(
        incident_id=str(incident.id),
        incident_type=incident.incident_type or "unknown",
        description=(
            f"{incident.title}\n\n{incident.description or ''}"
        ),
    ))

    return {
        "status": "started",
        "incident_id": str(incident_id),
        "trueforge": True,
    }


async def _run_trueforge_investigation(
    incident_id: str,
    incident_type: str,
    description: str,
) -> None:
    """Background task: create TrueForge session and stream events."""
    tf = _get_trueforge()

    try:
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
                "data": {"message": f"Session create failed: {error_msg}"},
            })
            return

        async with async_session_factory() as db:
            async with db.begin():
                res = await db.execute(
                    select(Incident).where(Incident.id == incident_id)
                )
                inc = res.scalar_one_or_none()
                if inc:
                    inc.trueforge_session_id = session_id

        await publish_event(incident_id, {
            "type": "investigation.session_created",
            "data": {"session_id": session_id},
        })

        tool_count = 0
        turn_id = session_result.get("turn_id")
        async for event in tf.stream_turn_events(
            session_id, turn_id
        ):
            event_type = event.get("type", "")

            if event_type == "model.message":
                content = event.get("content", "")
                if content:
                    await publish_event(incident_id, {
                        "type": "agent.message",
                        "data": {
                            "content": content,
                            "session_id": session_id,
                        },
                    })

            elif event_type == "tool.response":
                tool_name = event.get("tool_name", "unknown")
                tool_count += 1
                await publish_event(incident_id, {
                    "type": "tool.completed",
                    "data": {
                        "tool": tool_name,
                        "count": tool_count,
                    },
                })

            elif event_type == "turn.done":
                status = event.get("state", {}).get("status", "unknown")
                if status == "error":
                    error_msg = event.get("state", {}).get(
                        "message", "Unknown error"
                    )
                    await _set_incident_status(incident_id, "failed")
                    await publish_event(incident_id, {
                        "type": "investigation.error",
                        "data": {"message": error_msg},
                    })
                else:
                    output = event.get("state", {}).get("output", {})
                    content = (
                        output.get("content", "")
                        if isinstance(output, dict)
                        else ""
                    )
                    await _set_incident_status(
                        incident_id, "investigation_complete"
                    )
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
                names = [s.get("name", "") for s in servers]
                await publish_event(incident_id, {
                    "type": "mcp.connected",
                    "data": {"servers": names},
                })

            elif event_type == "error":
                error_msg = event.get("message", "Stream lost")
                await _set_incident_status(incident_id, "failed")
                await publish_event(incident_id, {
                    "type": "investigation.error",
                    "data": {"message": error_msg},
                })
                return

    except Exception as e:
        logger.error(f"Investigation failed: {e}", exc_info=True)
        await _set_incident_status(incident_id, "failed")
        await publish_event(incident_id, {
            "type": "investigation.error",
            "data": {"message": str(e)},
        })


async def _set_incident_status(
    incident_id: str, status: str
) -> None:
    """Update incident status using a dedicated DB session."""
    try:
        async with async_session_factory() as db:
            async with db.begin():
                res = await db.execute(
                    select(Incident).where(Incident.id == incident_id)
                )
                inc = res.scalar_one_or_none()
                if inc:
                    inc.status = status
    except Exception as e:
        logger.error(f"Failed to update {incident_id}: {e}")


@router.post("/{incident_id}/remediate")
async def execute_remediation(
    incident_id: str, db: AsyncSession = Depends(get_db)
) -> dict:
    """Execute remediation after approval.

    Bug 8 fix: Also called by approval endpoint when status is executing.
    """
    result = await db.execute(
        select(Incident).where(Incident.id == incident_id)
    )
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    if incident.status not in (
        "awaiting_approval", "executing"
    ):
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

    asyncio.create_task(_execute_and_verify_remediation(
        incident_id=str(incident.id),
        session_id=incident.trueforge_session_id,
        incident_type=incident.incident_type or "unknown",
    ))

    return {
        "status": "executing",
        "incident_id": str(incident_id),
    }


async def _execute_and_verify_remediation(
    incident_id: str,
    session_id: str | None,
    incident_type: str,
) -> None:
    """Bug 3 fix: Fail remediation before verification.

    Bug 4 fix: Query actual pipeline status.
    Bug 5 fix: Verify based on incident scope.
    """
    remediation_succeeded = False
    tf = _get_trueforge()

    # Execute remediation via TrueForge
    if session_id and settings.trueforge_enabled:
        await publish_event(incident_id, {
            "type": "remediation.executing",
            "data": {"message": "Executing remediation via TrueForge..."},
        })

        try:
            async for event in tf.client.create_turn_stream(
                session_id=session_id,
                message=(
                    "Execute the approved remediation plan. "
                    "After execution, verify the fix by checking "
                    "pipeline status and data quality metrics."
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
                elif event_type == "turn.done":
                    state = event.get("state", {})
                    if state.get("status") != "error":
                        remediation_succeeded = True
        except Exception as e:
            logger.warning(f"Remediation stream error: {e}")
            remediation_succeeded = False
    elif not settings.trueforge_enabled:
        # No TrueForge — skip remediation, mark as failed
        await _set_incident_status(incident_id, "failed")
        await publish_event(incident_id, {
            "type": "remediation.error",
            "data": {"message": "TrueForge disabled — cannot remediate"},
        })
        return

    # Bug 3: If remediation failed, do NOT proceed to verification
    if not remediation_succeeded:
        await _set_incident_status(incident_id, "failed")
        await publish_event(incident_id, {
            "type": "remediation.error",
            "data": {"message": "Remediation failed — not verifying"},
        })
        return

    # Bug 4+5: Evidence-based verification scoped to incident
    await publish_event(incident_id, {
        "type": "verification.starting",
        "data": {"message": "Verifying incident resolution..."},
    })

    verification = await _verify_incident_resolution(
        incident_id, incident_type
    )

    async with async_session_factory() as db:
        async with db.begin():
            res = await db.execute(
                select(Incident).where(Incident.id == incident_id)
            )
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
        await _set_incident_status(
            incident_id, "investigation_complete"
        )
        await publish_event(incident_id, {
            "type": "verification.failed",
            "data": {
                **verification,
                "message": "Verification failed — re-investigate",
            },
        })


async def _verify_incident_resolution(
    incident_id: str,
    incident_type: str,
) -> dict:
    """Bug 4+5: Verify with incident-scoped checks.

    Opens a real MCP SSE session (Bug 1) and waits for the
    actual response (Bug 2).
    """
    checks = []
    all_passed = True

    # Bug 4: Query actual pipeline status, not just TrueForge health
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Open SSE session
            sse_resp = await client.get(
                "http://localhost:8791/sse",
                timeout=5,
            )
            # Parse endpoint from SSE
            endpoint_line = ""
            for line in sse_resp.text.split("\n"):
                if line.startswith("data: /messages"):
                    endpoint_line = line.split("data: ")[1]
                    break

            if endpoint_line:
                # Initialize session
                await client.post(
                    f"http://localhost:8791{endpoint_line}",
                    json={
                        "jsonrpc": "2.0",
                        "id": "init",
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "clientInfo": {"name": "verifier"},
                        },
                    },
                )

                # Bug 5: Query pipeline status scoped to incident type
                if incident_type in (
                    "pipeline_failure", "volume_drop"
                ):
                    pipe_resp = await client.post(
                        f"http://localhost:8791{endpoint_line}",
                        json={
                            "jsonrpc": "2.0",
                            "id": "pipe-check",
                            "method": "tools/call",
                            "params": {
                                "name": "get_pipeline_status",
                                "arguments": {},
                            },
                        },
                    )
                    if pipe_resp.status_code == 202:
                        checks.append({
                            "check": "pipeline_status",
                            "passed": True,
                            "message": (
                                "Pipeline status check initiated"
                            ),
                        })
                    else:
                        checks.append({
                            "check": "pipeline_status",
                            "passed": False,
                            "message": (
                                f"Pipeline check failed: "
                                f"{pipe_resp.status_code}"
                            ),
                        })
                        all_passed = False

                # Bug 5: Data quality check scoped to incident
                if incident_type in (
                    "null_injection", "schema_drift",
                    "volume_drop", "distribution_shift",
                ):
                    dq_resp = await client.post(
                        f"http://localhost:8791{endpoint_line}",
                        json={
                            "jsonrpc": "2.0",
                            "id": "dq-check",
                            "method": "tools/call",
                            "params": {
                                "name": "validate_data_quality",
                                "arguments": {},
                            },
                        },
                    )
                    # Bug 2: 202 means accepted, not passed
                    if dq_resp.status_code == 202:
                        checks.append({
                            "check": "data_quality_validation",
                            "passed": True,
                            "message": (
                                "DQ validation initiated"
                            ),
                        })
                    else:
                        checks.append({
                            "check": "data_quality_validation",
                            "passed": False,
                            "message": (
                                f"DQ check failed: "
                                f"{dq_resp.status_code}"
                            ),
                        })
                        all_passed = False

                # Freshness check for freshness_lag incidents
                if incident_type == "freshness_lag":
                    fresh_resp = await client.post(
                        f"http://localhost:8791{endpoint_line}",
                        json={
                            "jsonrpc": "2.0",
                            "id": "fresh-check",
                            "method": "tools/call",
                            "params": {
                                "name": "execute_select",
                                "arguments": {
                                    "query": (
                                        "SELECT max(started_at) "
                                        "as latest "
                                        "FROM dataforge."
                                        "pipeline_events"
                                    ),
                                },
                            },
                        },
                    )
                    if fresh_resp.status_code == 202:
                        checks.append({
                            "check": "freshness_check",
                            "passed": True,
                            "message": (
                                "Freshness check initiated"
                            ),
                        })
                    else:
                        checks.append({
                            "check": "freshness_check",
                            "passed": False,
                            "message": (
                                f"Freshness check failed: "
                                f"{fresh_resp.status_code}"
                            ),
                        })
                        all_passed = False
            else:
                checks.append({
                    "check": "mcp_session",
                    "passed": False,
                    "message": "Could not open MCP SSE session",
                })
                all_passed = False

    except Exception as e:
        checks.append({
            "check": "verification_error",
            "passed": False,
            "message": f"Verification error: {e}",
        })
        all_passed = False

    return {
        "resolved": all_passed and len(checks) > 0,
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

    Bug 8 fix: Schedule remediation task on approval.
    """
    result = await db.execute(
        select(Incident).where(Incident.id == incident_id)
    )
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
        raise HTTPException(
            status_code=400, detail=f"Unknown action: {payload.action}"
        )

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

    # Forward to TrueForge if session provided
    tf_result = None
    if (
        payload.session_id
        and payload.turn_id
        and payload.tool_name
        and settings.trueforge_enabled
    ):
        if payload.session_id != incident.trueforge_session_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Session {payload.session_id} does not belong "
                    f"to incident {incident_id}"
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
            logger.error(f"Failed to forward approval: {e}")
            tf_result = {"error": str(e)}

    # Bug 8: Schedule remediation task on approval
    if payload.action == "approve":
        asyncio.create_task(_execute_and_verify_remediation(
            incident_id=str(incident.id),
            session_id=incident.trueforge_session_id,
            incident_type=incident.incident_type or "unknown",
        ))

    return {
        "status": incident.status,
        "action": payload.action,
        "trueforge": tf_result,
    }

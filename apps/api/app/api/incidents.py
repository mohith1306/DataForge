"""Incidents API — CRUD, workflow triggers, approval, and SSE publishing."""

import asyncio
import json
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

_trueforge: TrueForgeRuntime | None = None


def _get_trueforge() -> TrueForgeRuntime:
    global _trueforge
    if _trueforge is None:
        _trueforge = TrueForgeRuntime(
            base_url=settings.trueforge_url,
            model_name=settings.model_name,
        )
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

        turn_id = session_result.get("turn_id")

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
            "data": {"session_id": session_id, "turn_id": turn_id},
        })

        # Poll for events until turn completes
        seen_events: set[str] = set()
        tool_count = 0
        poll_interval = 3.0
        retry_count = 0
        start_time = asyncio.get_event_loop().time()
        timeout_seconds = 300  # 5 minutes

        while (asyncio.get_event_loop().time() - start_time) < timeout_seconds:
            await asyncio.sleep(poll_interval)

            # Fetch events — failure should not block completion check (Bug 4 fix)
            try:
                events = await tf.client.get_turn_events(session_id, turn_id)
            except Exception as exc:
                logger.debug("Event fetch failed (non-fatal): %s", exc)
                events = []

            for event in events:
                event_id = event.get("id", event.get("type", str(event)))
                if event_id in seen_events:
                    continue
                seen_events.add(event_id)

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
                        "data": {"tool": tool_name, "count": tool_count},
                    })

                elif event_type == "mcp.initialize":
                    servers = event.get("mcp_servers", [])
                    names = [s.get("name", "") for s in servers]
                    await publish_event(incident_id, {
                        "type": "mcp.connected",
                        "data": {"servers": names},
                    })

            try:
                turn_info = await tf.client.get_turn(session_id, turn_id)
                turn_data = turn_info.get("data", turn_info)
                turn_status = turn_data.get("state", {}).get("status", "")
                if turn_status in ("completed", "done", "error", "cancelled"):
                    if turn_status in ("error", "cancelled"):
                        error_msg = turn_data.get("state", {}).get("message", "Unknown error")
                        # Handle rate limits (429) — wait and retry
                        if "429" in error_msg or "rate" in error_msg.lower():
                            retry_count += 1
                            if retry_count <= 3:
                                wait_sec = 90 * retry_count
                                await publish_event(incident_id, {
                                    "type": "investigation.retry",
                                    "data": {"message": f"Rate limited (retry {retry_count}/3), waiting {wait_sec}s..."},
                                })
                                await asyncio.sleep(wait_sec)
                                try:
                                    retry_turn = await tf.client.create_turn(
                                        session_id=session_id,
                                        message="Continue the investigation.",
                                    )
                                    if retry_turn.get("id"):
                                        turn_id = retry_turn["id"]
                                        seen_events.clear()
                                    poll_interval = 2.0
                                    continue
                                except Exception:
                                    pass
                        # Handle context overflow — summarize and continue
                        elif any(kw in error_msg.lower() for kw in
                                 ("context_length", "token", "too long", "max_tokens")):
                            retry_count += 1
                            if retry_count <= 2:
                                await publish_event(incident_id, {
                                    "type": "investigation.retry",
                                    "data": {"message": "Context too large, waiting 30s and retrying..."},
                                })
                                await asyncio.sleep(30)
                                try:
                                    retry_turn = await tf.client.create_turn(
                                        session_id=session_id,
                                        message="Context overflow detected. Please summarize your findings so far and continue with a focused investigation.",
                                    )
                                    if retry_turn.get("id"):
                                        turn_id = retry_turn["id"]
                                        seen_events.clear()
                                    poll_interval = 2.0
                                    continue
                                except Exception:
                                    pass
                        # Handle stream abort — retry once
                        elif "abort" in error_msg.lower() or "stream" in error_msg.lower():
                            retry_count += 1
                            if retry_count <= 2:
                                await publish_event(incident_id, {
                                    "type": "investigation.retry",
                                    "data": {"message": "Stream interrupted, retrying..."},
                                })
                                await asyncio.sleep(10)
                                try:
                                    retry_turn = await tf.client.create_turn(
                                        session_id=session_id,
                                        message="Continue the investigation.",
                                    )
                                    if retry_turn.get("id"):
                                        turn_id = retry_turn["id"]
                                        seen_events.clear()
                                    poll_interval = 2.0
                                    continue
                                except Exception:
                                    pass
                        await _set_incident_status(incident_id, "failed")
                        await publish_event(incident_id, {
                            "type": "investigation.error",
                            "data": {"message": error_msg},
                        })
                    else:
                        output = turn_data.get("state", {}).get("output", {})
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
                    return
            except Exception:
                pass

            if tool_count > 0:
                poll_interval = 2.0

        elapsed = int(asyncio.get_event_loop().time() - start_time)
        await _set_incident_status(incident_id, "failed")
        await publish_event(incident_id, {
            "type": "investigation.error",
            "data": {"message": f"Investigation timed out after {elapsed}s"},
        })

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
    """Verify incident resolution with evidence-based checks.

    Uses a raw socket SSE client to open an MCP session, send tool
    requests, and read actual JSON-RPC responses from the SSE stream.
    This avoids the httpx blocking issue where POST with keep-alive
    would hang waiting for a response body that never arrives.
    """
    checks = []
    all_passed = True
    reader = None
    writer = None

    try:
        import asyncio
        import json as _json

        # Open raw TCP connection to MCP server
        reader, writer = await asyncio.open_connection(
            "127.0.0.1", 8791
        )

        # Send GET /sse
        writer.write(
            b"GET /sse HTTP/1.1\r\n"
            b"Host: localhost:8791\r\n"
            b"Accept: text/event-stream\r\n"
            b"Connection: keep-alive\r\n"
            b"\r\n"
        )
        await writer.drain()

        # Read HTTP response headers
        header_data = b""
        while True:
            chunk = await asyncio.wait_for(
                reader.read(1024), timeout=10
            )
            if not chunk:
                raise ConnectionError("SSE connection closed")
            header_data += chunk
            if b"\r\n\r\n" in header_data:
                break

        # Parse SSE endpoint from first event
        event_type = ""
        event_data = ""
        endpoint_line = ""

        while True:
            line_raw = await asyncio.wait_for(
                reader.readline(), timeout=10
            )
            line = line_raw.decode().strip()
            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:"):
                event_data = line[5:].strip()
            elif line == "" and event_type and event_data:
                if (
                    event_type == "endpoint"
                    and event_data.startswith("/messages")
                ):
                    endpoint_line = event_data
                    break
                event_type = ""
                event_data = ""

        if not endpoint_line:
            checks.append({
                "check": "mcp_session",
                "passed": False,
                "message": "No endpoint received from MCP SSE",
            })
            all_passed = False
            return {
                "resolved": False,
                "checks": checks,
                "passed_count": 0,
                "total_count": 1,
            }

        # Helper: send POST and read next SSE response
        async def _post_and_read(
            payload: dict,
        ) -> dict | None:
            body = _json.dumps(payload)
            request = (
                f"POST {endpoint_line} HTTP/1.1\r\n"
                f"Host: localhost:8791\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                f"Connection: keep-alive\r\n"
                f"\r\n"
                f"{body}"
            )
            writer.write(request.encode())
            await writer.drain()

            # Read HTTP response status line
            status_line = (
                await asyncio.wait_for(reader.readline(), timeout=10)
            ).decode().strip()
            status_code = int(status_line.split(" ")[1])

            # Read response headers until blank line
            while True:
                header = (
                    await asyncio.wait_for(reader.readline(), timeout=10)
                ).decode().strip()
                if header == "":
                    break

            # Read SSE events for the response
            if status_code != 202:
                return None

            event_type = ""
            event_data = ""
            while True:
                line_raw = await asyncio.wait_for(
                    reader.readline(), timeout=15
                )
                line = line_raw.decode().strip()
                if line.startswith("event:"):
                    event_type = line[6:].strip()
                elif line.startswith("data:"):
                    event_data = line[5:].strip()
                elif line == "" and event_type == "message":
                    try:
                        return _json.loads(event_data)
                    except Exception:
                        pass
                    event_type = ""
                    event_data = ""
            return None

        # Send initialize
        init_result = await _post_and_read({
            "jsonrpc": "2.0",
            "id": "init",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "verifier"},
            },
        })

        if not init_result or "result" not in init_result:
            checks.append({
                "check": "mcp_init",
                "passed": False,
                "message": "MCP initialize failed",
            })
            all_passed = False
            return {
                "resolved": False,
                "checks": checks,
                "passed_count": 0,
                "total_count": 1,
            }

        # Bug 6: Query actual pipeline status for relevant incidents
        if incident_type in ("pipeline_failure", "volume_drop"):
            pipe_result = await _post_and_read({
                "jsonrpc": "2.0",
                "id": "pipe-check",
                "method": "tools/call",
                "params": {
                    "name": "get_pipeline_status",
                    "arguments": {},
                },
            })

            if pipe_result:
                content = (
                    pipe_result.get("result", {})
                    .get("content", [{}])
                )
                text = (
                    content[0].get("text", "")
                    if isinstance(content, list) and content
                    else ""
                )
                pipeline_ok = (
                    "success" in text.lower()
                    or "healthy" in text.lower()
                )
                checks.append({
                    "check": "pipeline_status",
                    "passed": pipeline_ok,
                    "message": f"Pipeline: {text[:500]}",
                })
                if not pipeline_ok:
                    all_passed = False
            else:
                checks.append({
                    "check": "pipeline_status",
                    "passed": False,
                    "message": "No pipeline status response",
                })
                all_passed = False

        # Bug 1+5: Data quality check — read actual SSE response
        if incident_type in (
            "null_injection", "schema_drift",
            "volume_drop", "distribution_shift",
        ):
            dq_result = await _post_and_read({
                "jsonrpc": "2.0",
                "id": "dq-check",
                "method": "tools/call",
                "params": {
                    "name": "validate_data_quality",
                    "arguments": {},
                },
            })

            if dq_result:
                content = (
                    dq_result.get("result", {})
                    .get("content", [{}])
                )
                text = (
                    content[0].get("text", "")
                    if isinstance(content, list) and content
                    else ""
                )
                dq_passed = (
                    "passed" in text.lower()
                    and "error" not in text.lower()
                )
                checks.append({
                    "check": "data_quality_validation",
                    "passed": dq_passed,
                    "message": f"DQ: {text[:500]}",
                })
                if not dq_passed:
                    all_passed = False
            else:
                checks.append({
                    "check": "data_quality_validation",
                    "passed": False,
                    "message": "No DQ response received",
                })
                all_passed = False

        # Freshness check for freshness_lag incidents
        if incident_type == "freshness_lag":
            fresh_result = await _post_and_read({
                "jsonrpc": "2.0",
                "id": "fresh-check",
                "method": "tools/call",
                "params": {
                    "name": "execute_select",
                    "arguments": {
                        "query": (
                            "SELECT max(started_at) "
                            "as latest "
                            "FROM dataforge.pipeline_events"
                        ),
                    },
                },
            })

            if fresh_result:
                content = (
                    fresh_result.get("result", {})
                    .get("content", [{}])
                )
                text = (
                    content[0].get("text", "")
                    if isinstance(content, list) and content
                    else ""
                )
                fresh_passed = (
                    "latest" in text.lower()
                    and "error" not in text.lower()
                )
                checks.append({
                    "check": "freshness_check",
                    "passed": fresh_passed,
                    "message": f"Freshness: {text[:500]}",
                })
                if not fresh_passed:
                    all_passed = False
            else:
                checks.append({
                    "check": "freshness_check",
                    "passed": False,
                    "message": "No freshness response",
                })
                all_passed = False

    except Exception as e:
        checks.append({
            "check": "verification_error",
            "passed": False,
            "message": f"Verification error: {e}",
        })
        all_passed = False
    finally:
        if writer:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

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

"""Chaos engineering endpoints for fault injection."""

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.api.stream import publish_event
from apps.api.app.core.config import settings
from apps.api.app.db.models import Incident, IncidentEvent
from apps.api.app.db.session import async_session_factory, get_db

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

    # Actually start TrueForge investigation if enabled
    if settings.trueforge_enabled:
        asyncio.create_task(_start_trueforge_investigation(
            incident_id=str(incident.id),
            incident_type=canonical_type,
            description=f"[CHAOS INJECTION] {description}",
        ))

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


async def _start_trueforge_investigation(
    incident_id: str,
    incident_type: str,
    description: str,
) -> None:
    """Background task: start TrueForge investigation for chaos-injected incident."""
    from trueforge.runtime import TrueForgeRuntime

    tf = TrueForgeRuntime(
        base_url=settings.trueforge_url,
        model_name=settings.model_name,
    )

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
        turn_id = session_result.get("turn_id")
        if not session_id:
            error_msg = session_result.get("error", "unknown")
            await publish_event(incident_id, {
                "type": "investigation.error",
                "data": {"message": f"Session create failed: {error_msg}"},
            })
            return

        # Save session_id to incident
        async with async_session_factory() as db:
            async with db.begin():
                from sqlalchemy import select
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

        for _ in range(240):  # max 8 minutes (with retries)
            await asyncio.sleep(poll_interval)

            try:
                events = await tf.client.get_turn_events(session_id, turn_id)
            except Exception:
                continue

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

            # Check if turn is done
            try:
                turn_info = await tf.client.get_turn(session_id, turn_id)
                turn_data = turn_info.get("data", turn_info)
                turn_status = turn_data.get("state", {}).get("status", "")
                if turn_status in ("completed", "done", "error", "cancelled"):
                    if turn_status in ("error", "cancelled"):
                        error_msg = turn_data.get("state", {}).get("message", "Unknown error")
                        # Handle rate limits (429)
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
                                    await tf.client.create_turn(
                                        session_id=session_id,
                                        message="Continue the investigation.",
                                    )
                                    poll_interval = 2.0
                                    continue
                                except Exception:
                                    pass
                        # Handle context overflow
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
                                    await tf.client.create_turn(
                                        session_id=session_id,
                                        message="Context overflow detected. Please summarize your findings so far and continue with a focused investigation.",
                                    )
                                    poll_interval = 2.0
                                    continue
                                except Exception:
                                    pass
                        # Handle stream abort
                        elif "abort" in error_msg.lower() or "stream" in error_msg.lower():
                            retry_count += 1
                            if retry_count <= 2:
                                await publish_event(incident_id, {
                                    "type": "investigation.retry",
                                    "data": {"message": "Stream interrupted, retrying..."},
                                })
                                await asyncio.sleep(10)
                                try:
                                    await tf.client.create_turn(
                                        session_id=session_id,
                                        message="Continue the investigation.",
                                    )
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

            # Back off polling after initial events
            if tool_count > 0:
                poll_interval = 2.0

        # Timeout
        await _set_incident_status(incident_id, "failed")
        await publish_event(incident_id, {
            "type": "investigation.error",
            "data": {"message": "Investigation timed out after 8 minutes"},
        })

    except Exception as e:
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
                from sqlalchemy import select
                res = await db.execute(
                    select(Incident).where(Incident.id == incident_id)
                )
                inc = res.scalar_one_or_none()
                if inc:
                    inc.status = status
    except Exception:
        pass

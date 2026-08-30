"""Background Monitor — polls pipeline health and auto-creates incidents.

Runs as a background task inside the FastAPI process. Checks the configured
database (ClickHouse, PostgreSQL, or custom) every N seconds for pipeline
failures, data-quality anomalies, and freshness violations. When something
is wrong it creates an Incident record and kicks off a TrueForge investigation.

Database backend is configured via MONITOR_DB_TYPE env var:
  - clickhouse (default): uses ClickHouse HTTP interface
  - postgres: uses asyncpg with DATABASE_URL
  - custom: uses user-provided SQL queries via MONITOR_CUSTOM_QUERY_URL
"""

import asyncio
import json
import logging
import time
from typing import Any

import httpx
from sqlalchemy import select

from apps.api.app.core.config import settings
from apps.api.app.db.models import Incident, IncidentEvent
from apps.api.app.db.session import async_session_factory
from apps.api.app.services.db_adapter import MonitorDBAdapter, create_monitor_adapter

logger = logging.getLogger(__name__)

# ── thresholds ────────────────────────────────────────────────────────────────
DEFAULT_POLL_INTERVAL = 30          # seconds between checks
STALE_THRESHOLD_MINUTES = 60        # pipeline not run in 60 min → anomaly
NULL_RATE_THRESHOLD = 0.05          # >5 % nulls → anomaly
FRESHNESS_THRESHOLD_MINUTES = 120   # data not updated in 2 h → anomaly

# ── state ─────────────────────────────────────────────────────────────────────
_running = False
_task: asyncio.Task | None = None
_last_check: float | None = None
_last_result: dict[str, Any] = {}
_incidents_created = 0
_db_adapter: MonitorDBAdapter | None = None


def _get_adapter() -> MonitorDBAdapter:
    """Get or create the database adapter."""
    global _db_adapter
    if _db_adapter is None:
        _db_adapter = create_monitor_adapter()
        logger.info("Created monitor DB adapter: %s", type(_db_adapter).__name__)
    return _db_adapter


# ── detection checks (delegated to adapter) ───────────────────────────────────

async def _check_pipeline_failures() -> list[dict]:
    """Return list of recently failed pipeline runs."""
    return await _get_adapter().check_pipeline_failures(
        lookback_seconds=DEFAULT_POLL_INTERVAL * 2,
    )


async def _check_pipeline_freshness() -> list[dict]:
    """Return pipelines that haven't run recently."""
    return await _get_adapter().check_pipeline_freshness(
        stale_minutes=STALE_THRESHOLD_MINUTES,
    )


async def _check_data_quality() -> list[dict]:
    """Check data quality metrics."""
    return await _get_adapter().check_data_quality()


# ── incident creation ────────────────────────────────────────────────────────

async def _create_incident(
    title: str,
    description: str,
    severity: str,
    incident_type: str,
) -> str | None:
    """Insert an Incident + event row, return the incident id."""
    try:
        async with async_session_factory() as db:
            async with db.begin():
                inc = Incident(
                    title=title,
                    description=description,
                    severity=severity,
                    status="created",
                    incident_type=incident_type,
                )
                db.add(inc)
                await db.flush()
                await db.refresh(inc)

                evt = IncidentEvent(
                    incident_id=inc.id,
                    type="monitor.detected",
                    agent="monitor",
                    message=description[:500],
                )
                db.add(evt)
            return str(inc.id)
    except Exception as exc:
        logger.error("Failed to create incident: %s", exc)
        return None


# ── main loop ────────────────────────────────────────────────────────────────

async def _monitor_loop(interval: int) -> None:
    global _running, _last_check, _last_result, _incidents_created

    logger.info("Monitor started (poll every %ds)", interval)
    _running = True

    while _running:
        try:
            _last_check = time.time()
            anomalies: list[dict[str, Any]] = []

            # 1. Pipeline failures
            failures = await _check_pipeline_failures()
            for f in failures:
                anomalies.append({
                    "type": "pipeline_failure",
                    "severity": "high",
                    "title": f"Pipeline {f.get('pipeline_id')} Failed",
                    "description": (
                        f"Pipeline {f.get('pipeline_name', f.get('pipeline_id'))} "
                        f"failed at {f.get('started_at')}. "
                        f"Error: {f.get('error_message', 'unknown')[:300]}"
                    ),
                })

            # 2. Pipeline freshness
            stale = await _check_pipeline_freshness()
            for s in stale:
                anomalies.append({
                    "type": "freshness_lag",
                    "severity": "medium",
                    "title": f"Pipeline {s.get('pipeline_id')} Stale",
                    "description": (
                        f"Pipeline {s.get('pipeline_name', s.get('pipeline_id'))} "
                        f"last ran at {s.get('last_run')} — "
                        f"stale for >{STALE_THRESHOLD_MINUTES} min"
                    ),
                })

            # 3. Data quality
            dq_issues = await _check_data_quality()
            for dq in dq_issues:
                anomalies.append({
                    "type": "data_quality",
                    "severity": "high",
                    "title": f"Data Quality: {dq['table']}.{dq['column']} null rate {dq['null_rate']}",
                    "description": (
                        f"Table {dq['table']}, column {dq['column']} has "
                        f"null rate {dq['null_rate']:.1%} (threshold {dq['threshold']:.1%})"
                    ),
                })

            # Create incidents for new anomalies (deduplicate by title)
            for a in anomalies:
                # Check if an open incident with same title already exists
                existing_inc = None
                async with async_session_factory() as db:
                    result = await db.execute(
                        select(Incident).where(
                            Incident.title == a["title"],
                            Incident.status.notin_(["resolved", "failed"]),
                        )
                    )
                    existing_inc = result.scalar_one_or_none()

                if existing_inc:
                    # If it's in "created" status with no session, start investigation
                    if existing_inc.status == "created" and not existing_inc.trueforge_session_id:
                        if settings.trueforge_enabled:
                            await _start_investigation(str(existing_inc.id))
                    continue

                inc_id = await _create_incident(
                    title=a["title"],
                    description=a["description"],
                    severity=a["severity"],
                    incident_type=a["type"],
                )
                if inc_id:
                    _incidents_created += 1
                    logger.info("Auto-created incident %s: %s", inc_id, a["title"])

                    # Start TrueForge investigation automatically
                    if settings.trueforge_enabled:
                        await _start_investigation(inc_id)

            _last_result = {
                "anomalies_found": len(anomalies),
                "incidents_created": _incidents_created,
                "failures": len(failures),
                "stale_pipelines": len(stale),
                "dq_issues": len(dq_issues),
            }

            if anomalies:
                logger.info(
                    "Monitor check: %d anomalies found, %d incidents created total",
                    len(anomalies), _incidents_created,
                )

        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("Monitor loop error: %s", exc, exc_info=True)

        await asyncio.sleep(interval)

    _running = False
    logger.info("Monitor stopped")


async def _start_investigation(incident_id: str) -> None:
    """Trigger a TrueForge investigation for an incident and wait for completion."""
    try:
        from apps.api.app.api.incidents import _get_trueforge

        tf = _get_trueforge()

        async with async_session_factory() as db:
            res = await db.execute(select(Incident).where(Incident.id == incident_id))
            inc = res.scalar_one_or_none()
            if not inc:
                return

            result = await tf.start_investigation(
                incident_id=incident_id,
                incident_type=inc.incident_type or "unknown",
                description=f"{inc.title}\n\n{inc.description or ''}",
            )
            session_id = result.get("session_id")
            turn_id = result.get("turn_id")
            if session_id:
                inc.status = "investigating"
                inc.trueforge_session_id = session_id
                await db.commit()
                logger.info("Started investigation for %s (session %s)", incident_id, session_id)
            else:
                logger.warning("No session returned for %s: %s", incident_id, result)
                return

        # Poll for completion
        if turn_id:
            await _poll_investigation(incident_id, session_id, turn_id)

    except Exception as exc:
        logger.error("Failed to start investigation for %s: %s", incident_id, exc)
        try:
            async with async_session_factory() as db:
                async with db.begin():
                    res = await db.execute(select(Incident).where(Incident.id == incident_id))
                    inc = res.scalar_one_or_none()
                    if inc and inc.status == "investigating" and not inc.trueforge_session_id:
                        inc.status = "created"
        except Exception:
            pass


async def _poll_investigation(incident_id: str, session_id: str, turn_id: str) -> None:
    """Poll TrueForge until the investigation turn completes."""
    from apps.api.app.api.incidents import _get_trueforge
    import asyncio as _asyncio

    tf = _get_trueforge()
    max_wait = 300  # 5 minutes max
    elapsed = 0
    poll_interval = 3.0

    while elapsed < max_wait:
        await _asyncio.sleep(poll_interval)
        elapsed += poll_interval

        try:
            turn_info = await tf.client.get_turn(session_id, turn_id)
            turn_data = turn_info.get("data", turn_info)
            turn_status = turn_data.get("state", {}).get("status", "")

            if turn_status in ("done", "completed"):
                output = turn_data.get("state", {}).get("output", {})
                content = ""
                if isinstance(output, dict):
                    content = output.get("content", "")
                elif isinstance(output, str):
                    content = output

                # Store the investigation result as an event
                async with async_session_factory() as db:
                    async with db.begin():
                        from apps.api.app.db.models import IncidentEvent
                        event = IncidentEvent(
                            incident_id=incident_id,
                            type="investigation_complete",
                            message=content[:2000] if content else "Investigation completed",
                        )
                        db.add(event)

                        # Update incident status
                        res = await db.execute(select(Incident).where(Incident.id == incident_id))
                        inc = res.scalar_one_or_none()
                        if inc:
                            inc.status = "investigation_complete"

                logger.info("Investigation %s completed (session %s)", incident_id, session_id)
                return

            elif turn_status in ("error", "cancelled"):
                msg = turn_data.get("state", {}).get("message", "Unknown error")
                logger.warning("Investigation %s failed: %s", incident_id, msg)
                async with async_session_factory() as db:
                    async with db.begin():
                        res = await db.execute(select(Incident).where(Incident.id == incident_id))
                        inc = res.scalar_one_or_none()
                        if inc:
                            inc.status = "failed"
                return

        except Exception as exc:
            logger.error("Poll error for %s: %s", incident_id, exc)

    logger.warning("Investigation %s timed out after %ds", incident_id, max_wait)


# ── public API ───────────────────────────────────────────────────────────────

def start(interval: int = DEFAULT_POLL_INTERVAL) -> None:
    """Start the background monitor (idempotent)."""
    global _task
    if _task and not _task.done():
        logger.info("Monitor already running")
        return
    _task = asyncio.create_task(_monitor_loop(interval))


def stop() -> None:
    """Stop the background monitor."""
    global _running
    _running = False
    if _task and not _task.done():
        _task.cancel()


def status() -> dict[str, Any]:
    """Return current monitor status."""
    return {
        "running": _running,
        "last_check": _last_check,
        "last_result": _last_result,
        "incidents_created": _incidents_created,
    }

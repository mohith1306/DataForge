"""Shared utilities for API routes."""
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.db.models import Incident
from apps.api.app.db.session import async_session_factory

logger = logging.getLogger(__name__)


async def set_incident_status(incident_id: str, status: str) -> None:
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
        logger.error("Failed to update %s: %s", incident_id, e)


def incident_to_dict(inc: Incident) -> dict[str, Any]:
    """Convert an Incident model to a dictionary for API responses."""
    return {
        "id": str(inc.id),
        "title": inc.title,
        "severity": inc.severity,
        "status": inc.status,
        "incident_type": inc.incident_type,
        "connector_id": inc.connector_id,
        "trueforge_session_id": inc.trueforge_session_id,
        "approval_reason": inc.approval_reason,
        "verification_result": inc.verification_result,
    }

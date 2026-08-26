from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.db.models import IncidentEvent
from apps.api.app.db.session import get_db
from apps.api.app.schemas.incident import IncidentEventResponse

router = APIRouter(prefix="/incidents/{incident_id}/events", tags=["events"])


@router.get("/", response_model=list[IncidentEventResponse])
async def list_events(incident_id: str, db: AsyncSession = Depends(get_db)) -> list[IncidentEvent]:
    result = await db.execute(
        select(IncidentEvent)
        .where(IncidentEvent.incident_id == incident_id)
        .order_by(IncidentEvent.created_at.asc())
    )
    return list(result.scalars().all())

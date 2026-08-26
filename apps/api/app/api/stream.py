"""SSE streaming endpoint for real-time incident updates."""

import asyncio
import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/stream", tags=["streaming"])

# In-memory event queue (per incident)
_subscribers: dict[str, list[asyncio.Queue]] = {}


async def publish_event(incident_id: str, event: dict) -> None:
    """Publish an event to all subscribers of an incident."""
    if incident_id in _subscribers:
        dead_queues = []
        for queue in _subscribers[incident_id]:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                dead_queues.append(queue)
        for q in dead_queues:
            _subscribers[incident_id].remove(q)


async def _event_generator(incident_id: str) -> AsyncGenerator[str, None]:
    """Generate SSE events for an incident."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    if incident_id not in _subscribers:
        _subscribers[incident_id] = []
    _subscribers[incident_id].append(queue)

    try:
        # Send initial connection event
        yield f"data: {json.dumps({'type': 'connected', 'incident_id': incident_id})}\n\n"

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30)
                yield f"data: {json.dumps(event)}\n\n"
            except TimeoutError:
                # Send keepalive
                yield ": keepalive\n\n"
    finally:
        if incident_id in _subscribers and queue in _subscribers[incident_id]:
            _subscribers[incident_id].remove(queue)


@router.get("/{incident_id}")
async def stream_incident(incident_id: str) -> StreamingResponse:
    """Stream real-time events for an incident via SSE."""
    return StreamingResponse(
        _event_generator(incident_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

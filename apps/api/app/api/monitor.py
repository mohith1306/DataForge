"""Monitor API — start/stop/status for the background health monitor."""

from fastapi import APIRouter

from apps.api.app.services import monitor

router = APIRouter(prefix="/monitor", tags=["monitor"])


@router.get("/status")
async def get_status() -> dict:
    """Return current monitor status."""
    return monitor.status()


@router.post("/start")
async def start_monitor(interval: int = 30) -> dict:
    """Start the background monitor."""
    monitor.start(interval=interval)
    return {"status": "started", "interval": interval}


@router.post("/stop")
async def stop_monitor() -> dict:
    """Stop the background monitor."""
    monitor.stop()
    return {"status": "stopped"}

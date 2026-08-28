"""DataForge API — Health check."""
import logging

from fastapi import APIRouter

from apps.api.app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    result: dict = {"status": "healthy", "service": "dataforge-api"}

    if settings.trueforge_enabled:
        try:
            from trueforge.client import TrueForgeClient
            client = TrueForgeClient(base_url=settings.trueforge_url)
            tf_health = await client.health()
            result["trueforge"] = {"status": "connected", **tf_health}
        except Exception as e:
            result["trueforge"] = {"status": "disconnected", "error": str(e)}
            logger.warning(f"TrueForge health check failed: {e}")
    else:
        result["trueforge"] = {"status": "disabled"}

    return result

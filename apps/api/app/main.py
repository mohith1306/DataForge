from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.app.api.chaos import router as chaos_router
from apps.api.app.api.connectors import router as connectors_router
from apps.api.app.api.database import router as database_router
from apps.api.app.api.events import router as events_router
from apps.api.app.api.health import router as health_router
from apps.api.app.api.incidents import router as incidents_router
from apps.api.app.api.monitor import router as monitor_router
from apps.api.app.api.stream import router as stream_router
from apps.api.app.core.config import settings
from apps.api.app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    setup_logging()
    from apps.api.app.db.session import ensure_schema
    await ensure_schema()

    # Auto-start background monitor
    from apps.api.app.services import monitor
    monitor.start(interval=30)

    # Auto-start monitoring for all enabled connectors
    from apps.api.app.services.connectors.registry import registry
    for conn in registry.list_connectors():
        if conn.get("enabled"):
            await registry.start_monitoring(conn["id"])

    yield
    monitor.stop()
    # Stop all connector monitoring
    for conn in registry.list_connectors():
        await registry.stop_monitoring(conn["id"])


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Autonomous Data Reliability Engineer",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(incidents_router, prefix="/api")
app.include_router(events_router, prefix="/api")
app.include_router(stream_router, prefix="/api")
app.include_router(chaos_router, prefix="/api")
app.include_router(monitor_router, prefix="/api")
app.include_router(database_router, prefix="/api")
app.include_router(connectors_router, prefix="/api")


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "dataforge-api", "version": settings.app_version}

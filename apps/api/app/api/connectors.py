"""Connector API — add, list, test, delete database connectors."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from apps.api.app.services.connectors.base import ConnectorConfig
from apps.api.app.services.connectors.registry import registry

router = APIRouter(prefix="/connectors", tags=["connectors"])


class AddConnectorRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    db_type: str = Field(..., pattern="^(postgres|mysql|clickhouse|snowflake|databricks)$")
    host: str = Field(..., min_length=1)
    port: int = Field(default=5432)
    database: str = Field(..., min_length=1)
    username: str = ""
    password: str = ""
    schema: str = "public"
    extra: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    poll_interval: int = Field(default=30, ge=5, le=3600)


@router.get("")
async def list_connectors():
    """List all registered database connectors."""
    return registry.list_connectors()


@router.post("")
async def add_connector(req: AddConnectorRequest):
    """Add a new database connector — auto-discovers tables and starts monitoring."""
    # Set schema default based on db type
    schema = req.schema
    if req.db_type == "clickhouse":
        schema = req.database
    elif req.db_type == "snowflake":
        schema = req.schema or "PUBLIC"
    elif req.db_type == "databricks":
        schema = req.schema or "default"

    config = ConnectorConfig(
        id=f"conn_{uuid.uuid4().hex[:12]}",
        name=req.name,
        db_type=req.db_type,
        host=req.host,
        port=req.port,
        database=req.database,
        username=req.username,
        password=req.password,
        schema=schema,
        extra=req.extra,
        enabled=req.enabled,
        poll_interval=req.poll_interval,
    )

    result = await registry.add_connector(config)

    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])

    # Auto-start monitoring
    if config.enabled:
        await registry.start_monitoring(config.id)

    return {
        "status": "success",
        "connector_id": config.id,
        "discovered_tables": result["discovered_tables"],
        "monitoring_queries": result["monitoring_queries"],
        "message": f"Connected to {req.db_type}. Found {len(result['discovered_tables'])} monitorable tables. Monitoring started.",
    }


@router.get("/{connector_id}")
async def get_connector(connector_id: str):
    """Get connector details."""
    connectors = registry.list_connectors()
    for c in connectors:
        if c["id"] == connector_id:
            return c
    raise HTTPException(status_code=404, detail="Connector not found")


@router.delete("/{connector_id}")
async def delete_connector(connector_id: str):
    """Delete a connector and stop its monitoring."""
    success = await registry.remove_connector(connector_id)
    if not success:
        raise HTTPException(status_code=404, detail="Connector not found")
    return {"status": "deleted", "connector_id": connector_id}


@router.post("/{connector_id}/test")
async def test_connector(connector_id: str):
    """Test a connector's database connection."""
    result = await registry.test_connection(connector_id)
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/{connector_id}/check")
async def run_check(connector_id: str):
    """Run a single monitoring check for a connector."""
    result = await registry.run_monitoring_check(connector_id)
    return result


@router.post("/{connector_id}/start")
async def start_monitoring(connector_id: str):
    """Start background monitoring for a connector."""
    await registry.start_monitoring(connector_id)
    return {"status": "started", "connector_id": connector_id}


@router.post("/{connector_id}/stop")
async def stop_monitoring(connector_id: str):
    """Stop background monitoring for a connector."""
    await registry.stop_monitoring(connector_id)
    return {"status": "stopped", "connector_id": connector_id}

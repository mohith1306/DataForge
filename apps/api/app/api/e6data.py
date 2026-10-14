"""e6data API — endpoints for e6data integration and telemetry.

Provides endpoints for:
- Query telemetry ingestion and retrieval
- Ingest pipeline telemetry
- AgentFlow reliability monitoring
- Graph integration for e6data resources
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.core.auth import get_current_user
from apps.api.app.core.config import settings
from apps.api.app.db.models import ReliabilityNode, ReliabilityEdge
from apps.api.app.db.session import get_db
from apps.api.app.services.e6data_connector import (
    E6DataConnector,
    QueryTelemetry,
    IngestTelemetry,
    Severity,
)
from apps.api.app.services.agentflow_reliability import (
    AgentFlowReliability,
    AgentRun,
    AgentStatus,
    ToolCall,
    ToolStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/e6data", tags=["e6data"])

e6data_connector = E6DataConnector()
agentflow = AgentFlowReliability()


# ─── Request Models ────────────────────────────────────────────────────


class QueryEventRequest(BaseModel):
    query_id: str
    query_text: str
    status: str
    duration_ms: float = 0.0
    rows_returned: int = 0
    rows_scanned: int = 0
    tables_scanned: list[str] = Field(default_factory=list)
    error_message: str = ""
    started_at: str = ""
    completed_at: str = ""


class IngestEventRequest(BaseModel):
    pipeline_id: str
    pipeline_name: str
    status: str
    records_processed: int = 0
    records_failed: int = 0
    throughput_rps: float = 0.0
    lag_seconds: float = 0.0
    schema_version: str = ""
    error_message: str = ""
    started_at: str = ""
    completed_at: str = ""


class AgentRunRequest(BaseModel):
    run_id: str
    agent_name: str
    status: str
    workflow_name: str = ""
    tool_calls: list[dict] = Field(default_factory=list)
    error_message: str = ""
    started_at: str = ""
    completed_at: str = ""
    duration_ms: float = 0.0


class GraphNodeRequest(BaseModel):
    node_type: str
    name: str
    external_id: str = ""
    business_criticality: str = "medium"
    extra_data: dict = Field(default_factory=dict)


# ─── Query Telemetry Endpoints ────────────────────────────────────────


@router.post("/telemetry/query")
async def ingest_query_event(
    req: QueryEventRequest,
    user: Any = Depends(get_current_user),
) -> dict:
    """Ingest a query telemetry event from e6data."""
    qt = QueryTelemetry(
        query_id=req.query_id,
        query_text=req.query_text,
        status=req.status,
        duration_ms=req.duration_ms,
        rows_returned=req.rows_returned,
        rows_scanned=req.rows_scanned,
        tables_scanned=req.tables_scanned,
        error_message=req.error_message,
        started_at=req.started_at,
        completed_at=req.completed_at,
    )
    event = await e6data_connector.ingest_query_event(qt)
    return {"status": "ingested", "event": event.to_dict()}


@router.get("/telemetry/query")
async def get_query_telemetry(
    time_range_minutes: int = 60,
    status_filter: str = "",
    user: Any = Depends(get_current_user),
) -> dict:
    """Get query telemetry from e6data."""
    telemetry = await e6data_connector.get_query_telemetry(time_range_minutes, status_filter)
    return {
        "count": len(telemetry),
        "telemetry": [t.to_dict() for t in telemetry],
    }


# ─── Ingest Telemetry Endpoints ──────────────────────────────────────


@router.post("/telemetry/ingest")
async def ingest_pipeline_event(
    req: IngestEventRequest,
    user: Any = Depends(get_current_user),
) -> dict:
    """Ingest a pipeline telemetry event from e6data."""
    it = IngestTelemetry(
        pipeline_id=req.pipeline_id,
        pipeline_name=req.pipeline_name,
        status=req.status,
        records_processed=req.records_processed,
        records_failed=req.records_failed,
        throughput_rps=req.throughput_rps,
        lag_seconds=req.lag_seconds,
        schema_version=req.schema_version,
        error_message=req.error_message,
        started_at=req.started_at,
        completed_at=req.completed_at,
    )
    event = await e6data_connector.ingest_pipeline_event(it)
    return {"status": "ingested", "event": event.to_dict()}


@router.get("/telemetry/ingest")
async def get_ingest_telemetry(
    time_range_minutes: int = 60,
    status_filter: str = "",
    user: Any = Depends(get_current_user),
) -> dict:
    """Get ingest pipeline telemetry from e6data."""
    telemetry = await e6data_connector.get_ingest_telemetry(time_range_minutes, status_filter)
    return {
        "count": len(telemetry),
        "telemetry": [t.to_dict() for t in telemetry],
    }


# ─── Anomaly Detection ────────────────────────────────────────────────


@router.get("/anomalies")
async def get_anomalies(
    min_severity: str = "medium",
    user: Any = Depends(get_current_user),
) -> dict:
    """Get detected anomalies from e6data telemetry."""
    severity = Severity(min_severity)
    anomalies = e6data_connector.get_anomalies(min_severity=severity)
    return {
        "count": len(anomalies),
        "anomalies": [a.to_dict() for a in anomalies],
    }


@router.get("/health/{resource_id}")
async def get_resource_health(
    resource_id: str,
    user: Any = Depends(get_current_user),
) -> dict:
    """Get health status for a specific e6data resource."""
    return e6data_connector.get_resource_health(resource_id)


# ─── AgentFlow Reliability Endpoints ──────────────────────────────────


@router.post("/agentflow/run")
async def record_agent_run(
    req: AgentRunRequest,
    user: Any = Depends(get_current_user),
) -> dict:
    """Record an agent run for reliability monitoring."""
    tool_calls = [
        ToolCall(
            tool_name=tc.get("tool_name", ""),
            status=ToolStatus(tc.get("status", "success")),
            duration_ms=tc.get("duration_ms", 0),
            error_message=tc.get("error_message", ""),
        )
        for tc in req.tool_calls
    ]

    run = AgentRun(
        run_id=req.run_id,
        agent_name=req.agent_name,
        status=AgentStatus(req.status),
        workflow_name=req.workflow_name,
        tool_calls=tool_calls,
        error_message=req.error_message,
        started_at=req.started_at,
        completed_at=req.completed_at,
        duration_ms=req.duration_ms,
    )

    events = await agentflow.record_run(run)

    return {
        "status": "recorded",
        "run": run.to_dict(),
        "events_detected": [e.to_dict() for e in events],
    }


@router.get("/agentflow/health/{agent_name}")
async def get_agent_health(
    agent_name: str,
    user: Any = Depends(get_current_user),
) -> dict:
    """Get health summary for a specific agent."""
    return agentflow.get_agent_health(agent_name)


@router.get("/agentflow/workflow/{workflow_name}")
async def get_workflow_health(
    workflow_name: str,
    user: Any = Depends(get_current_user),
) -> dict:
    """Get health summary for a specific workflow."""
    return agentflow.get_workflow_health(workflow_name)


@router.get("/agentflow/tools")
async def get_tool_reliability(
    user: Any = Depends(get_current_user),
) -> dict:
    """Get reliability stats for all tools."""
    return {"tools": agentflow.get_tool_reliability()}


@router.get("/agentflow/events")
async def get_agentflow_events(
    limit: int = 20,
    user: Any = Depends(get_current_user),
) -> dict:
    """Get recent agent reliability events."""
    return {"events": agentflow.get_recent_events(limit)}


# ─── Graph Integration ────────────────────────────────────────────────


@router.post("/graph/node")
async def create_e6data_node(
    req: GraphNodeRequest,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(get_current_user),
) -> dict:
    """Create an e6data resource as a Reliability Graph node."""
    from apps.api.app.core.config import settings

    org_id = settings.default_org_id

    node = ReliabilityNode(
        org_id=UUID(org_id) if isinstance(org_id, str) else org_id,
        node_type=req.node_type,
        name=req.name,
        external_id=req.external_id,
        business_criticality=req.business_criticality,
        extra_data={**req.extra_data, "source": "e6data"},
    )
    db.add(node)
    await db.flush()

    return {
        "status": "created",
        "node_id": str(node.id),
        "node_type": node.node_type,
        "name": node.name,
    }


@router.get("/graph/nodes")
async def list_e6data_nodes(
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(get_current_user),
) -> dict:
    """List all e6data graph nodes."""
    from apps.api.app.core.config import settings

    org_id = settings.default_org_id

    stmt = select(ReliabilityNode).where(
        ReliabilityNode.org_id == UUID(org_id) if isinstance(org_id, str) else org_id,
        ReliabilityNode.extra_data["source"].astext == "e6data",
    )
    result = await db.execute(stmt)
    nodes = result.scalars().all()

    return {
        "count": len(nodes),
        "nodes": [
            {
                "id": str(n.id),
                "node_type": n.node_type,
                "name": n.name,
                "external_id": n.external_id,
                "business_criticality": n.business_criticality,
            }
            for n in nodes
        ],
    }


@router.post("/graph/edge")
async def create_e6data_edge(
    source_id: str,
    target_id: str,
    edge_type: str = "depends_on",
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(get_current_user),
) -> dict:
    """Create an edge between e6data graph nodes."""
    edge = ReliabilityEdge(
        source_id=UUID(source_id),
        target_id=UUID(target_id),
        edge_type=edge_type,
        extra_data={"source": "e6data"},
    )
    db.add(edge)
    await db.flush()

    return {
        "status": "created",
        "edge_id": str(edge.id),
        "source_id": source_id,
        "target_id": target_id,
        "edge_type": edge_type,
    }

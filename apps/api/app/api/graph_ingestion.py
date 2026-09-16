"""Phase 8 API — Graph Ingestion, Lineage, and Versioning endpoints."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.core.auth import UserContext, get_current_user, require_write
from apps.api.app.db.session import get_db

router = APIRouter(prefix="/graph", tags=["graph-ingestion"])


# ─── Schemas ───────────────────────────────────────────────────────


class ConnectorDiscoveryRequest(BaseModel):
    connector_id: str
    connector_name: str
    db_type: str
    discovered_tables: list[dict]


class SQLLineageRequest(BaseModel):
    source_table: str
    target_table: str
    transformation: str = "select"
    connector_id: str | None = None


class SQLBatchLineageRequest(BaseModel):
    queries: list[str]
    connector_id: str | None = None


class DbtManifestRequest(BaseModel):
    manifest: dict
    connector_id: str | None = None


class VersionCreateRequest(BaseModel):
    description: str = ""


class VersionDiffRequest(BaseModel):
    version_a: str
    version_b: str


# ─── Graph Ingestion ──────────────────────────────────────────────


@router.post("/ingest/connector")
async def ingest_connector(
    payload: ConnectorDiscoveryRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_write),
) -> dict:
    """Ingest schema discovery from a connector into the Reliability Graph."""
    if not user.org_id:
        raise HTTPException(status_code=403, detail="Organization membership required")

    from apps.api.app.services.graph_ingestion import GraphIngestionService

    service = GraphIngestionService(db, user.org_id)
    stats = await service.ingest_connector_discovery(
        connector_id=payload.connector_id,
        connector_name=payload.connector_name,
        db_type=payload.db_type,
        discovered_tables=payload.discovered_tables,
    )
    return {"status": "success", "stats": stats}


@router.post("/ingest/sql-lineage")
async def ingest_sql_lineage(
    payload: SQLLineageRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_write),
) -> dict:
    """Ingest a single SQL lineage relationship."""
    if not user.org_id:
        raise HTTPException(status_code=403, detail="Organization membership required")

    from apps.api.app.services.graph_ingestion import GraphIngestionService

    service = GraphIngestionService(db, user.org_id)
    stats = await service.ingest_sql_lineage(
        source_table=payload.source_table,
        target_table=payload.target_table,
        transformation=payload.transformation,
        connector_id=payload.connector_id,
    )
    return {"status": "success", "stats": stats}


@router.post("/ingest/sql-batch")
async def ingest_sql_batch(
    payload: SQLBatchLineageRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_write),
) -> dict:
    """Parse multiple SQL queries and ingest all discovered lineage."""
    if not user.org_id:
        raise HTTPException(status_code=403, detail="Organization membership required")

    from apps.api.app.metadata.sql_lineage import SQLLineageParser
    from apps.api.app.services.graph_ingestion import GraphIngestionService

    parser = SQLLineageParser()
    parsed = parser.parse_batch(payload.queries)

    service = GraphIngestionService(db, user.org_id)
    total_stats = {"nodes_created": 0, "edges_created": 0}

    for edge in parsed["all_edges"]:
        stats = await service.ingest_sql_lineage(
            source_table=edge.source,
            target_table=edge.target,
            transformation=edge.transformation,
            connector_id=payload.connector_id,
        )
        total_stats["nodes_created"] += stats["nodes_created"]
        total_stats["edges_created"] += stats["edges_created"]

    return {
        "status": "success",
        "queries_parsed": parsed["query_count"],
        "lineage_edges_found": len(parsed["all_edges"]),
        "stats": total_stats,
    }


@router.post("/ingest/dbt")
async def ingest_dbt_manifest(
    payload: DbtManifestRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_write),
) -> dict:
    """Ingest lineage from a dbt manifest.json."""
    if not user.org_id:
        raise HTTPException(status_code=403, detail="Organization membership required")

    from apps.api.app.services.graph_ingestion import GraphIngestionService

    service = GraphIngestionService(db, user.org_id)
    stats = await service.ingest_dbt_manifest(
        manifest=payload.manifest,
        connector_id=payload.connector_id,
    )
    return {"status": "success", "stats": stats}


# ─── SQL Parsing ──────────────────────────────────────────────────


@router.post("/parse/sql")
async def parse_sql(
    payload: SQLBatchLineageRequest,
    user: UserContext = Depends(get_current_user),
) -> dict:
    """Parse SQL queries and return lineage without persisting."""
    from apps.api.app.metadata.sql_lineage import SQLLineageParser

    parser = SQLLineageParser()
    result = parser.parse_batch(payload.queries)

    return {
        "source_tables": result["all_source_tables"],
        "target_tables": result["all_target_tables"],
        "edges": [
            {
                "source": e.source,
                "target": e.target,
                "transformation": e.transformation,
            }
            for e in result["all_edges"]
        ],
        "query_count": result["query_count"],
    }


# ─── Graph Snapshot ───────────────────────────────────────────────


@router.get("/snapshot")
async def get_graph_snapshot(
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
) -> dict:
    """Get a point-in-time snapshot of the graph."""
    if not user.org_id:
        raise HTTPException(status_code=403, detail="Organization membership required")

    from apps.api.app.services.graph_ingestion import GraphIngestionService

    service = GraphIngestionService(db, user.org_id)
    return await service.snapshot_graph()


# ─── Graph Versioning ─────────────────────────────────────────────


@router.post("/versions")
async def create_version(
    payload: VersionCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_write),
) -> dict:
    """Create a new version snapshot of the graph."""
    if not user.org_id:
        raise HTTPException(status_code=403, detail="Organization membership required")

    from apps.api.app.services.graph_versioning import GraphVersioningService

    service = GraphVersioningService(db, user.org_id)
    return await service.create_version(description=payload.description)


@router.get("/versions")
async def list_versions(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
) -> dict:
    """List recent graph versions."""
    if not user.org_id:
        raise HTTPException(status_code=403, detail="Organization membership required")

    from apps.api.app.services.graph_versioning import GraphVersioningService

    service = GraphVersioningService(db, user.org_id)
    versions = await service.list_versions(limit=limit)
    return {"versions": versions}


@router.get("/versions/{version_number}")
async def get_version(
    version_number: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
) -> dict:
    """Get a specific graph version."""
    if not user.org_id:
        raise HTTPException(status_code=403, detail="Organization membership required")

    from apps.api.app.services.graph_versioning import GraphVersioningService

    service = GraphVersioningService(db, user.org_id)
    version = await service.get_version(version_number)
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    return version


@router.post("/versions/diff")
async def diff_versions(
    payload: VersionDiffRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
) -> dict:
    """Compare two graph versions."""
    if not user.org_id:
        raise HTTPException(status_code=403, detail="Organization membership required")

    from apps.api.app.services.graph_versioning import GraphVersioningService

    service = GraphVersioningService(db, user.org_id)
    return await service.diff_versions(payload.version_a, payload.version_b)

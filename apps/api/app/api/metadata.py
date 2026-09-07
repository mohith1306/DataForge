"""Metadata API endpoints."""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from ..core.auth import get_current_user, require_read, require_write
from ..core.tenant import UserContext
from ..metadata.schema_discovery import SchemaDiscovery, DiscoveredSchema
from ..metadata.lineage import LineageTracker, NodeType, EdgeType

router = APIRouter(prefix="/metadata", tags=["metadata"])

# Singleton instances
_schema_discovery = SchemaDiscovery()
_lineage_tracker = LineageTracker()


class SchemaDiscoverRequest(BaseModel):
    """Request to discover schema from data."""
    name: str
    source_id: str
    data: List[Dict[str, Any]]
    sample_size: int = 100


class LineageNodeRequest(BaseModel):
    """Request to add a lineage node."""
    name: str
    node_type: NodeType
    source_id: Optional[str] = None
    schema_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class LineageEdgeRequest(BaseModel):
    """Request to add a lineage edge."""
    source_node_id: str
    target_node_id: str
    edge_type: EdgeType
    transformation: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@router.post("/schemas/discover")
async def discover_schema(
    request: SchemaDiscoverRequest,
    user: UserContext = Depends(require_write),
) -> Dict[str, Any]:
    """Discover schema from data."""
    schema = _schema_discovery.discover_from_dict(
        name=request.name,
        source_id=request.source_id,
        data=request.data,
        sample_size=request.sample_size
    )
    return {"schema": schema.model_dump(), "message": "Schema discovered"}


@router.get("/schemas")
async def list_schemas(
    user: UserContext = Depends(require_read),
) -> Dict[str, Any]:
    """List all discovered schemas."""
    schemas = _schema_discovery.list_schemas()
    return {"schemas": [s.model_dump() for s in schemas]}


@router.get("/schemas/{schema_id}")
async def get_schema(
    schema_id: str,
    user: UserContext = Depends(require_read),
) -> Dict[str, Any]:
    """Get a specific schema."""
    schema = _schema_discovery.get_schema(schema_id)
    if not schema:
        raise HTTPException(status_code=404, detail="Schema not found")
    return {"schema": schema.model_dump()}


@router.get("/schemas/compare/{schema_id1}/{schema_id2}")
async def compare_schemas(
    schema_id1: str,
    schema_id2: str,
    user: UserContext = Depends(require_read),
) -> Dict[str, Any]:
    """Compare two schemas."""
    result = _schema_discovery.compare_schemas(schema_id1, schema_id2)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/lineage/nodes")
async def add_lineage_node(
    request: LineageNodeRequest,
    user: UserContext = Depends(require_write),
) -> Dict[str, Any]:
    """Add a node to the lineage graph."""
    node = _lineage_tracker.add_node(
        name=request.name,
        node_type=request.node_type,
        source_id=request.source_id,
        schema_id=request.schema_id,
        metadata=request.metadata
    )
    return {"node": node.model_dump(), "message": "Node added"}


@router.post("/lineage/edges")
async def add_lineage_edge(
    request: LineageEdgeRequest,
    user: UserContext = Depends(require_write),
) -> Dict[str, Any]:
    """Add an edge to the lineage graph."""
    edge = _lineage_tracker.add_edge(
        source_node_id=request.source_node_id,
        target_node_id=request.target_node_id,
        edge_type=request.edge_type,
        transformation=request.transformation,
        metadata=request.metadata
    )
    if not edge:
        raise HTTPException(status_code=400, detail="Invalid node IDs")
    return {"edge": edge.model_dump(), "message": "Edge added"}


@router.get("/lineage/upstream/{node_id}")
async def get_upstream(
    node_id: str,
    depth: int = -1,
    user: UserContext = Depends(require_read),
) -> Dict[str, Any]:
    """Get upstream nodes."""
    nodes = _lineage_tracker.get_upstream(node_id, depth)
    return {"nodes": [n.model_dump() for n in nodes]}


@router.get("/lineage/downstream/{node_id}")
async def get_downstream(
    node_id: str,
    depth: int = -1,
    user: UserContext = Depends(require_read),
) -> Dict[str, Any]:
    """Get downstream nodes."""
    nodes = _lineage_tracker.get_downstream(node_id, depth)
    return {"nodes": [n.model_dump() for n in nodes]}


@router.get("/lineage/blast-radius/{node_id}")
async def get_blast_radius(
    node_id: str,
    user: UserContext = Depends(require_read),
) -> Dict[str, Any]:
    """Calculate blast radius from a node."""
    result = _lineage_tracker.get_blast_radius(node_id)
    return result


@router.get("/lineage/summary")
async def get_lineage_summary(
    user: UserContext = Depends(require_read),
) -> Dict[str, Any]:
    """Get lineage graph summary."""
    return _lineage_tracker.get_lineage_summary()


@router.get("/lineage/cycles")
async def detect_cycles(
    user: UserContext = Depends(require_read),
) -> Dict[str, Any]:
    """Detect cycles in lineage graph."""
    cycles = _lineage_tracker.detect_cycles()
    return {"cycles": cycles, "count": len(cycles)}

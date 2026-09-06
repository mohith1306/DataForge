"""Reliability Graph API — CRUD and traversal endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.core.auth import UserContext, get_current_user, require_write
from apps.api.app.db.session import get_db
from apps.api.app.schemas.reliability_graph import (
    BlastRadius,
    BlastRadiusNode,
    BusinessImpact,
    EdgeCreate,
    EdgeResponse,
    NodeCreate,
    NodeResponse,
    NodeUpdate,
    ReliabilityScore,
)
from apps.api.app.services.reliability_graph import ReliabilityGraphService

router = APIRouter(prefix="/graph", tags=["reliability-graph"])


async def get_graph_service(
    user: UserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReliabilityGraphService:
    """Dependency that provides a graph service scoped to the user's org."""
    if not user.org_id:
        raise HTTPException(
            status_code=400,
            detail="User must belong to an organization to use the graph",
        )
    return ReliabilityGraphService(db, user.org_id)


# ─── Node Endpoints ──────────────────────────────────────────────


@router.post("/nodes", response_model=NodeResponse, status_code=201)
async def create_node(
    payload: NodeCreate,
    graph: ReliabilityGraphService = Depends(get_graph_service),
    user: UserContext = Depends(require_write),
) -> NodeResponse:
    """Add a node to the reliability graph."""
    node = await graph.add_node(
        node_type=payload.node_type,
        name=payload.name,
        external_id=payload.external_id,
        metadata=payload.metadata,
        project_id=payload.project_id,
        owner_id=payload.owner_id,
        business_criticality=payload.business_criticality,
    )
    return node


@router.get("/nodes", response_model=list[NodeResponse])
async def list_nodes(
    node_type: str | None = None,
    project_id: UUID | None = None,
    limit: int = 100,
    offset: int = 0,
    graph: ReliabilityGraphService = Depends(get_graph_service),
) -> list[NodeResponse]:
    """List nodes with optional filters."""
    return await graph.list_nodes(
        node_type=node_type,
        project_id=project_id,
        limit=limit,
        offset=offset,
    )


@router.get("/nodes/{node_id}", response_model=NodeResponse)
async def get_node(
    node_id: UUID,
    graph: ReliabilityGraphService = Depends(get_graph_service),
) -> NodeResponse:
    """Get a node by ID."""
    node = await graph.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node


@router.patch("/nodes/{node_id}", response_model=NodeResponse)
async def update_node(
    node_id: UUID,
    payload: NodeUpdate,
    graph: ReliabilityGraphService = Depends(get_graph_service),
    user: UserContext = Depends(require_write),
) -> NodeResponse:
    """Update a node."""
    node = await graph.update_node(
        node_id=node_id,
        name=payload.name,
        external_id=payload.external_id,
        metadata=payload.metadata,
        owner_id=payload.owner_id,
        business_criticality=payload.business_criticality,
        project_id=payload.project_id,
    )
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node


@router.delete("/nodes/{node_id}")
async def delete_node(
    node_id: UUID,
    graph: ReliabilityGraphService = Depends(get_graph_service),
    user: UserContext = Depends(require_write),
) -> dict:
    """Delete a node and all its edges."""
    success = await graph.delete_node(node_id)
    if not success:
        raise HTTPException(status_code=404, detail="Node not found")
    return {"status": "deleted", "node_id": str(node_id)}


# ─── Edge Endpoints ──────────────────────────────────────────────


@router.post("/edges", response_model=EdgeResponse, status_code=201)
async def create_edge(
    payload: EdgeCreate,
    graph: ReliabilityGraphService = Depends(get_graph_service),
    user: UserContext = Depends(require_write),
) -> EdgeResponse:
    """Add an edge between two nodes."""
    try:
        edge = await graph.add_edge(
            source_id=payload.source_id,
            target_id=payload.target_id,
            edge_type=payload.edge_type,
            metadata=payload.metadata,
        )
        return edge
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/edges", response_model=list[EdgeResponse])
async def list_edges(
    node_id: UUID | None = None,
    edge_type: str | None = None,
    direction: str = "both",
    graph: ReliabilityGraphService = Depends(get_graph_service),
) -> list[EdgeResponse]:
    """List edges with optional filters."""
    return await graph.get_edges(
        node_id=node_id,
        edge_type=edge_type,
        direction=direction,
    )


@router.delete("/edges/{edge_id}")
async def delete_edge(
    edge_id: UUID,
    graph: ReliabilityGraphService = Depends(get_graph_service),
    user: UserContext = Depends(require_write),
) -> dict:
    """Delete an edge."""
    success = await graph.delete_edge(edge_id)
    if not success:
        raise HTTPException(status_code=404, detail="Edge not found")
    return {"status": "deleted", "edge_id": str(edge_id)}


# ─── Graph Traversal Endpoints ───────────────────────────────────


@router.get("/nodes/{node_id}/upstream", response_model=list[NodeResponse])
async def get_upstream(
    node_id: UUID,
    depth: int = 5,
    graph: ReliabilityGraphService = Depends(get_graph_service),
) -> list[NodeResponse]:
    """Get all upstream nodes (dependencies)."""
    return await graph.get_upstream(node_id, depth)


@router.get("/nodes/{node_id}/downstream", response_model=list[NodeResponse])
async def get_downstream(
    node_id: UUID,
    depth: int = 5,
    graph: ReliabilityGraphService = Depends(get_graph_service),
) -> list[NodeResponse]:
    """Get all downstream nodes (dependents)."""
    return await graph.get_downstream(node_id, depth)


@router.get("/nodes/{node_id}/subgraph")
async def get_subgraph(
    node_id: UUID,
    depth: int = 3,
    graph: ReliabilityGraphService = Depends(get_graph_service),
) -> dict:
    """Get a subgraph centered on a node."""
    subgraph = await graph.get_subgraph(node_id, depth)
    return {
        "nodes": [
            {
                "id": str(n.id),
                "node_type": n.node_type,
                "name": n.name,
                "reliability_score": n.reliability_score,
                "business_criticality": n.business_criticality,
            }
            for n in subgraph["nodes"]
        ],
        "edges": [
            {
                "id": str(e.id),
                "source_id": str(e.source_id),
                "target_id": str(e.target_id),
                "edge_type": e.edge_type,
            }
            for e in subgraph["edges"]
        ],
    }


# ─── Analysis Endpoints ──────────────────────────────────────────


@router.get("/nodes/{node_id}/blast-radius")
async def get_blast_radius(
    node_id: UUID,
    depth: int = 10,
    graph: ReliabilityGraphService = Depends(get_graph_service),
) -> BlastRadius:
    """Calculate the blast radius if this node fails."""
    blast = await graph.calculate_blast_radius(node_id, depth)
    return BlastRadius(
        affected_nodes=[BlastRadiusNode(**n) for n in blast["affected_nodes"]],
        total_affected=blast["total_affected"],
        business_impact=blast["business_impact"],
        affected_business_processes=blast["affected_business_processes"],
        affected_by_type=blast.get("affected_by_type", {}),
    )


@router.get("/nodes/{node_id}/reliability-score")
async def get_reliability_score(
    node_id: UUID,
    graph: ReliabilityGraphService = Depends(get_graph_service),
) -> ReliabilityScore:
    """Calculate reliability score for a node."""
    result = await graph.calculate_reliability_score(node_id)
    node = await graph.get_node(node_id)
    return ReliabilityScore(
        node_id=node_id,
        score=result["score"],
        factors=result["factors"],
        last_updated=node.last_updated if node else None,
    )


@router.get("/incidents/{incident_id}/business-impact")
async def get_business_impact(
    incident_id: UUID,
    graph: ReliabilityGraphService = Depends(get_graph_service),
) -> BusinessImpact:
    """Analyze business impact of an incident."""
    result = await graph.analyze_business_impact(incident_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return BusinessImpact(**result)


# ─── Stats Endpoint ──────────────────────────────────────────────


@router.get("/stats")
async def get_graph_stats(
    graph: ReliabilityGraphService = Depends(get_graph_service),
) -> dict:
    """Get statistics about the reliability graph."""
    return await graph.get_graph_stats()

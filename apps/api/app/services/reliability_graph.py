"""Reliability Graph Service — Central abstraction for DataForge."""
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.db.models import (
    Incident,
    ReliabilityEdge,
    ReliabilityNode,
)

logger = logging.getLogger(__name__)


class ReliabilityGraphService:
    """Manages the Reliability Graph — technical and business entities."""

    def __init__(self, db: AsyncSession, org_id: UUID):
        self.db = db
        self.org_id = org_id

    # ─── Node Operations ──────────────────────────────────────────────

    async def add_node(
        self,
        node_type: str,
        name: str,
        external_id: str | None = None,
        metadata: dict | None = None,
        project_id: UUID | None = None,
        owner_id: UUID | None = None,
        business_criticality: str = "medium",
    ) -> ReliabilityNode:
        """Add a node to the reliability graph."""
        node = ReliabilityNode(
            org_id=self.org_id,
            project_id=project_id,
            node_type=node_type,
            name=name,
            external_id=external_id,
            extra_data=metadata or {},
            owner_id=owner_id,
            business_criticality=business_criticality,
            reliability_score=100.0,
        )
        self.db.add(node)
        await self.db.flush()
        await self.db.refresh(node)
        logger.info("Added node: %s (%s)", name, node_type)
        return node

    async def get_node(self, node_id: UUID) -> ReliabilityNode | None:
        """Get a node by ID."""
        result = await self.db.execute(
            select(ReliabilityNode)
            .where(ReliabilityNode.id == node_id)
            .where(ReliabilityNode.org_id == self.org_id)
        )
        return result.scalar_one_or_none()

    async def get_node_by_external_id(
        self, external_id: str, node_type: str | None = None
    ) -> ReliabilityNode | None:
        """Get a node by external_id."""
        query = (
            select(ReliabilityNode)
            .where(ReliabilityNode.org_id == self.org_id)
            .where(ReliabilityNode.external_id == external_id)
        )
        if node_type:
            query = query.where(ReliabilityNode.node_type == node_type)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_nodes(
        self,
        node_type: str | None = None,
        project_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ReliabilityNode]:
        """List nodes with optional filters."""
        query = (
            select(ReliabilityNode)
            .where(ReliabilityNode.org_id == self.org_id)
            .order_by(ReliabilityNode.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        if node_type:
            query = query.where(ReliabilityNode.node_type == node_type)
        if project_id:
            query = query.where(ReliabilityNode.project_id == project_id)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_node(
        self,
        node_id: UUID,
        name: str | None = None,
        external_id: str | None = None,
        metadata: dict | None = None,
        owner_id: UUID | None = None,
        business_criticality: str | None = None,
        project_id: UUID | None = None,
    ) -> ReliabilityNode | None:
        """Update node properties."""
        node = await self.get_node(node_id)
        if not node:
            return None

        if name is not None:
            node.name = name
        if external_id is not None:
            node.external_id = external_id
        if metadata is not None:
            node.extra_data = {**node.extra_data, **metadata}
        if owner_id is not None:
            node.owner_id = owner_id
        if business_criticality is not None:
            node.business_criticality = business_criticality
        if project_id is not None:
            node.project_id = project_id

        node.last_updated = datetime.now(UTC)
        await self.db.flush()
        return node

    async def delete_node(self, node_id: UUID) -> bool:
        """Delete a node and all its edges."""
        node = await self.get_node(node_id)
        if not node:
            return False

        # Delete all edges involving this node
        await self.db.execute(
            ReliabilityEdge.__table__.delete()
            .where(
                or_(
                    ReliabilityEdge.source_id == node_id,
                    ReliabilityEdge.target_id == node_id,
                )
            )
        )

        await self.db.delete(node)
        await self.db.flush()
        logger.info("Deleted node: %s", node_id)
        return True

    # ─── Edge Operations ──────────────────────────────────────────────

    async def add_edge(
        self,
        source_id: UUID,
        target_id: UUID,
        edge_type: str,
        metadata: dict | None = None,
    ) -> ReliabilityEdge:
        """Add an edge between two nodes."""
        # Verify both nodes exist and belong to same org
        source = await self.get_node(source_id)
        target = await self.get_node(target_id)

        if not source or not target:
            raise ValueError("Source or target node not found")

        if source_id == target_id:
            raise ValueError("Cannot create self-referencing edge")

        # Check for duplicate edge
        existing = await self.db.execute(
            select(ReliabilityEdge)
            .where(
                and_(
                    ReliabilityEdge.source_id == source_id,
                    ReliabilityEdge.target_id == target_id,
                    ReliabilityEdge.edge_type == edge_type,
                )
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Edge already exists")

        edge = ReliabilityEdge(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            extra_data=metadata or {},
        )
        self.db.add(edge)
        await self.db.flush()
        await self.db.refresh(edge)
        logger.info("Added edge: %s -> %s (%s)", source_id, target_id, edge_type)
        return edge

    async def get_edges(
        self,
        node_id: UUID | None = None,
        edge_type: str | None = None,
        direction: str = "both",
    ) -> list[ReliabilityEdge]:
        """Get edges, optionally filtered by node, type, and direction."""
        query = select(ReliabilityEdge)

        if node_id:
            if direction == "outgoing":
                query = query.where(ReliabilityEdge.source_id == node_id)
            elif direction == "incoming":
                query = query.where(ReliabilityEdge.target_id == node_id)
            else:
                query = query.where(
                    or_(
                        ReliabilityEdge.source_id == node_id,
                        ReliabilityEdge.target_id == node_id,
                    )
                )

        if edge_type:
            query = query.where(ReliabilityEdge.edge_type == edge_type)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_edge(
        self, source_id: UUID, target_id: UUID, edge_type: str
    ) -> ReliabilityEdge | None:
        """Get a specific edge."""
        result = await self.db.execute(
            select(ReliabilityEdge)
            .where(
                and_(
                    ReliabilityEdge.source_id == source_id,
                    ReliabilityEdge.target_id == target_id,
                    ReliabilityEdge.edge_type == edge_type,
                )
            )
        )
        return result.scalar_one_or_none()

    async def delete_edge(self, edge_id: UUID) -> bool:
        """Delete an edge."""
        result = await self.db.execute(
            select(ReliabilityEdge).where(ReliabilityEdge.id == edge_id)
        )
        edge = result.scalar_one_or_none()
        if not edge:
            return False

        await self.db.delete(edge)
        await self.db.flush()
        logger.info("Deleted edge: %s", edge_id)
        return True

    # ─── Graph Traversal ──────────────────────────────────────────────

    async def get_upstream(
        self,
        node_id: UUID,
        depth: int = 5,
        edge_types: list[str] | None = None,
    ) -> list[ReliabilityNode]:
        """Get all upstream nodes (dependencies) up to depth."""
        visited: set[UUID] = set()
        result: list[ReliabilityNode] = []

        async def _traverse(current_id: UUID, current_depth: int):
            if current_depth > depth or current_id in visited:
                return
            visited.add(current_id)

            # Get edges where current node is the target (incoming edges)
            query = select(ReliabilityEdge).where(
                ReliabilityEdge.target_id == current_id
            )
            if edge_types:
                query = query.where(ReliabilityEdge.edge_type.in_(edge_types))

            edges = (await self.db.execute(query)).scalars().all()

            for edge in edges:
                if edge.source_id not in visited:
                    node = await self.get_node(edge.source_id)
                    if node:
                        result.append(node)
                        await _traverse(edge.source_id, current_depth + 1)

        await _traverse(node_id, 0)
        return result

    async def get_downstream(
        self,
        node_id: UUID,
        depth: int = 5,
        edge_types: list[str] | None = None,
    ) -> list[ReliabilityNode]:
        """Get all downstream nodes (dependents) up to depth."""
        visited: set[UUID] = set()
        result: list[ReliabilityNode] = []

        async def _traverse(current_id: UUID, current_depth: int):
            if current_depth > depth or current_id in visited:
                return
            visited.add(current_id)

            # Get edges where current node is the source (outgoing edges)
            query = select(ReliabilityEdge).where(
                ReliabilityEdge.source_id == current_id
            )
            if edge_types:
                query = query.where(ReliabilityEdge.edge_type.in_(edge_types))

            edges = (await self.db.execute(query)).scalars().all()

            for edge in edges:
                if edge.target_id not in visited:
                    node = await self.get_node(edge.target_id)
                    if node:
                        result.append(node)
                        await _traverse(edge.target_id, current_depth + 1)

        await _traverse(node_id, 0)
        return result

    async def get_subgraph(
        self,
        node_id: UUID,
        depth: int = 3,
    ) -> dict:
        """Get a subgraph centered on a node."""
        center = await self.get_node(node_id)
        if not center:
            return {"nodes": [], "edges": []}

        upstream = await self.get_upstream(node_id, depth)
        downstream = await self.get_downstream(node_id, depth)

        all_nodes = [center] + upstream + downstream
        node_ids = {n.id for n in all_nodes}

        # Get all edges between these nodes
        edges: list[ReliabilityEdge] = []
        for node in all_nodes:
            node_edges = await self.get_edges(node_id=node.id)
            for edge in node_edges:
                if edge.source_id in node_ids and edge.target_id in node_ids:
                    edges.append(edge)

        return {
            "nodes": all_nodes,
            "edges": edges,
        }

    # ─── Blast Radius Analysis ────────────────────────────────────────

    async def calculate_blast_radius(
        self,
        node_id: UUID,
        depth: int = 10,
    ) -> dict:
        """Calculate the blast radius if this node fails."""
        downstream = await self.get_downstream(node_id, depth)

        if not downstream:
            return {
                "affected_nodes": [],
                "total_affected": 0,
                "business_impact": "none",
                "affected_business_processes": [],
                "affected_by_type": {},
            }

        # Categorize affected nodes
        affected_by_type: dict[str, list] = {}
        for node in downstream:
            if node.node_type not in affected_by_type:
                affected_by_type[node.node_type] = []
            affected_by_type[node.node_type].append(node)

        # Get affected business processes
        business_processes = [
            n for n in downstream if n.node_type == "business_process"
        ]

        # Calculate business impact
        critical_count = sum(
            1 for n in downstream if n.business_criticality in ("high", "critical")
        )

        if critical_count > 5 or len(business_processes) > 2:
            business_impact = "critical"
        elif critical_count > 2 or len(business_processes) > 0:
            business_impact = "high"
        elif critical_count > 0 or len(downstream) > 10:
            business_impact = "medium"
        else:
            business_impact = "low"

        return {
            "affected_nodes": [
                {
                    "id": str(n.id),
                    "type": n.node_type,
                    "name": n.name,
                    "criticality": n.business_criticality,
                }
                for n in downstream
            ],
            "total_affected": len(downstream),
            "business_impact": business_impact,
            "affected_business_processes": [n.name for n in business_processes],
            "affected_by_type": {k: len(v) for k, v in affected_by_type.items()},
        }

    # ─── Reliability Score Calculation ─────────────────────────────────

    async def calculate_reliability_score(
        self,
        node_id: UUID,
    ) -> dict:
        """Calculate reliability score for a node based on multiple factors."""
        node = await self.get_node(node_id)
        if not node:
            return {"score": 0.0, "factors": {}}

        factors = {
            "freshness": 100.0,
            "failure_rate": 100.0,
            "schema_stability": 100.0,
            "dependency_health": 100.0,
            "historical_risk": 100.0,
        }

        # Get recent incidents for this node
        recent_incidents = await self.db.execute(
            select(Incident)
            .where(Incident.org_id == self.org_id)
            .where(Incident.reliability_graph_snapshot.isnot(None))
            .order_by(Incident.created_at.desc())
            .limit(100)
        )
        incidents = list(recent_incidents.scalars().all())

        # Calculate failure rate
        node_incidents = [
            i
            for i in incidents
            if i.reliability_graph_snapshot
            and str(node_id) in str(i.reliability_graph_snapshot)
        ]

        if node_incidents:
            failure_count = len(node_incidents)
            factors["failure_rate"] = max(0, 100 - (failure_count * 10))

        # Get downstream nodes and check their health
        downstream = await self.get_downstream(node_id, depth=3)
        if downstream:
            avg_score = sum(n.reliability_score for n in downstream) / len(downstream)
            factors["dependency_health"] = avg_score

        # Weighted average
        weights = {
            "freshness": 0.2,
            "failure_rate": 0.3,
            "schema_stability": 0.2,
            "dependency_health": 0.2,
            "historical_risk": 0.1,
        }

        score = sum(factors[k] * weights[k] for k in weights)

        # Update node
        node.reliability_score = score
        node.last_updated = datetime.now(UTC)
        await self.db.flush()

        return {"score": score, "factors": factors}

    # ─── Business Impact Analysis ─────────────────────────────────────

    async def analyze_business_impact(
        self,
        incident_id: UUID,
    ) -> dict:
        """Analyze business impact of an incident based on the graph."""
        result = await self.db.execute(
            select(Incident).where(Incident.id == incident_id)
        )
        incident = result.scalar_one_or_none()
        if not incident:
            return {"error": "Incident not found"}

        # Find affected nodes from incident snapshot
        affected_node_ids: list[str] = []
        if incident.reliability_graph_snapshot:
            affected_node_ids = incident.reliability_graph_snapshot.get(
                "affected_nodes", []
            )

        if not affected_node_ids:
            return {
                "impact_level": "unknown",
                "affected_business_processes": [],
                "recommended_actions": [],
            }

        # Analyze each affected node
        business_processes: list[str] = []
        total_impact_score = 0

        for node_id_str in affected_node_ids:
            try:
                node_id = UUID(node_id_str)
                blast = await self.calculate_blast_radius(node_id)

                if blast["affected_business_processes"]:
                    business_processes.extend(blast["affected_business_processes"])

                # Score based on criticality
                criticality_scores = {"low": 1, "medium": 2, "high": 3, "critical": 4}
                node = await self.get_node(node_id)
                if node:
                    total_impact_score += criticality_scores.get(
                        node.business_criticality, 1
                    )
            except (ValueError, TypeError):
                continue

        # Determine impact level
        if total_impact_score > 20:
            impact_level = "critical"
        elif total_impact_score > 10:
            impact_level = "high"
        elif total_impact_score > 5:
            impact_level = "medium"
        else:
            impact_level = "low"

        return {
            "impact_level": impact_level,
            "impact_score": total_impact_score,
            "affected_business_processes": list(set(business_processes)),
            "recommended_actions": self._get_recommended_actions(impact_level),
        }

    def _get_recommended_actions(self, impact_level: str) -> list[str]:
        """Get recommended actions based on impact level."""
        actions = {
            "critical": [
                "Immediate rollback of changes",
                "Notify business stakeholders",
                "Activate incident response team",
                "Consider data restoration from backup",
            ],
            "high": [
                "Investigate root cause immediately",
                "Notify affected teams",
                "Consider rollback if fix is not clear",
            ],
            "medium": [
                "Schedule investigation",
                "Monitor for escalation",
                "Document findings",
            ],
            "low": [
                "Add to backlog",
                "Monitor trends",
            ],
        }
        return actions.get(impact_level, actions["low"])

    # ─── Failure DNA ──────────────────────────────────────────────────

    async def generate_failure_dna(
        self,
        incident_id: UUID,
    ) -> str:
        """Generate a machine-readable fingerprint for an incident."""
        result = await self.db.execute(
            select(Incident).where(Incident.id == incident_id)
        )
        incident = result.scalar_one_or_none()
        if not incident:
            return ""

        # Build fingerprint from incident properties
        parts = [
            incident.incident_type or "UNKNOWN",
            incident.severity.upper(),
        ]

        # Add affected node types
        if incident.reliability_graph_snapshot:
            affected = incident.reliability_graph_snapshot.get("affected_nodes", [])
            for node_id_str in affected[:5]:  # Limit to 5
                try:
                    node = await self.get_node(UUID(node_id_str))
                    if node:
                        parts.append(node.node_type.upper())
                except (ValueError, TypeError):
                    pass

        return "+".join(parts)

    # ─── Graph Statistics ─────────────────────────────────────────────

    async def get_graph_stats(self) -> dict:
        """Get statistics about the reliability graph."""
        nodes = await self.list_nodes(limit=10000)
        edges = await self.get_edges()

        # Count by type
        nodes_by_type: dict[str, int] = {}
        for node in nodes:
            nodes_by_type[node.node_type] = nodes_by_type.get(node.node_type, 0) + 1

        edges_by_type: dict[str, int] = {}
        for edge in edges:
            edges_by_type[edge.edge_type] = edges_by_type.get(edge.edge_type, 0) + 1

        # Average reliability score
        avg_score = (
            sum(n.reliability_score for n in nodes) / len(nodes) if nodes else 0
        )

        return {
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "nodes_by_type": nodes_by_type,
            "edges_by_type": edges_by_type,
            "average_reliability_score": round(avg_score, 2),
        }

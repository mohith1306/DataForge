"""Lineage Tracking for data flow and dependency mapping."""
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from enum import Enum
from collections import defaultdict


class NodeType(str, Enum):
    """Types of lineage nodes."""
    TABLE = "table"
    VIEW = "view"
    PIPELINE = "pipeline"
    DASHBOARD = "dashboard"
    MODEL = "model"
    API = "api"
    FILE = "file"
    TRANSFORM = "transform"


class EdgeType(str, Enum):
    """Types of lineage edges."""
    READS_FROM = "reads_from"
    WRITES_TO = "writes_to"
    TRANSFORMS = "transforms"
    DEPENDS_ON = "depends_on"
    UPSTREAM = "upstream"
    DOWNSTREAM = "downstream"


class LineageNode(BaseModel):
    """A node in the lineage graph."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    node_type: NodeType
    source_id: Optional[str] = None
    schema_id: Optional[str] = None
    metadata: Dict[str, Any] = {}
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LineageEdge(BaseModel):
    """An edge in the lineage graph."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    source_node_id: str
    target_node_id: str
    edge_type: EdgeType
    transformation: Optional[str] = None
    metadata: Dict[str, Any] = {}
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LineageTracker:
    """Tracks data lineage and dependencies."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.nodes: Dict[str, LineageNode] = {}
        self.edges: Dict[str, LineageEdge] = {}
        self.adjacency: Dict[str, List[str]] = defaultdict(list)  # node_id -> edge_ids
        self.reverse_adjacency: Dict[str, List[str]] = defaultdict(list)

    def add_node(
        self,
        name: str,
        node_type: NodeType,
        source_id: Optional[str] = None,
        schema_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> LineageNode:
        """Add a node to the lineage graph."""
        # Check if node already exists
        for node in self.nodes.values():
            if node.name == name and node.node_type == node_type:
                return node

        node = LineageNode(
            name=name,
            node_type=node_type,
            source_id=source_id,
            schema_id=schema_id,
            metadata=metadata or {}
        )
        self.nodes[node.id] = node
        return node

    def add_edge(
        self,
        source_node_id: str,
        target_node_id: str,
        edge_type: EdgeType,
        transformation: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[LineageEdge]:
        """Add an edge to the lineage graph."""
        if source_node_id not in self.nodes or target_node_id not in self.nodes:
            return None

        # Check for duplicate edges
        for edge in self.edges.values():
            if (edge.source_node_id == source_node_id and
                edge.target_node_id == target_node_id and
                edge.edge_type == edge_type):
                return edge

        edge = LineageEdge(
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            edge_type=edge_type,
            transformation=transformation,
            metadata=metadata or {}
        )
        self.edges[edge.id] = edge
        self.adjacency[source_node_id].append(edge.id)
        self.reverse_adjacency[target_node_id].append(edge.id)
        return edge

    def get_upstream(self, node_id: str, depth: int = -1) -> List[LineageNode]:
        """Get all upstream nodes (dependencies)."""
        visited = set()
        result = []
        self._traverse_upstream(node_id, depth, visited, result)
        return result

    def _traverse_upstream(self, node_id: str, depth: int, visited: Set[str], result: List[LineageNode]):
        """Recursively traverse upstream."""
        if depth == 0 or node_id in visited:
            return
        visited.add(node_id)

        for edge_id in self.reverse_adjacency.get(node_id, []):
            edge = self.edges[edge_id]
            source_node = self.nodes.get(edge.source_node_id)
            if source_node and source_node.id not in visited:
                result.append(source_node)
                self._traverse_upstream(source_node.id, depth - 1, visited, result)

    def get_downstream(self, node_id: str, depth: int = -1) -> List[LineageNode]:
        """Get all downstream nodes (dependents)."""
        visited = set()
        result = []
        self._traverse_downstream(node_id, depth, visited, result)
        return result

    def _traverse_downstream(self, node_id: str, depth: int, visited: Set[str], result: List[LineageNode]):
        """Recursively traverse downstream."""
        if depth == 0 or node_id in visited:
            return
        visited.add(node_id)

        for edge_id in self.adjacency.get(node_id, []):
            edge = self.edges[edge_id]
            target_node = self.nodes.get(edge.target_node_id)
            if target_node and target_node.id not in visited:
                result.append(target_node)
                self._traverse_downstream(target_node.id, depth - 1, visited, result)

    def get_blast_radius(self, node_id: str) -> Dict[str, Any]:
        """Calculate blast radius from a node."""
        downstream = self.get_downstream(node_id)
        upstream = self.get_upstream(node_id)

        affected_by_type = defaultdict(int)
        for node in downstream:
            affected_by_type[node.node_type.value] += 1

        return {
            "source_node": node_id,
            "directly_affected": len([e for e in self.edges.values() if e.source_node_id == node_id]),
            "total_downstream": len(downstream),
            "total_upstream": len(upstream),
            "affected_by_type": dict(affected_by_type),
            "risk_score": min(1.0, len(downstream) * 0.1)
        }

    def find_paths(self, source_id: str, target_id: str) -> List[List[str]]:
        """Find all paths between two nodes."""
        paths = []
        self._find_paths_dfs(source_id, target_id, [], paths)
        return paths

    def _find_paths_dfs(self, current: str, target: str, path: List[str], all_paths: List[List[str]]):
        """DFS to find paths."""
        if current == target:
            all_paths.append(path + [current])
            return

        if current in path:
            return

        path.append(current)
        for edge_id in self.adjacency.get(current, []):
            edge = self.edges[edge_id]
            self._find_paths_dfs(edge.target_node_id, target, path, all_paths)
        path.pop()

    def get_lineage_summary(self) -> Dict[str, Any]:
        """Get summary of lineage graph."""
        node_types = defaultdict(int)
        edge_types = defaultdict(int)

        for node in self.nodes.values():
            node_types[node.node_type.value] += 1

        for edge in self.edges.values():
            edge_types[edge.edge_type.value] += 1

        return {
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "node_types": dict(node_types),
            "edge_types": dict(edge_types),
            "orphan_nodes": len([n for n in self.nodes.values() if not self.adjacency.get(n.id) and not self.reverse_adjacency.get(n.id)])
        }

    def detect_cycles(self) -> List[List[str]]:
        """Detect cycles in the lineage graph."""
        cycles = []
        visited = set()
        rec_stack = set()

        def dfs(node_id, path):
            visited.add(node_id)
            rec_stack.add(node_id)
            path.append(node_id)

            for edge_id in self.adjacency.get(node_id, []):
                edge = self.edges[edge_id]
                if edge.target_node_id not in visited:
                    dfs(edge.target_node_id, path)
                elif edge.target_node_id in rec_stack:
                    cycle_start = path.index(edge.target_node_id)
                    cycles.append(path[cycle_start:] + [edge.target_node_id])

            path.pop()
            rec_stack.remove(node_id)

        for node_id in self.nodes:
            if node_id not in visited:
                dfs(node_id, [])

        return cycles

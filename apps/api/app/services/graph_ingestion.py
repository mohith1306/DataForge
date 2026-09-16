"""Graph Ingestion Service — Populates the Reliability Graph from external sources.

This is the core of Phase 8: Auto-Ingestion & Data Lineage.
It takes discoveries from connectors, SQL parsers, and dbt manifests
and populates the DB-backed Reliability Graph idempotently.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.db.models import ReliabilityEdge, ReliabilityNode

logger = logging.getLogger(__name__)


class GraphIngestionService:
    """Idempotent ingestion pipeline for the Reliability Graph.

    External System → Metadata Adapter → Normalizer → Graph Updater → Reliability Graph
    """

    def __init__(self, db: AsyncSession, org_id: UUID):
        self.db = db
        self.org_id = org_id

    # ─── Idempotent Node Upsert ────────────────────────────────────────

    async def upsert_node(
        self,
        node_type: str,
        name: str,
        external_id: str | None = None,
        metadata: dict | None = None,
        project_id: UUID | None = None,
        business_criticality: str = "medium",
    ) -> ReliabilityNode:
        """Insert or update a node. Idempotent by (external_id, node_type)."""
        existing = await self._find_node(external_id, node_type)
        if existing:
            # Update
            if metadata:
                existing.extra_data = {**existing.extra_data, **metadata}
            existing.name = name
            existing.last_updated = datetime.now(UTC)
            await self.db.flush()
            return existing
        # Create
        node = ReliabilityNode(
            org_id=self.org_id,
            project_id=project_id,
            node_type=node_type,
            name=name,
            external_id=external_id,
            extra_data=metadata or {},
            business_criticality=business_criticality,
            reliability_score=100.0,
        )
        self.db.add(node)
        await self.db.flush()
        await self.db.refresh(node)
        return node

    async def _find_node(
        self, external_id: str | None, node_type: str | None = None
    ) -> ReliabilityNode | None:
        """Find a node by external_id and optionally node_type."""
        if not external_id:
            return None
        query = (
            select(ReliabilityNode)
            .where(ReliabilityNode.org_id == self.org_id)
            .where(ReliabilityNode.external_id == external_id)
        )
        if node_type:
            query = query.where(ReliabilityNode.node_type == node_type)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    # ─── Idempotent Edge Upsert ────────────────────────────────────────

    async def upsert_edge(
        self,
        source_id: UUID,
        target_id: UUID,
        edge_type: str,
        metadata: dict | None = None,
    ) -> ReliabilityEdge | None:
        """Insert an edge. Idempotent — returns existing if already present."""
        existing = await self._find_edge(source_id, target_id, edge_type)
        if existing:
            return existing
        if source_id == target_id:
            return None
        # Verify both nodes exist
        source = await self._get_node(source_id)
        target = await self._get_node(target_id)
        if not source or not target:
            return None
        edge = ReliabilityEdge(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            extra_data=metadata or {},
        )
        self.db.add(edge)
        await self.db.flush()
        await self.db.refresh(edge)
        return edge

    async def _find_edge(
        self, source_id: UUID, target_id: UUID, edge_type: str
    ) -> ReliabilityEdge | None:
        result = await self.db.execute(
            select(ReliabilityEdge).where(
                and_(
                    ReliabilityEdge.source_id == source_id,
                    ReliabilityEdge.target_id == target_id,
                    ReliabilityEdge.edge_type == edge_type,
                )
            )
        )
        return result.scalar_one_or_none()

    async def _get_node(self, node_id: UUID) -> ReliabilityNode | None:
        result = await self.db.execute(
            select(ReliabilityNode).where(
                and_(
                    ReliabilityNode.id == node_id,
                    ReliabilityNode.org_id == self.org_id,
                )
            )
        )
        return result.scalar_one_or_none()

    # ─── Connector Discovery Ingestion ─────────────────────────────────

    async def ingest_connector_discovery(
        self,
        connector_id: str,
        connector_name: str,
        db_type: str,
        discovered_tables: list[dict],
    ) -> dict:
        """Ingest schema discovery from a connector into the graph.

        Args:
            connector_id: Connector identifier
            connector_name: Human-readable name
            db_type: Database type (postgres, clickhouse, etc.)
            discovered_tables: List of table info dicts from auto_discover

        Returns:
            Summary of ingested nodes and edges
        """
        stats = {"nodes_created": 0, "nodes_updated": 0, "edges_created": 0}

        # 1. Create/Update connector node
        connector_node = await self.upsert_node(
            node_type="source",
            name=connector_name,
            external_id=f"connector:{connector_id}",
            metadata={
                "db_type": db_type,
                "connector_id": connector_id,
                "source_type": "connector",
            },
            business_criticality="high",
        )
        stats["nodes_created"] += 1

        # 2. Create/Update database node
        db_name = discovered_tables[0].get("database", connector_name) if discovered_tables else connector_name
        db_node = await self.upsert_node(
            node_type="source",
            name=db_name,
            external_id=f"database:{connector_id}:{db_name}",
            metadata={
                "db_type": db_type,
                "connector_id": connector_id,
                "source_type": "database",
            },
            business_criticality="high",
        )
        stats["nodes_created"] += 1

        # Edge: connector → database
        edge = await self.upsert_edge(
            source_id=connector_node.id,
            target_id=db_node.id,
            edge_type="dependency",
            metadata={"relationship": "contains"},
        )
        if edge:
            stats["edges_created"] += 1

        # 3. Ingest each table and its columns
        for table_info in discovered_tables:
            table_name = table_info.get("table", "unknown")
            table_type = table_info.get("type", "unknown")
            columns = table_info.get("columns", {})
            row_count = table_info.get("row_count", 0)

            # Table node
            table_node = await self.upsert_node(
                node_type="table",
                name=table_name,
                external_id=f"table:{connector_id}:{table_name}",
                metadata={
                    "db_type": db_type,
                    "connector_id": connector_id,
                    "table_type": table_type,
                    "row_count": row_count,
                    "columns": list(columns.keys()) if isinstance(columns, dict) else [],
                },
                business_criticality="medium",
            )
            stats["nodes_created"] += 1

            # Edge: database → table
            edge = await self.upsert_edge(
                source_id=db_node.id,
                target_id=table_node.id,
                edge_type="dependency",
                metadata={"relationship": "contains"},
            )
            if edge:
                stats["edges_created"] += 1

            # Column nodes
            if isinstance(columns, dict):
                for col_name in columns:
                    col_node = await self.upsert_node(
                        node_type="column",
                        name=f"{table_name}.{col_name}",
                        external_id=f"column:{connector_id}:{table_name}:{col_name}",
                        metadata={
                            "table": table_name,
                            "column": col_name,
                            "connector_id": connector_id,
                        },
                        business_criticality="low",
                    )
                    stats["nodes_created"] += 1

                    # Edge: table → column
                    edge = await self.upsert_edge(
                        source_id=table_node.id,
                        target_id=col_node.id,
                        edge_type="dependency",
                        metadata={"relationship": "contains"},
                    )
                    if edge:
                        stats["edges_created"] += 1

        await self.db.commit()
        logger.info(
            "Ingested connector %s: %d nodes, %d edges",
            connector_name, stats["nodes_created"], stats["edges_created"],
        )
        return stats

    # ─── SQL Lineage Ingestion ─────────────────────────────────────────

    async def ingest_sql_lineage(
        self,
        source_table: str,
        target_table: str,
        transformation: str = "unknown",
        connector_id: str | None = None,
    ) -> dict:
        """Ingest a lineage edge derived from SQL analysis.

        Args:
            source_table: Source table name (e.g., "public.orders")
            target_table: Target table name (e.g., "staging.stg_orders")
            transformation: Type of transformation (select, join, aggregate, etc.)
            connector_id: Optional connector ID for external_id prefix

        Returns:
            Summary of created nodes and edges
        """
        stats = {"nodes_created": 0, "edges_created": 0}

        prefix = f"connector:{connector_id}:" if connector_id else ""

        source_node = await self.upsert_node(
            node_type="table",
            name=source_table,
            external_id=f"{prefix}table:{source_table}",
            metadata={"source_type": "sql_lineage"},
        )
        stats["nodes_created"] += 1

        target_node = await self.upsert_node(
            node_type="table",
            name=target_table,
            external_id=f"{prefix}table:{target_table}",
            metadata={"source_type": "sql_lineage"},
        )
        stats["nodes_created"] += 1

        edge = await self.upsert_edge(
            source_id=source_node.id,
            target_id=target_node.id,
            edge_type="lineage",
            metadata={
                "transformation": transformation,
                "source": "sql_parser",
            },
        )
        if edge:
            stats["edges_created"] += 1

        return stats

    # ─── dbt Manifest Ingestion ────────────────────────────────────────

    async def ingest_dbt_manifest(
        self,
        manifest: dict,
        connector_id: str | None = None,
    ) -> dict:
        """Ingest lineage from a dbt manifest.json.

        The manifest contains nodes with upstream/downstream relationships.
        """
        stats = {"nodes_created": 0, "edges_created": 0}
        prefix = f"connector:{connector_id}:" if connector_id else ""

        nodes = manifest.get("nodes", {})

        for node_id, node_data in nodes.items():
            node_type = node_data.get("resource_type", "model")
            name = node_data.get("name", node_id)
            schema = node_data.get("schema", "")
            database = node_data.get("database", "")

            # Create dbt model node
            dbt_node = await self.upsert_node(
                node_type="pipeline" if node_type == "model" else "table",
                name=f"{database}.{schema}.{name}" if database else name,
                external_id=f"{prefix}dbt:{node_id}",
                metadata={
                    "dbt_resource_type": node_type,
                    "database": database,
                    "schema": schema,
                    "materialized": node_data.get("config", {}).get("materialized", ""),
                    "source": "dbt",
                },
                business_criticality="medium",
            )
            stats["nodes_created"] += 1

            # Create upstream edges from depends_on
            depends_on = node_data.get("depends_on", {})
            upstream_refs = depends_on.get("nodes", [])
            for upstream_id in upstream_refs:
                upstream_node = await self.upsert_node(
                    node_type="table",
                    name=upstream_id,
                    external_id=f"{prefix}dbt:{upstream_id}",
                    metadata={"source": "dbt_ref"},
                )
                stats["nodes_created"] += 1

                edge = await self.upsert_edge(
                    source_id=upstream_node.id,
                    target_id=dbt_node.id,
                    edge_type="lineage",
                    metadata={
                        "source": "dbt_manifest",
                        "relationship": "depends_on",
                    },
                )
                if edge:
                    stats["edges_created"] += 1

        await self.db.commit()
        logger.info(
            "Ingested dbt manifest: %d nodes, %d edges",
            stats["nodes_created"], stats["edges_created"],
        )
        return stats

    # ─── Graph Snapshot ────────────────────────────────────────────────

    async def snapshot_graph(self) -> dict:
        """Capture a point-in-time snapshot of the graph state."""
        nodes_result = await self.db.execute(
            select(ReliabilityNode).where(ReliabilityNode.org_id == self.org_id)
        )
        nodes = list(nodes_result.scalars().all())

        edges_result = await self.db.execute(
            select(ReliabilityEdge)
            .join(ReliabilityNode, ReliabilityEdge.source_id == ReliabilityNode.id)
            .where(ReliabilityNode.org_id == self.org_id)
        )
        edges = list(edges_result.scalars().all())

        # Generate a content hash for change detection
        content = json.dumps(
            {
                "nodes": sorted(
                    [{"id": str(n.id), "name": n.name, "type": n.node_type} for n in nodes],
                    key=lambda x: str(x["id"]),
                ),
                "edges": sorted(
                    [{"src": str(e.source_id), "tgt": str(e.target_id), "type": e.edge_type} for e in edges],
                    key=lambda x: f"{x['src']}:{x['tgt']}",
                ),
            },
            sort_keys=True,
        )
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "content_hash": content_hash,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "nodes_by_type": self._count_by_type(nodes, "node_type"),
            "edges_by_type": self._count_by_type(edges, "edge_type"),
        }

    def _count_by_type(self, items: list, field: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in items:
            t = getattr(item, field, "unknown")
            counts[t] = counts.get(t, 0) + 1
        return counts

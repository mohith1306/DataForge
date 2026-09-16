"""Graph Versioning Service — Track changes to the Reliability Graph over time.

Enables historical analysis: "What did the graph look like at incident time?"
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.db.models import GraphVersion, ReliabilityEdge, ReliabilityNode

logger = logging.getLogger(__name__)


class GraphVersioningService:
    """Manages graph versions — snapshots and diffs."""

    def __init__(self, db: AsyncSession, org_id: UUID):
        self.db = db
        self.org_id = org_id

    async def create_version(self, description: str = "") -> dict:
        """Create a new version snapshot of the current graph state."""
        # Capture current state
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

        # Build snapshot
        snapshot = {
            "nodes": [
                {
                    "id": str(n.id),
                    "type": n.node_type,
                    "name": n.name,
                    "external_id": n.external_id,
                    "criticality": n.business_criticality,
                    "score": n.reliability_score,
                    "metadata": n.extra_data,
                }
                for n in nodes
            ],
            "edges": [
                {
                    "id": str(e.id),
                    "source": str(e.source_id),
                    "target": str(e.target_id),
                    "type": e.edge_type,
                    "metadata": e.extra_data,
                }
                for e in edges
            ],
        }

        # Calculate content hash
        content_str = json.dumps(snapshot, sort_keys=True, default=str)
        content_hash = hashlib.sha256(content_str.encode()).hexdigest()[:16]

        # Get next version number
        last_version = await self._get_latest_version()
        if last_version:
            try:
                last_num = int(last_version.version_number.split(".")[-1])
            except (ValueError, IndexError):
                last_num = 0
            version_number = f"1.0.{last_num + 1}"
        else:
            version_number = "1.0.0"

        # Check if state actually changed
        if last_version and last_version.content_hash == content_hash:
            return {
                "version_number": last_version.version_number,
                "content_hash": content_hash,
                "changed": False,
                "message": "No changes detected",
            }

        # Save version
        graph_version = GraphVersion(
            org_id=self.org_id,
            version_number=version_number,
            content_hash=content_hash,
            snapshot=snapshot,
            change_description=description,
        )
        self.db.add(graph_version)
        await self.db.flush()

        logger.info("Created graph version %s (hash=%s)", version_number, content_hash)
        return {
            "version_number": version_number,
            "content_hash": content_hash,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "changed": True,
        }

    async def get_version(self, version_number: str) -> dict | None:
        """Get a specific version by number."""
        result = await self.db.execute(
            select(GraphVersion)
            .where(GraphVersion.org_id == self.org_id)
            .where(GraphVersion.version_number == version_number)
        )
        version = result.scalar_one_or_none()
        if not version:
            return None
        return {
            "version_number": version.version_number,
            "content_hash": version.content_hash,
            "snapshot": version.snapshot,
            "change_description": version.change_description,
            "created_at": version.created_at.isoformat() if version.created_at else None,
        }

    async def list_versions(self, limit: int = 20) -> list[dict]:
        """List recent versions."""
        result = await self.db.execute(
            select(GraphVersion)
            .where(GraphVersion.org_id == self.org_id)
            .order_by(desc(GraphVersion.created_at))
            .limit(limit)
        )
        versions = result.scalars().all()
        return [
            {
                "version_number": v.version_number,
                "content_hash": v.content_hash,
                "change_description": v.change_description,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in versions
        ]

    async def diff_versions(
        self, version_a: str, version_b: str
    ) -> dict:
        """Compare two versions and return the diff."""
        a = await self.get_version(version_a)
        b = await self.get_version(version_b)

        if not a or not b:
            return {"error": "Version not found"}

        a_nodes = {n["id"]: n for n in a["snapshot"].get("nodes", [])}
        b_nodes = {n["id"]: n for n in b["snapshot"].get("nodes", [])}
        a_edges = {e["id"]: e for e in a["snapshot"].get("edges", [])}
        b_edges = {e["id"]: e for e in b["snapshot"].get("edges", [])}

        added_nodes = [b_nodes[nid] for nid in b_nodes if nid not in a_nodes]
        removed_nodes = [a_nodes[nid] for nid in a_nodes if nid not in b_nodes]
        added_edges = [b_edges[eid] for eid in b_edges if eid not in a_edges]
        removed_edges = [a_edges[eid] for eid in a_edges if eid not in b_edges]

        # Detect modified nodes
        modified_nodes = []
        for nid in a_nodes:
            if nid in b_nodes:
                a_data = json.dumps(a_nodes[nid], sort_keys=True, default=str)
                b_data = json.dumps(b_nodes[nid], sort_keys=True, default=str)
                if a_data != b_data:
                    modified_nodes.append({
                        "id": nid,
                        "before": a_nodes[nid],
                        "after": b_nodes[nid],
                    })

        return {
            "version_a": version_a,
            "version_b": version_b,
            "added_nodes": added_nodes,
            "removed_nodes": removed_nodes,
            "modified_nodes": modified_nodes,
            "added_edges": added_edges,
            "removed_edges": removed_edges,
            "summary": {
                "nodes_added": len(added_nodes),
                "nodes_removed": len(removed_nodes),
                "nodes_modified": len(modified_nodes),
                "edges_added": len(added_edges),
                "edges_removed": len(removed_edges),
            },
        }

    async def _get_latest_version(self) -> GraphVersion | None:
        result = await self.db.execute(
            select(GraphVersion)
            .where(GraphVersion.org_id == self.org_id)
            .order_by(desc(GraphVersion.created_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

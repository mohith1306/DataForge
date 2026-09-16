"""dbt Manifest Parser — Extracts lineage from dbt manifest.json.

The manifest contains nodes (models, sources, tests) with
depends_on relationships that define the lineage graph.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DbtNode:
    """Parsed dbt node."""
    node_id: str
    name: str
    resource_type: str  # model, source, test, seed, snapshot
    database: str = ""
    schema_name: str = ""
    materialized: str = ""
    upstream_ids: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DbtLineage:
    """Lineage graph parsed from a dbt manifest."""
    nodes: list[DbtNode] = field(default_factory=list)
    edges: list[tuple[str, str]] = field(default_factory=list)  # (upstream_id, downstream_id)
    sources: list[DbtNode] = field(default_factory=list)
    models: list[DbtNode] = field(default_factory=list)


class DbtManifestParser:
    """Parse dbt manifest.json for lineage extraction."""

    def parse_file(self, path: str | Path) -> DbtLineage:
        """Parse a dbt manifest.json file."""
        path = Path(path)
        if not path.exists():
            logger.error("dbt manifest not found: %s", path)
            return DbtLineage()

        with open(path) as f:
            manifest = json.load(f)

        return self.parse_manifest(manifest)

    def parse_manifest(self, manifest: dict) -> DbtLineage:
        """Parse a dbt manifest dict."""
        lineage = DbtLineage()
        nodes_data = manifest.get("nodes", {})
        sources_data = manifest.get("sources", {})

        # Parse nodes
        node_map: dict[str, DbtNode] = {}
        for node_id, node_data in nodes_data.items():
            dbt_node = self._parse_node(node_id, node_data)
            node_map[node_id] = dbt_node
            lineage.nodes.append(dbt_node)

            if dbt_node.resource_type == "model":
                lineage.models.append(dbt_node)

        # Parse sources
        for source_id, source_data in sources_data.items():
            dbt_node = self._parse_source(source_id, source_data)
            node_map[source_id] = dbt_node
            lineage.nodes.append(dbt_node)
            lineage.sources.append(dbt_node)

        # Build edges from depends_on
        for node_id, dbt_node in node_map.items():
            for upstream_id in dbt_node.upstream_ids:
                if upstream_id in node_map:
                    lineage.edges.append((upstream_id, node_id))

        logger.info(
            "Parsed dbt manifest: %d nodes, %d edges, %d sources, %d models",
            len(lineage.nodes), len(lineage.edges),
            len(lineage.sources), len(lineage.models),
        )
        return lineage

    def _parse_node(self, node_id: str, data: dict) -> DbtNode:
        """Parse a single dbt node."""
        config = data.get("config", {})
        depends_on = data.get("depends_on", {})

        columns = []
        columns_data = data.get("columns", {})
        if isinstance(columns_data, dict):
            columns = list(columns_data.keys())

        return DbtNode(
            node_id=node_id,
            name=data.get("name", node_id),
            resource_type=data.get("resource_type", "model"),
            database=data.get("database", ""),
            schema_name=data.get("schema", ""),
            materialized=config.get("materialized", ""),
            upstream_ids=depends_on.get("nodes", []),
            columns=columns,
            tags=data.get("tags", []),
            metadata={
                "package_name": data.get("package_name", ""),
                "path": data.get("path", ""),
                "config": config,
            },
        )

    def _parse_source(self, source_id: str, data: dict) -> DbtNode:
        """Parse a dbt source."""
        columns = []
        columns_data = data.get("columns", {})
        if isinstance(columns_data, dict):
            columns = list(columns_data.keys())

        return DbtNode(
            node_id=source_id,
            name=data.get("name", source_id),
            resource_type="source",
            database=data.get("database", ""),
            schema_name=data.get("schema", ""),
            columns=columns,
            tags=data.get("tags", []),
            metadata={
                "source_name": data.get("source_name", ""),
                "loader": data.get("loader", ""),
            },
        )

    def get_lineage_dict(self, lineage: DbtLineage) -> dict:
        """Convert DbtLineage to a serializable dict."""
        return {
            "nodes": [
                {
                    "id": n.node_id,
                    "name": n.name,
                    "type": n.resource_type,
                    "database": n.database,
                    "schema": n.schema_name,
                    "materialized": n.materialized,
                    "columns": n.columns,
                    "tags": n.tags,
                    "upstream": n.upstream_ids,
                }
                for n in lineage.nodes
            ],
            "edges": [
                {"source": src, "target": tgt}
                for src, tgt in lineage.edges
            ],
            "summary": {
                "total_nodes": len(lineage.nodes),
                "total_edges": len(lineage.edges),
                "sources": len(lineage.sources),
                "models": len(lineage.models),
            },
        }

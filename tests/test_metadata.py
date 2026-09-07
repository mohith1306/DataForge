"""Tests for Metadata Engine — Schema Discovery and Lineage Tracking."""
import pytest
from datetime import datetime, timezone
from apps.api.app.metadata.schema_discovery import SchemaDiscovery, FieldType
from apps.api.app.metadata.lineage import LineageTracker, NodeType, EdgeType


class TestSchemaDiscovery:
    """Tests for SchemaDiscovery."""

    def setup_method(self):
        self.discovery = SchemaDiscovery()

    def test_discover_from_dict(self):
        data = [
            {"id": 1, "name": "Alice", "active": True},
            {"id": 2, "name": "Bob", "active": False},
        ]
        schema = self.discovery.discover_from_dict("users", "db1", data)
        assert schema.name == "users"
        assert len(schema.fields) == 3
        assert schema.row_count == 2

    def test_field_type_inference(self):
        data = [
            {"score": 100, "ratio": 0.5, "label": "high", "flag": True}
        ]
        schema = self.discovery.discover_from_dict("test", "src1", data)
        field_map = {f.name: f.field_type for f in schema.fields}
        assert field_map["score"] == FieldType.INTEGER
        assert field_map["ratio"] == FieldType.FLOAT
        assert field_map["label"] == FieldType.STRING
        assert field_map["flag"] == FieldType.BOOLEAN

    def test_discover_empty_data(self):
        schema = self.discovery.discover_from_dict("empty", "src2", [])
        assert schema.row_count is None
        assert len(schema.fields) == 0

    def test_schema_persistence(self):
        data = [{"a": 1}]
        schema = self.discovery.discover_from_dict("s1", "src3", data)
        retrieved = self.discovery.get_schema(schema.id)
        assert retrieved is not None
        assert retrieved.name == "s1"

    def test_compare_schemas(self):
        s1 = self.discovery.discover_from_dict("s1", "src", [{"a": 1, "b": 2}])
        s2 = self.discovery.discover_from_dict("s2", "src", [{"a": 1, "c": 3}])
        result = self.discovery.compare_schemas(s1.id, s2.id)
        assert "a" in result["common_fields"]
        assert "b" in result["only_in_schema1"]
        assert "c" in result["only_in_schema2"]
        assert result["similarity"] > 0


class TestLineageTracker:
    """Tests for LineageTracker."""

    def setup_method(self):
        self.tracker = LineageTracker()

    def test_add_node(self):
        node = self.tracker.add_node("users_table", NodeType.TABLE)
        assert node.name == "users_table"
        assert node.node_type == NodeType.TABLE

    def test_add_edge(self):
        n1 = self.tracker.add_node("source", NodeType.TABLE)
        n2 = self.tracker.add_node("target", NodeType.TABLE)
        edge = self.tracker.add_edge(n1.id, n2.id, EdgeType.READS_FROM)
        assert edge is not None
        assert edge.source_node_id == n1.id

    def test_upstream_downstream(self):
        n1 = self.tracker.add_node("a", NodeType.TABLE)
        n2 = self.tracker.add_node("b", NodeType.TABLE)
        n3 = self.tracker.add_node("c", NodeType.TABLE)
        self.tracker.add_edge(n1.id, n2.id, EdgeType.READS_FROM)
        self.tracker.add_edge(n2.id, n3.id, EdgeType.READS_FROM)

        upstream = self.tracker.get_upstream(n3.id)
        assert len(upstream) == 2

        downstream = self.tracker.get_downstream(n1.id)
        assert len(downstream) == 2

    def test_blast_radius(self):
        n1 = self.tracker.add_node("core", NodeType.TABLE)
        n2 = self.tracker.add_node("dep1", NodeType.TABLE)
        n3 = self.tracker.add_node("dep2", NodeType.TABLE)
        self.tracker.add_edge(n1.id, n2.id, EdgeType.READS_FROM)
        self.tracker.add_edge(n1.id, n3.id, EdgeType.READS_FROM)

        radius = self.tracker.get_blast_radius(n1.id)
        assert radius["total_downstream"] == 2
        assert radius["risk_score"] > 0

    def test_cycle_detection(self):
        n1 = self.tracker.add_node("x", NodeType.TABLE)
        n2 = self.tracker.add_node("y", NodeType.TABLE)
        self.tracker.add_edge(n1.id, n2.id, EdgeType.READS_FROM)
        self.tracker.add_edge(n2.id, n1.id, EdgeType.READS_FROM)

        cycles = self.tracker.detect_cycles()
        assert len(cycles) > 0

    def test_lineage_summary(self):
        self.tracker.add_node("a", NodeType.TABLE)
        self.tracker.add_node("b", NodeType.VIEW)
        summary = self.tracker.get_lineage_summary()
        assert summary["total_nodes"] == 2
        assert summary["node_types"]["table"] == 1

"""Phase 8 Tests — Graph Ingestion, Lineage Parsing, and Versioning."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from apps.api.app.metadata.sql_lineage import SQLLineageParser, TableRef, LineageEdge
from apps.api.app.metadata.dbt_parser import DbtManifestParser, DbtLineage


class TestSQLLineageParser:
    """Test SQL lineage extraction."""

    def setup_method(self):
        self.parser = SQLLineageParser()

    def test_simple_select(self):
        sql = "SELECT * FROM public.orders WHERE id = 1"
        result = self.parser.parse(sql)
        assert len(result["source_tables"]) == 1
        assert result["source_tables"][0].table == "orders"
        assert result["source_tables"][0].schema == "public"

    def test_insert_select(self):
        sql = "INSERT INTO staging.stg_orders SELECT * FROM public.orders"
        result = self.parser.parse(sql)
        assert len(result["source_tables"]) == 1
        assert result["source_tables"][0].full_name == "public.orders"
        assert len(result["target_tables"]) == 1
        assert result["target_tables"][0].full_name == "staging.stg_orders"
        assert len(result["lineage_edges"]) == 1
        assert result["lineage_edges"][0].source == "public.orders"
        assert result["lineage_edges"][0].target == "staging.stg_orders"

    def test_join_lineage(self):
        sql = """
        SELECT o.id, c.name
        FROM public.orders o
        JOIN public.customers c ON o.customer_id = c.id
        """
        result = self.parser.parse(sql)
        assert len(result["source_tables"]) == 2
        tables = {t.table for t in result["source_tables"]}
        assert "orders" in tables
        assert "customers" in tables

    def test_create_table_as_select(self):
        sql = "CREATE TABLE analytics.revenue AS SELECT region, SUM(amount) FROM public.orders GROUP BY region"
        result = self.parser.parse(sql)
        assert len(result["target_tables"]) == 1
        assert result["target_tables"][0].table == "revenue"

    def test_cte_detection(self):
        sql = "WITH ranked AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY id) as rn FROM public.orders) SELECT * FROM ranked WHERE rn = 1"
        result = self.parser.parse(sql)
        assert len(result["ctes"]) == 1
        assert result["ctes"][0] == "ranked"

    def test_transformation_inference(self):
        parser = SQLLineageParser()
        assert parser._infer_transformation("SELECT * FROM t") == "select"
        assert parser._infer_transformation("SELECT * FROM t GROUP BY col") == "aggregate"
        assert parser._infer_transformation("SELECT * FROM t1 UNION SELECT * FROM t2") == "union"
        assert parser._infer_transformation("SELECT * FROM t1 JOIN t2 ON t1.id = t2.id") == "join"

    def test_backtick_table_refs(self):
        sql = "SELECT * FROM `project`.`dataset`.`table`"
        result = self.parser.parse(sql)
        assert result["source_tables"][0].database == "project"
        assert result["source_tables"][0].schema == "dataset"
        assert result["source_tables"][0].table == "table"

    def test_batch_parsing(self):
        queries = [
            "INSERT INTO staging.stg_orders SELECT * FROM public.orders",
            "INSERT INTO staging.stg_customers SELECT * FROM public.customers",
        ]
        result = self.parser.parse_batch(queries)
        assert result["query_count"] == 2
        assert len(result["all_source_tables"]) == 2
        assert len(result["all_target_tables"]) == 2
        assert len(result["all_edges"]) == 2


class TestTableRef:
    """Test TableRef model."""

    def test_full_name_three_parts(self):
        ref = TableRef(database="db", schema="schema", table="table")
        assert ref.full_name == "db.schema.table"

    def test_full_name_two_parts(self):
        ref = TableRef(schema="public", table="orders")
        assert ref.full_name == "public.orders"

    def test_full_name_one_part(self):
        ref = TableRef(table="orders")
        assert ref.full_name == "orders"

    def test_display_name(self):
        ref = TableRef(schema="public", table="orders")
        assert ref.display_name == "orders"


class TestDbtManifestParser:
    """Test dbt manifest parsing."""

    def test_parse_manifest(self):
        manifest = {
            "nodes": {
                "model.jaffle.stg_orders": {
                    "name": "stg_orders",
                    "resource_type": "model",
                    "database": "analytics",
                    "schema": "staging",
                    "config": {"materialized": "view"},
                    "depends_on": {"nodes": ["source.jaffle.raw_orders"]},
                    "columns": {"id": {}, "status": {}},
                    "tags": [],
                    "package_name": "jaffle",
                    "path": "models/staging/stg_orders.sql",
                },
            },
            "sources": {
                "source.jaffle.raw_orders": {
                    "name": "raw_orders",
                    "source_name": "jaffle",
                    "database": "raw",
                    "schema": "jaffle",
                    "columns": {"id": {}, "amount": {}},
                    "tags": [],
                    "loader": "airbyte",
                },
            },
        }
        parser = DbtManifestParser()
        lineage = parser.parse_manifest(manifest)

        assert len(lineage.nodes) == 2
        assert len(lineage.models) == 1
        assert len(lineage.sources) == 1
        assert len(lineage.edges) == 1
        assert lineage.edges[0] == ("source.jaffle.raw_orders", "model.jaffle.stg_orders")

    def test_parse_file_not_found(self):
        parser = DbtManifestParser()
        lineage = parser.parse_file("/nonexistent/path.json")
        assert len(lineage.nodes) == 0

    def test_get_lineage_dict(self):
        manifest = {
            "nodes": {
                "model.test.my_model": {
                    "name": "my_model",
                    "resource_type": "model",
                    "database": "db",
                    "schema": "schema",
                    "config": {"materialized": "table"},
                    "depends_on": {"nodes": []},
                    "columns": {},
                    "tags": [],
                },
            },
            "sources": {},
        }
        parser = DbtManifestParser()
        lineage = parser.parse_manifest(manifest)
        result = parser.get_lineage_dict(lineage)
        assert "nodes" in result
        assert "edges" in result
        assert "summary" in result
        assert result["summary"]["total_nodes"] == 1


class TestGraphIngestionService:
    """Test graph ingestion service (with mocked DB)."""

    @pytest.mark.asyncio
    async def test_upsert_node_creates(self):
        from apps.api.app.services.graph_ingestion import GraphIngestionService
        from apps.api.app.db.models import ReliabilityNode

        mock_db = AsyncMock()
        org_id = uuid4()

        # Mock _find_node to return None (no existing node)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        service = GraphIngestionService(mock_db, org_id)
        node = await service.upsert_node(
            node_type="table",
            name="test_table",
            external_id="table:test_table",
            metadata={"source": "test"},
        )

        assert isinstance(node, ReliabilityNode)
        assert node.name == "test_table"
        assert node.node_type == "table"
        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_upsert_node_idempotent(self):
        from apps.api.app.services.graph_ingestion import GraphIngestionService
        from apps.api.app.db.models import ReliabilityNode
        from unittest.mock import MagicMock

        mock_db = AsyncMock()
        org_id = uuid4()

        # Mock existing node
        existing_node = MagicMock(spec=ReliabilityNode)
        existing_node.extra_data = {"old": "data"}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_node

        # First call = _find_node, second+ = not used
        mock_db.execute.return_value = mock_result

        service = GraphIngestionService(mock_db, org_id)
        node = await service.upsert_node(
            node_type="table",
            name="test_table",
            external_id="table:test_table",
            metadata={"new": "data"},
        )

        # Should update existing, not create new
        assert node.extra_data == {"old": "data", "new": "data"}
        mock_db.add.assert_not_called()


class TestGraphVersioningService:
    """Test graph versioning (with mocked DB)."""

    @pytest.mark.asyncio
    async def test_create_version_empty_graph(self):
        from apps.api.app.services.graph_versioning import GraphVersioningService

        mock_db = AsyncMock()
        org_id = uuid4()

        # Mock empty results for nodes, edges, and latest version
        mock_nodes = MagicMock()
        mock_nodes.scalars.return_value.all.return_value = []
        mock_edges = MagicMock()
        mock_edges.scalars.return_value.all.return_value = []
        mock_version = MagicMock()
        mock_version.scalar_one_or_none.return_value = None

        mock_db.execute.side_effect = [mock_nodes, mock_edges, mock_version]

        service = GraphVersioningService(mock_db, org_id)
        result = await service.create_version(description="Initial")

        assert result["version_number"] == "1.0.0"
        assert result["total_nodes"] == 0
        assert result["changed"] is True

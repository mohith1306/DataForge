"""Tests for Reliability Graph Service."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone

from apps.api.app.services.reliability_graph import ReliabilityGraphService


def _make_mock_node(**overrides):
    """Create a mock node with defaults."""
    defaults = {
        "id": uuid4(),
        "org_id": uuid4(),
        "project_id": None,
        "node_type": "table",
        "name": "test_node",
        "external_id": None,
        "extra_data": {},
        "owner_id": None,
        "business_criticality": "medium",
        "reliability_score": 100.0,
        "last_incident_at": None,
        "last_updated": datetime.now(timezone.utc),
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    node = MagicMock(**defaults)
    return node


def _make_mock_edge(**overrides):
    """Create a mock edge with defaults."""
    defaults = {
        "id": uuid4(),
        "source_id": uuid4(),
        "target_id": uuid4(),
        "edge_type": "dependency",
        "extra_data": {},
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    edge = MagicMock(**defaults)
    return edge


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    db = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()
    db.delete = AsyncMock()
    return db


@pytest.fixture
def graph_service(mock_db):
    """Create a ReliabilityGraphService with mocked database."""
    org_id = uuid4()
    return ReliabilityGraphService(mock_db, org_id)


@pytest.mark.asyncio
async def test_add_node(graph_service, mock_db):
    """Test adding a node to the graph."""
    node = await graph_service.add_node(
        node_type="table",
        name="test_table",
        metadata={"columns": ["id", "name"]},
    )

    assert mock_db.add.called
    assert mock_db.flush.called
    assert mock_db.refresh.called


@pytest.mark.asyncio
async def test_get_node(graph_service, mock_db):
    """Test getting a node by ID."""
    mock_node = _make_mock_node()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_node
    mock_db.execute.return_value = mock_result

    result = await graph_service.get_node(uuid4())

    assert result == mock_node
    assert mock_db.execute.called


@pytest.mark.asyncio
async def test_get_node_not_found(graph_service, mock_db):
    """Test getting a non-existent node."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    result = await graph_service.get_node(uuid4())

    assert result is None


@pytest.mark.asyncio
async def test_list_nodes(graph_service, mock_db):
    """Test listing nodes with filters."""
    mock_nodes = [_make_mock_node() for _ in range(3)]
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = mock_nodes
    mock_db.execute.return_value = mock_result

    result = await graph_service.list_nodes()

    assert len(result) == 3
    assert mock_db.execute.called


@pytest.mark.asyncio
async def test_delete_node(graph_service, mock_db):
    """Test deleting a node."""
    mock_node = _make_mock_node()
    mock_get_result = MagicMock()
    mock_get_result.scalar_one_or_none.return_value = mock_node

    mock_delete_result = MagicMock()

    # First call returns node, second call returns for delete query
    mock_db.execute.side_effect = [mock_get_result, mock_delete_result]

    success = await graph_service.delete_node(mock_node.id)

    assert success is True
    assert mock_db.delete.called
    assert mock_db.flush.called


@pytest.mark.asyncio
async def test_add_edge(graph_service, mock_db):
    """Test adding an edge between nodes."""
    node1 = _make_mock_node()
    node2 = _make_mock_node()

    # Mock get_node calls
    mock_result1 = MagicMock()
    mock_result1.scalar_one_or_none.return_value = node1

    mock_result2 = MagicMock()
    mock_result2.scalar_one_or_none.return_value = node2

    # Mock duplicate check
    mock_duplicate = MagicMock()
    mock_duplicate.scalar_one_or_none.return_value = None

    mock_db.execute.side_effect = [mock_result1, mock_result2, mock_duplicate]

    edge = await graph_service.add_edge(
        source_id=node1.id,
        target_id=node2.id,
        edge_type="dependency",
    )

    assert mock_db.add.called
    assert mock_db.flush.called


@pytest.mark.asyncio
async def test_add_edge_self_reference(graph_service, mock_db):
    """Test that self-referencing edges are rejected."""
    node = _make_mock_node()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = node
    mock_db.execute.return_value = mock_result

    with pytest.raises(ValueError, match="self-referencing"):
        await graph_service.add_edge(
            source_id=node.id,
            target_id=node.id,
            edge_type="dependency",
        )


@pytest.mark.asyncio
async def test_add_edge_node_not_found(graph_service, mock_db):
    """Test adding edge when node not found."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    with pytest.raises(ValueError, match="not found"):
        await graph_service.add_edge(
            source_id=uuid4(),
            target_id=uuid4(),
            edge_type="dependency",
        )


@pytest.mark.asyncio
async def test_calculate_blast_radius(graph_service, mock_db):
    """Test blast radius calculation."""
    # Create mock nodes for downstream
    source = _make_mock_node(node_type="source", business_criticality="critical")
    table1 = _make_mock_node(node_type="table")
    dashboard = _make_mock_node(node_type="dashboard", business_criticality="high")

    # Mock get_node for source
    mock_source_result = MagicMock()
    mock_source_result.scalar_one_or_none.return_value = source

    # Mock get_downstream - return edges from source
    edge1 = _make_mock_edge(source_id=source.id, target_id=table1.id)
    edge2 = _make_mock_edge(source_id=table1.id, target_id=dashboard.id)

    mock_edges_result = MagicMock()
    mock_edges_result.scalars.return_value.all.return_value = [edge1, edge2]

    # Mock get_node for table1 and dashboard
    mock_table_result = MagicMock()
    mock_table_result.scalar_one_or_none.return_value = table1

    mock_dashboard_result = MagicMock()
    mock_dashboard_result.scalar_one_or_none.return_value = dashboard

    # Setup mock to return different results for each call
    call_count = [0]

    async def mock_execute(query):
        call_count[0] += 1
        if call_count[0] == 1:
            return mock_source_result  # get_node for source
        elif call_count[0] == 2:
            return mock_edges_result  # get_downstream edges
        elif call_count[0] == 3:
            return mock_table_result  # get_node for table1
        elif call_count[0] == 4:
            return mock_edges_result  # get_downstream edges for table1
        elif call_count[0] == 5:
            return mock_dashboard_result  # get_node for dashboard
        return MagicMock()

    mock_db.execute = mock_execute

    blast = await graph_service.calculate_blast_radius(source.id)

    # Verify the structure of the result
    assert "total_affected" in blast
    assert "business_impact" in blast
    assert "affected_nodes" in blast
    assert "affected_business_processes" in blast


@pytest.mark.asyncio
async def test_graph_stats(graph_service, mock_db):
    """Test graph statistics."""
    mock_nodes = [_make_mock_node() for _ in range(2)]
    mock_edges = [_make_mock_edge() for _ in range(1)]

    mock_nodes_result = MagicMock()
    mock_nodes_result.scalars.return_value.all.return_value = mock_nodes

    mock_edges_result = MagicMock()
    mock_edges_result.scalars.return_value.all.return_value = mock_edges

    mock_db.execute.side_effect = [mock_nodes_result, mock_edges_result]

    stats = await graph_service.get_graph_stats()

    assert stats["total_nodes"] == 2
    assert stats["total_edges"] == 1
    assert "average_reliability_score" in stats

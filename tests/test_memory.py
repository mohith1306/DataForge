"""Tests for Incident Memory."""
import pytest
from apps.api.app.execution.memory import IncidentMemory, FailureDNA


def test_memory_initialization():
    """Test IncidentMemory initialization."""
    memory = IncidentMemory()
    
    stats = memory.get_memory_stats()
    assert stats["total_incidents"] == 0
    assert stats["failure_patterns"] == 0


def test_store_incident():
    """Test storing an incident."""
    memory = IncidentMemory()
    
    record = memory.store_incident(
        incident_id="INC-001",
        title="Database connection timeout",
        description="Connection pool exhausted",
        severity="high",
        category="database",
        error_signatures=["connection_timeout", "pool_exhausted"],
        affected_services=["api", "worker"],
    )
    
    assert record.incident_id == "INC-001"
    assert record.failure_dna is not None
    assert record.failure_dna.category == "database"


def test_get_incident():
    """Test getting an incident."""
    memory = IncidentMemory()
    
    record = memory.store_incident(
        incident_id="INC-002",
        title="Test incident",
        description="Test description",
        severity="low",
        category="test",
    )
    
    retrieved = memory.get_incident(record.id)
    assert retrieved is not None
    assert retrieved.incident_id == "INC-002"


def test_find_similar_incidents():
    """Test finding similar incidents."""
    memory = IncidentMemory()
    
    # Store incidents
    memory.store_incident(
        incident_id="INC-003",
        title="DB timeout 1",
        description="Description",
        severity="high",
        category="database",
        error_signatures=["connection_timeout"],
    )
    
    memory.store_incident(
        incident_id="INC-004",
        title="DB timeout 2",
        description="Description",
        severity="high",
        category="database",
        error_signatures=["connection_timeout"],
    )
    
    # Find similar
    similar = memory.find_similar_incidents(
        error_signatures=["connection_timeout"],
        category="database",
    )
    
    assert len(similar) >= 2


def test_get_by_category():
    """Test getting incidents by category."""
    memory = IncidentMemory()
    
    memory.store_incident(
        incident_id="INC-005",
        title="DB incident",
        description="Description",
        severity="high",
        category="database",
    )
    
    memory.store_incident(
        incident_id="INC-006",
        title="Network incident",
        description="Description",
        severity="medium",
        category="network",
    )
    
    db_incidents = memory.get_by_category("database")
    assert len(db_incidents) == 1
    assert db_incidents[0].category == "database"


def test_get_by_service():
    """Test getting incidents by service."""
    memory = IncidentMemory()
    
    memory.store_incident(
        incident_id="INC-007",
        title="API incident",
        description="Description",
        severity="high",
        category="database",
        affected_services=["api", "worker"],
    )
    
    api_incidents = memory.get_by_service("api")
    assert len(api_incidents) == 1


def test_resolve_incident():
    """Test resolving an incident."""
    memory = IncidentMemory()
    
    record = memory.store_incident(
        incident_id="INC-008",
        title="Resolvable incident",
        description="Description",
        severity="low",
        category="test",
    )
    
    success = memory.resolve_incident(
        record.id,
        resolution="Restarted service",
        resolution_steps=[{"step": "Restart", "status": "completed"}],
    )
    
    assert success is True
    
    # Verify resolution
    incident = memory.get_incident(record.id)
    assert incident.resolution == "Restarted service"
    assert incident.resolved_at is not None


def test_get_resolution_patterns():
    """Test getting resolution patterns."""
    memory = IncidentMemory()
    
    # Store multiple incidents with same resolution
    for i in range(3):
        record = memory.store_incident(
            incident_id=f"INC-PATTERN-{i}",
            title="Pattern incident",
            description="Description",
            severity="medium",
            category="database",
        )
        memory.resolve_incident(record.id, resolution="Restarted service")
    
    patterns = memory.get_resolution_patterns("database")
    assert len(patterns) > 0
    assert patterns[0]["resolution"] == "Restarted service"
    assert patterns[0]["count"] == 3


def test_generate_failure_dna():
    """Test failure DNA generation."""
    memory = IncidentMemory()
    
    dna = memory.generate_failure_dna(
        error_signatures=["error1", "error2"],
        category="database",
        severity="high",
    )
    
    assert isinstance(dna, FailureDNA)
    assert dna.hash is not None
    assert dna.fingerprint.startswith("database:high:")


def test_memory_export_import():
    """Test memory export and import."""
    memory1 = IncidentMemory()
    
    memory1.store_incident(
        incident_id="INC-EXPORT",
        title="Export test",
        description="Description",
        severity="low",
        category="test",
    )
    
    # Export
    exported = memory1.export_memory()
    assert "incidents" in exported
    
    # Import
    memory2 = IncidentMemory()
    memory2.import_memory(exported)
    
    assert memory2.get_memory_stats()["total_incidents"] == 1


def test_memory_stats():
    """Test memory statistics."""
    memory = IncidentMemory()
    
    memory.store_incident(
        incident_id="INC-STATS-1",
        title="Stats test 1",
        description="Description",
        severity="high",
        category="database",
        affected_services=["api"],
    )
    
    memory.store_incident(
        incident_id="INC-STATS-2",
        title="Stats test 2",
        description="Description",
        severity="medium",
        category="network",
        affected_services=["worker"],
    )
    
    stats = memory.get_memory_stats()
    assert stats["total_incidents"] == 2
    assert "database" in stats["categories"]
    assert "network" in stats["categories"]
    assert "api" in stats["services"]
    assert "worker" in stats["services"]

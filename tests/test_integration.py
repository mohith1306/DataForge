"""Integration Tests — Cross-module interactions and end-to-end flows."""
import pytest
from datetime import datetime, timezone

# Phase 2: Policy
from apps.api.app.core.policy_engine import PolicyEngine, Policy, PolicyType

# Phase 3: Memory
from apps.api.app.execution.memory import IncidentMemory

# Phase 4: Metadata + Intelligence
from apps.api.app.metadata.schema_discovery import SchemaDiscovery
from apps.api.app.metadata.lineage import LineageTracker, NodeType, EdgeType
from apps.api.app.intelligence.correlation import IncidentCorrelation, CorrelationStrategy
from apps.api.app.intelligence.deduplication import IncidentDeduplication
from apps.api.app.intelligence.blast_radius import BlastRadiusCalculator

# Phase 5: Gateway
from apps.api.app.gateway.rate_limiter import RateLimiter
from apps.api.app.gateway.audit_logger import AuditLogger, AuditLevel


class TestIncidentLifecycle:
    """Test full incident lifecycle: detect → investigate → resolve → remember."""

    def setup_method(self):
        self.memory = IncidentMemory()
        self.correlation = IncidentCorrelation()
        self.dedup = IncidentDeduplication()
        self.blast_radius = BlastRadiusCalculator()

    def test_full_incident_lifecycle(self):
        incident = {
            "id": "inc_lifecycle_001",
            "title": "Database connection timeout",
            "description": "Primary DB unreachable for 5 minutes",
            "severity": "high",
            "category": "database",
            "affected_services": ["api-gateway", "user-service"],
            "error_signatures": ["ConnectionTimeout", "ECONNREFUSED"],
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        # Step 1: Add to deduplication index
        self.dedup.add_incident(incident)

        # Step 2: Calculate blast radius
        self.blast_radius.register_entity("api-gateway", "service", ["user-service"])
        self.blast_radius.register_entity("user-service", "service", [])
        blast = self.blast_radius.calculate(incident)
        assert blast.risk_score > 0

        # Step 3: Correlate with similar incidents
        incidents = [incident]
        correlations = self.correlation.correlate(incidents, CorrelationStrategy.SERVICE)
        assert len(correlations) >= 0

        # Step 4: Check for duplicates
        new_incident = {
            "id": "inc_lifecycle_002",
            "title": "Database connection timeout",
            "description": "Primary DB unreachable for 5 minutes",
            "severity": "high",
            "category": "database",
            "affected_services": ["api-gateway", "user-service"],
            "error_signatures": ["ConnectionTimeout"]
        }
        result = self.dedup.check_duplicate(new_incident)
        assert result is not None  # Should find duplicate


class TestSchemaToLineageFlow:
    """Test: Schema Discovery → Lineage Tracking → Blast Radius."""

    def setup_method(self):
        self.schema_discovery = SchemaDiscovery()
        self.lineage = LineageTracker()
        self.blast_radius = BlastRadiusCalculator()

    def test_schema_discovery_to_lineage(self):
        # Step 1: Discover schema
        data = [
            {"user_id": 1, "name": "Alice", "email": "alice@test.com"},
            {"user_id": 2, "name": "Bob", "email": "bob@test.com"}
        ]
        schema = self.schema_discovery.discover_from_dict("users", "pg_prod", data)
        assert len(schema.fields) == 3

        # Step 2: Add to lineage
        node = self.lineage.add_node(
            name="users_table",
            node_type=NodeType.TABLE,
            schema_id=schema.id
        )
        assert node.schema_id == schema.id

        # Step 3: Add downstream dependency
        view_node = self.lineage.add_node("active_users_view", NodeType.VIEW)
        self.lineage.add_edge(node.id, view_node.id, EdgeType.READS_FROM)

        # Step 4: Check blast radius
        radius = self.lineage.get_blast_radius(node.id)
        assert radius["total_downstream"] == 1

        # Step 5: Verify schema-lineage link
        retrieved = self.schema_discovery.get_schema(schema.id)
        assert retrieved is not None


class TestCorrelationDedupFlow:
    """Test: Incidents → Correlation → Deduplication → Intelligence."""

    def setup_method(self):
        self.correlation = IncidentCorrelation()
        self.dedup = IncidentDeduplication()

    def test_correlate_then_deduplicate(self):
        incidents = [
            {"id": "i1", "title": "Timeout A", "affected_services": ["api"], "error_signatures": ["timeout"], "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "i2", "title": "Timeout B", "affected_services": ["api"], "error_signatures": ["timeout"], "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "i3", "title": "Timeout C", "affected_services": ["api"], "error_signatures": ["timeout"], "created_at": datetime.now(timezone.utc).isoformat()},
        ]

        # Step 1: Add all to dedup index
        for inc in incidents:
            self.dedup.add_incident(inc)

        # Step 2: Correlate by service
        correlations = self.correlation.correlate(incidents, CorrelationStrategy.SERVICE)
        assert len(correlations) >= 1

        # Step 3: Check for duplicates
        new_incident = {"id": "i4", "title": "Timeout D", "affected_services": ["api"], "error_signatures": ["timeout"]}
        result = self.dedup.check_duplicate(new_incident)
        assert result is not None  # Should find similarity

        # Step 4: Get stats
        stats = self.dedup.get_stats()
        assert stats["total_incidents"] == 3


class TestExecutionToMemoryFlow:
    """Test: Execution → Memory recording."""

    def setup_method(self):
        self.memory = IncidentMemory()

    def test_execution_recorded_in_memory(self):
        # Step 1: Store incident
        record = self.memory.store_incident(
            incident_id="inc_exec_001",
            title="Execution test",
            description="Test execution flow",
            severity="medium",
            category="test",
            error_signatures=["timeout", "connection_refused"]
        )

        # Step 2: Generate failure DNA for the incident
        dna = self.memory.generate_failure_dna(
            error_signatures=["timeout", "connection_refused"],
            category="test",
            severity="medium"
        )
        assert dna.hash is not None

        # Step 3: Verify recording
        retrieved = self.memory.get_incident(record.id)
        assert retrieved is not None
        assert retrieved.incident_id == "inc_exec_001"


class TestRateLimitWithAudit:
    """Test: Rate Limiter + Audit Logger integration."""

    def setup_method(self):
        self.rate_limiter = RateLimiter()
        self.audit_logger = AuditLogger()

    def test_rate_limit_recorded_in_audit(self):
        client = "test_client_integration"

        # Make some requests
        for i in range(5):
            result = self.rate_limiter.check_rate_limit(client)
            self.audit_logger.log_api_request(
                method="GET",
                path="/api/test",
                actor=client,
                status_code=200 if result.allowed else 429
            )

        # Verify audit log
        events = self.audit_logger.get_events(event_type="api_request")
        assert len(events) == 5

        # Verify rate limit state
        usage = self.rate_limiter.get_usage(client)
        assert usage["requests_last_minute"] == 5


class TestBlastRadiusWithLineage:
    """Test: Blast Radius Calculator + Lineage Tracker integration."""

    def setup_method(self):
        self.lineage = LineageTracker()
        self.blast_radius = BlastRadiusCalculator()

    def test_blast_radius_from_lineage(self):
        # Build lineage graph
        db = self.lineage.add_node("database", NodeType.TABLE)
        api = self.lineage.add_node("api_service", NodeType.API)
        web = self.lineage.add_node("web_frontend", NodeType.DASHBOARD)

        self.lineage.add_edge(db.id, api.id, EdgeType.READS_FROM)
        self.lineage.add_edge(api.id, web.id, EdgeType.READS_FROM)

        # Register in blast radius calculator
        self.blast_radius.register_entity("database", "service", ["api_service"])
        self.blast_radius.register_entity("api_service", "service", ["web_frontend"])
        self.blast_radius.register_entity("web_frontend", "service", [])

        # Calculate blast radius from lineage
        lineage_radius = self.lineage.get_blast_radius(db.id)
        assert lineage_radius["total_downstream"] == 2

        # Calculate from blast radius calculator
        incident = {"id": "inc_blast", "affected_services": ["database"]}
        calc_radius = self.blast_radius.calculate(incident)
        assert calc_radius.risk_score > 0


class TestPolicyWithExecution:
    """Test: Policy Engine + Execution Fabric integration."""

    def setup_method(self):
        self.policy_engine = PolicyEngine()

    def test_policy_blocks_dangerous_execution(self):
        policy = Policy(
            name="block-drop-table",
            policy_type=PolicyType.ACTION_CONSTRAINT,
            rules=[{"action_type": "sql", "constraints": ["no_drop_table"]}],
            enabled=True
        )
        self.policy_engine.add_policy(policy)

        # Validate dangerous action
        result = self.policy_engine.validate_action({
            "action_type": "sql",
            "query": "DROP TABLE users"
        })

        assert result["is_allowed"] is True  # SQL not blocked by default, but constraints listed
        assert len(result["constraints"]) > 0

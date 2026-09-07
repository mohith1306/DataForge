"""Runtime Tests — Performance, load, and stress testing."""
import pytest
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

from apps.api.app.gateway.rate_limiter import RateLimiter, RateLimitConfig
from apps.api.app.gateway.audit_logger import AuditLogger
from apps.api.app.gateway.request_validator import RequestValidator
from apps.api.app.intelligence.correlation import IncidentCorrelation, CorrelationStrategy
from apps.api.app.intelligence.deduplication import IncidentDeduplication
from apps.api.app.intelligence.blast_radius import BlastRadiusCalculator
from apps.api.app.metadata.schema_discovery import SchemaDiscovery
from apps.api.app.metadata.lineage import LineageTracker, NodeType, EdgeType
from apps.api.app.execution.memory import IncidentMemory
from apps.api.app.core.policy_engine import PolicyEngine, Policy, PolicyType


class TestRateLimiterPerformance:
    def test_high_volume_rate_limit_check(self):
        limiter = RateLimiter(RateLimitConfig(requests_per_minute=10000))
        start = time.time()
        for i in range(10000):
            limiter.check_rate_limit(f"client_{i % 100}")
        elapsed = time.time() - start
        assert elapsed < 5.0

    def test_concurrent_rate_limit_checks(self):
        limiter = RateLimiter(RateLimitConfig(requests_per_minute=1000))
        results = []

        def check_limit(client_id):
            return limiter.check_rate_limit(client_id)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(check_limit, f"client_{i}") for i in range(1000)]
            for f in as_completed(futures):
                results.append(f.result())

        allowed = sum(1 for r in results if r.allowed)
        assert allowed > 0

    def test_rate_limit_memory_usage(self):
        limiter = RateLimiter()
        for i in range(10000):
            limiter.check_rate_limit(f"client_{i}")
        assert len(limiter.requests) <= 10000


class TestAuditLoggerPerformance:
    def test_high_volume_logging(self):
        logger = AuditLogger()
        start = time.time()
        for i in range(10000):
            logger.log_api_request(
                method="GET", path=f"/api/test/{i}",
                actor=f"user_{i % 50}", status_code=200
            )
        elapsed = time.time() - start
        assert elapsed < 5.0
        assert len(logger.events) == 10000

    def test_concurrent_logging(self):
        logger = AuditLogger()
        results = []

        def log_event(idx):
            return logger.log_api_request(
                method="GET", path=f"/api/concurrent/{idx}",
                actor=f"user_{idx}", status_code=200
            )

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(log_event, i) for i in range(1000)]
            for f in as_completed(futures):
                results.append(f.result())

        assert len(results) == 1000

    def test_audit_query_performance(self):
        logger = AuditLogger()
        for i in range(5000):
            logger.log_api_request(
                method="GET", path=f"/api/query/{i}",
                actor=f"user_{i % 100}", status_code=200
            )
        start = time.time()
        events = logger.get_events(actor="user_50")
        elapsed = time.time() - start
        assert elapsed < 1.0
        assert len(events) > 0


class TestRequestValidatorPerformance:
    def test_high_volume_validation(self):
        validator = RequestValidator()
        start = time.time()
        for i in range(10000):
            validator.validate_request(
                method="POST", path="/api/test",
                headers={"content-type": "application/json"},
                body={"id": i, "name": f"test_{i}"}
            )
        elapsed = time.time() - start
        assert elapsed < 5.0


class TestCorrelationPerformance:
    def test_correlate_large_dataset(self):
        correlation = IncidentCorrelation()
        incidents = [
            {
                "id": f"inc_{i}",
                "affected_services": [f"service_{i % 10}"],
                "error_signatures": [f"error_{i % 5}"],
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            for i in range(1000)
        ]
        start = time.time()
        results = correlation.correlate(incidents, CorrelationStrategy.SERVICE)
        elapsed = time.time() - start
        assert elapsed < 5.0


class TestDeduplicationPerformance:
    def test_dedup_large_dataset(self):
        dedup = IncidentDeduplication()
        for i in range(1000):
            dedup.add_incident({
                "id": f"inc_{i}",
                "error_signatures": [f"error_{i % 20}"],
                "affected_services": [f"service_{i % 10}"],
                "title": f"Incident {i}",
                "description": f"Description {i}"
            })

        start = time.time()
        for i in range(100):
            dedup.check_duplicate({
                "id": f"new_{i}",
                "error_signatures": [f"error_{i % 20}"],
                "affected_services": [f"service_{i % 10}"],
                "title": f"New Incident {i}",
                "description": f"New Description {i}"
            })
        elapsed = time.time() - start
        assert elapsed < 5.0


class TestBlastRadiusPerformance:
    def test_blast_radius_large_graph(self):
        calc = BlastRadiusCalculator()
        for i in range(500):
            deps = [f"entity_{j}" for j in range(max(0, i-5), i)]
            calc.register_entity(f"entity_{i}", "service", deps)

        start = time.time()
        for i in range(0, 500, 50):
            calc.calculate({"id": f"inc_{i}", "affected_services": [f"entity_{i}"]})
        elapsed = time.time() - start
        assert elapsed < 5.0


class TestLineagePerformance:
    def test_large_lineage_graph(self):
        tracker = LineageTracker()
        nodes = []
        for i in range(500):
            node = tracker.add_node(f"node_{i}", NodeType.TABLE)
            nodes.append(node)

        start = time.time()
        for i in range(1, 500):
            tracker.add_edge(nodes[i-1].id, nodes[i].id, EdgeType.READS_FROM)
        elapsed_edges = time.time() - start

        start = time.time()
        downstream = tracker.get_downstream(nodes[0].id)
        elapsed_query = time.time() - start

        assert elapsed_edges < 5.0
        assert elapsed_query < 2.0
        assert len(downstream) == 499


class TestSchemaDiscoveryPerformance:
    def test_discover_large_dataset(self):
        discovery = SchemaDiscovery()
        data = [
            {"id": i, "name": f"user_{i}", "email": f"user_{i}@test.com", "score": i * 1.5}
            for i in range(10000)
        ]
        start = time.time()
        schema = discovery.discover_from_dict("large_table", "pg_prod", data)
        elapsed = time.time() - start
        assert elapsed < 5.0
        assert len(schema.fields) == 4


class TestMemoryPerformance:
    def test_record_many_incidents(self):
        memory = IncidentMemory()
        start = time.time()
        for i in range(1000):
            memory.store_incident(
                incident_id=f"inc_{i}", title=f"Incident {i}",
                description=f"Description {i}", severity="medium",
                category=f"cat_{i % 10}"
            )
        elapsed = time.time() - start
        assert elapsed < 5.0

    def test_generate_failure_dna(self):
        memory = IncidentMemory()
        start = time.time()
        for i in range(1000):
            memory.generate_failure_dna(
                error_signatures=[f"error_{i % 10}"],
                category=f"cat_{i % 10}",
                severity="high"
            )
        elapsed = time.time() - start
        assert elapsed < 5.0


class TestPolicyEnginePerformance:
    def test_evaluate_many_actions(self):
        engine = PolicyEngine()
        policy = Policy(
            name="risk-check",
            policy_type=PolicyType.RISK_CLASSIFICATION,
            rules=[{"risk_level": "high", "action_types": ["deploy", "migration"]}],
            enabled=True
        )
        engine.add_policy(policy)

        start = time.time()
        for i in range(10000):
            engine.evaluate_risk({"action_type": "deploy", "target": "prod"})
        elapsed = time.time() - start
        assert elapsed < 5.0

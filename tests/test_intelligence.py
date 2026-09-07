"""Tests for Incident Intelligence — Correlation, Deduplication, Blast Radius."""
import pytest
from datetime import datetime, timezone
from apps.api.app.intelligence.correlation import IncidentCorrelation, CorrelationStrategy
from apps.api.app.intelligence.deduplication import IncidentDeduplication, DeduplicationStrategy
from apps.api.app.intelligence.blast_radius import BlastRadiusCalculator


class TestIncidentCorrelation:
    """Tests for IncidentCorrelation."""

    def setup_method(self):
        self.correlation = IncidentCorrelation()

    def test_correlate_by_service(self):
        incidents = [
            {"id": "i1", "affected_services": ["api-gateway"], "error_signatures": ["err1"]},
            {"id": "i2", "affected_services": ["api-gateway"], "error_signatures": ["err2"]},
            {"id": "i3", "affected_services": ["database"], "error_signatures": ["err3"]},
        ]
        results = self.correlation.correlate(incidents, CorrelationStrategy.SERVICE)
        assert len(results) >= 1
        gateway_group = [r for r in results if "api-gateway" in r.metadata.get("service", "")]
        assert len(gateway_group) == 1
        assert len(gateway_group[0].incident_ids) == 2

    def test_correlate_by_error_type(self):
        incidents = [
            {"id": "i1", "error_signatures": ["timeout_error"]},
            {"id": "i2", "error_signatures": ["timeout_error"]},
            {"id": "i3", "error_signatures": ["connection_error"]},
        ]
        results = self.correlation.correlate(incidents, CorrelationStrategy.ERROR_TYPE)
        assert len(results) >= 1

    def test_correlate_by_time_window(self):
        now = datetime.now(timezone.utc)
        incidents = [
            {"id": "i1", "created_at": now.isoformat(), "affected_services": [], "error_signatures": []},
            {"id": "i2", "created_at": now.isoformat(), "affected_services": [], "error_signatures": []},
        ]
        results = self.correlation.correlate(incidents, CorrelationStrategy.TIME_WINDOW)
        assert len(results) >= 1

    def test_correlate_by_failure_dna(self):
        dna = {"hash": "abc123", "components": ["timeout"], "severity": "high", "category": "perf", "fingerprint": "fp1"}
        incidents = [
            {"id": "i1", "failure_dna": dna, "affected_services": [], "error_signatures": []},
            {"id": "i2", "failure_dna": dna, "affected_services": [], "error_signatures": []},
        ]
        results = self.correlation.correlate(incidents, CorrelationStrategy.FAILURE_DNA)
        assert len(results) == 1
        assert len(results[0].incident_ids) == 2

    def test_merge_correlations(self):
        c1 = self.correlation.add_correlation_result("g1", ["i1", "i2"])
        c2 = self.correlation.add_correlation_result("g2", ["i2", "i3"])
        merged = self.correlation.merge_correlations([c1.id, c2.id])
        assert len(merged.incident_ids) == 3


class TestIncidentDeduplication:
    """Tests for IncidentDeduplication."""

    def setup_method(self):
        self.dedup = IncidentDeduplication()

    def test_exact_match(self):
        incident = {"id": "i1", "title": "DB Down", "description": "Primary DB unreachable", "affected_services": ["api"], "error_signatures": ["e1"]}
        self.dedup.add_incident(incident)
        duplicate = {"id": "i2", "title": "DB Down", "description": "Primary DB unreachable", "affected_services": ["api"], "error_signatures": ["e1"]}
        result = self.dedup.check_duplicate(duplicate, DeduplicationStrategy.EXACT_MATCH)
        assert result is not None
        assert result.original_incident_id == "i1"

    def test_signature_match(self):
        incident = {"id": "i1", "error_signatures": ["ConnectionRefused"], "affected_services": [], "title": "", "description": ""}
        self.dedup.add_incident(incident)
        duplicate = {"id": "i2", "error_signatures": ["ConnectionRefused"], "affected_services": [], "title": "", "description": ""}
        result = self.dedup.check_duplicate(duplicate, DeduplicationStrategy.SIGNATURE_MATCH)
        assert result is not None

    def test_no_duplicate(self):
        incident = {"id": "i1", "error_signatures": ["errA"], "affected_services": [], "title": "", "description": ""}
        self.dedup.add_incident(incident)
        unique = {"id": "i2", "error_signatures": ["errB"], "affected_services": [], "title": "", "description": ""}
        result = self.dedup.check_duplicate(unique, DeduplicationStrategy.SIGNATURE_MATCH)
        assert result is None

    def test_dedup_stats(self):
        self.dedup.add_incident({"id": "i1", "error_signatures": ["e1"], "affected_services": [], "title": "", "description": ""})
        stats = self.dedup.get_stats()
        assert stats["total_incidents"] == 1


class TestBlastRadiusCalculator:
    """Tests for BlastRadiusCalculator."""

    def setup_method(self):
        self.calculator = BlastRadiusCalculator()

    def test_register_entity(self):
        self.calculator.register_entity("svc-a", "service", ["svc-b", "svc-c"])
        assert "svc-a" in self.calculator.dependency_graph
        assert len(self.calculator.dependency_graph["svc-a"]) == 2

    def test_calculate_blast_radius(self):
        self.calculator.register_entity("svc-a", "service", ["svc-b"])
        self.calculator.register_entity("svc-b", "service", [])
        incident = {"id": "inc1", "affected_services": ["svc-a"]}
        result = self.calculator.calculate(incident)
        assert result.risk_score > 0
        assert result.severity in ("minimal", "low", "medium", "high", "critical")
        assert len(result.recommendations) > 0

    def test_dependency_chain(self):
        self.calculator.register_entity("a", "service", ["b"])
        self.calculator.register_entity("b", "service", ["c"])
        self.calculator.register_entity("c", "service", [])
        chain = self.calculator.get_dependency_chain("a")
        assert "b" in chain
        assert "c" in chain

    def test_dependents(self):
        self.calculator.register_entity("parent", "service", ["child"])
        self.calculator.register_entity("child", "service", [])
        dependents = self.calculator.get_dependents("child")
        assert "parent" in dependents

    def test_stats(self):
        self.calculator.register_entity("x", "service", [])
        stats = self.calculator.get_stats()
        assert stats["total_entities"] == 1

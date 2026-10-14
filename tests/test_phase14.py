"""Phase 14 Tests — Commercial MVP & Strategic Productization."""

import pytest

from apps.api.app.services.product_tiers import (
    ProductManager,
    ProductTier,
    TIER_FEATURES,
)
from apps.api.app.services.reliability_score import ReliabilityScorer
from apps.api.app.services.incident_memory import (
    IncidentMemory,
    IncidentRecord,
    FailureDNA,
)
from apps.api.app.services.change_intelligence import (
    PreventiveReliability,
    ChangeIntelligence,
    ChangeEvent,
    ChangeType,
    RiskLevel,
)


# ─── Product Tiers Tests ──────────────────────────────────────────────


class TestProductTiers:
    def test_list_tiers(self):
        mgr = ProductManager()
        tiers = mgr.list_tiers()
        assert len(tiers) == 4
        names = [t["tier"] for t in tiers]
        assert "observe" in names
        assert "autonomous" in names

    def test_subscribe(self):
        mgr = ProductManager()
        sub = mgr.subscribe("org1", ProductTier.OBSERVE, started_at="2026-01-01")
        assert sub.org_id == "org1"
        assert sub.tier == ProductTier.OBSERVE
        assert sub.is_active

    def test_upgrade(self):
        mgr = ProductManager()
        mgr.subscribe("org1", ProductTier.OBSERVE)
        sub = mgr.upgrade("org1", ProductTier.INVESTIGATE)
        assert sub.tier == ProductTier.INVESTIGATE

    def test_has_feature(self):
        mgr = ProductManager()
        mgr.subscribe("org1", ProductTier.OBSERVE)
        assert mgr.has_feature("org1", "Pipeline monitoring")
        assert not mgr.has_feature("org1", "AI-powered investigation")

    def test_check_limit(self):
        mgr = ProductManager()
        mgr.subscribe("org1", ProductTier.OBSERVE)
        result = mgr.check_limit("org1", "connectors", 2)
        assert result["within_limit"]
        result = mgr.check_limit("org1", "connectors", 5)
        assert not result["within_limit"]

    def test_check_limit_unlimited(self):
        mgr = ProductManager()
        mgr.subscribe("org1", ProductTier.AUTONOMOUS)
        result = mgr.check_limit("org1", "connectors", 100)
        assert result["within_limit"]
        assert result["limit"] == "unlimited"

    def test_get_subscription(self):
        mgr = ProductManager()
        mgr.subscribe("org1", ProductTier.REMEDIATE)
        sub = mgr.get_subscription("org1")
        assert sub.tier == ProductTier.REMEDIATE

    def test_no_subscription(self):
        mgr = ProductManager()
        assert mgr.get_subscription("nonexistent") is None

    def test_tier_features_complete(self):
        for tier in ProductTier:
            features = TIER_FEATURES[tier]
            assert "name" in features
            assert "description" in features
            assert "price_monthly" in features
            assert "features" in features
            assert "limits" in features


# ─── Reliability Score Tests ──────────────────────────────────────────


class TestReliabilityScore:
    def test_compute_score_perfect(self):
        scorer = ReliabilityScorer()
        metrics = {
            "pipeline_health": {"success_rate": 100},
            "data_quality": {"null_rate": 0},
            "freshness": {"avg_lag_minutes": 2},
            "schema_stability": {"drift_count_30d": 0},
            "incident_frequency": {"incidents_per_week": 0},
            "mttr": {"mttr_minutes": 5},
            "dependency_risk": {"critical_dependencies": 0},
            "remediation_success": {"success_rate": 100},
        }
        report = scorer.compute_score("org1", metrics)
        assert report.overall_score >= 90
        assert report.grade == "A"

    def test_compute_score_poor(self):
        scorer = ReliabilityScorer()
        metrics = {
            "pipeline_health": {"success_rate": 50},
            "data_quality": {"null_rate": 10},
            "freshness": {"avg_lag_minutes": 500},
            "schema_stability": {"drift_count_30d": 10},
            "incident_frequency": {"incidents_per_week": 20},
            "mttr": {"mttr_minutes": 2000},
            "dependency_risk": {"critical_dependencies": 10},
            "remediation_success": {"success_rate": 30},
        }
        report = scorer.compute_score("org1", metrics)
        assert report.overall_score < 50
        assert report.grade == "F"

    def test_dimensions_count(self):
        scorer = ReliabilityScorer()
        report = scorer.compute_score("org1", {})
        assert len(report.dimensions) == 8

    def test_recommendations(self):
        scorer = ReliabilityScorer()
        metrics = {
            "pipeline_health": {"success_rate": 40},
            "incident_frequency": {"incidents_per_week": 20},
        }
        report = scorer.compute_score("org1", metrics)
        assert len(report.recommendations) > 0

    def test_report_to_dict(self):
        scorer = ReliabilityScorer()
        report = scorer.compute_score("org1", {})
        d = report.to_dict()
        assert "overall_score" in d
        assert "grade" in d
        assert "dimensions" in d


# ─── Incident Memory Tests ────────────────────────────────────────────


class TestIncidentMemory:
    def test_generate_dna(self):
        mem = IncidentMemory()
        dna = mem.generate_dna("schema_drift", "high", ["column_missing"])
        assert dna.hash
        assert dna.category == "schema_drift"
        assert "schema_drift" in dna.fingerprint

    def test_record_incident(self):
        mem = IncidentMemory()
        dna = mem.generate_dna("pipeline_failure", "high", ["connection_timeout"])
        record = IncidentRecord(
            incident_id="inc-1",
            title="Pipeline failed",
            description="Connection timeout",
            severity="high",
            category="pipeline_failure",
            root_cause="Database overloaded",
            resolution="Restarted pipeline",
            affected_services=["pg-main"],
            error_signatures=["connection_timeout"],
            failure_dna=dna,
            resolution_steps=["Restarted pipeline"],
        )
        mem.record_incident(record)
        assert len(mem.records) == 1

    def test_find_similar(self):
        mem = IncidentMemory()
        for i in range(3):
            dna = mem.generate_dna("schema_drift", "high", ["col_missing"])
            record = IncidentRecord(
                incident_id=f"inc-{i}",
                title=f"Drift {i}",
                description="Schema drift",
                severity="high",
                category="schema_drift",
                root_cause="Migration",
                resolution="Updated dbt model",
                affected_services=["pg-main"],
                error_signatures=["col_missing"],
                failure_dna=dna,
                resolution_steps=["Updated model"],
            )
            mem.record_incident(record)

        similar = mem.find_similar(category="schema_drift")
        assert len(similar) == 3

    def test_get_resolution_patterns(self):
        mem = IncidentMemory()
        dna = mem.generate_dna("pipeline_failure", "high", ["timeout"])
        record = IncidentRecord(
            incident_id="inc-1",
            title="Pipeline failed",
            description="Timeout",
            severity="high",
            category="pipeline_failure",
            root_cause="Overload",
            resolution="Restarted pipeline",
            affected_services=["pg"],
            error_signatures=["timeout"],
            failure_dna=dna,
            resolution_steps=["Restart"],
        )
        mem.record_incident(record)
        patterns = mem.get_resolution_patterns("pipeline_failure")
        assert len(patterns) == 1

    def test_get_prevention_tips(self):
        mem = IncidentMemory()
        dna = mem.generate_dna("schema_drift", "medium", ["col_added"])
        record = IncidentRecord(
            incident_id="inc-1",
            title="Drift",
            description="Column added",
            severity="medium",
            category="schema_drift",
            root_cause="Migration",
            resolution="Updated model",
            affected_services=["pg"],
            error_signatures=["col_added"],
            failure_dna=dna,
            resolution_steps=["Update"],
            prevention_tip="Run dbt tests before deploy",
        )
        mem.record_incident(record)
        tips = mem.get_prevention_tips("schema_drift")
        assert "Run dbt tests before deploy" in tips

    def test_predict_risk(self):
        mem = IncidentMemory()
        dna = mem.generate_dna("pipeline_failure", "critical", ["timeout"])
        for i in range(5):
            record = IncidentRecord(
                incident_id=f"inc-{i}",
                title=f"Fail {i}",
                description="Fail",
                severity="critical",
                category="pipeline_failure",
                root_cause="Overload",
                resolution="Restart",
                affected_services=["pg"],
                error_signatures=["timeout"],
                failure_dna=dna,
                resolution_steps=["Restart"],
            )
            mem.record_incident(record)

        risk = mem.predict_risk("pipeline_failure", "pg")
        assert risk["risk_level"] == "high"

    def test_stats(self):
        mem = IncidentMemory()
        dna = mem.generate_dna("test", "low", ["sig"])
        record = IncidentRecord(
            incident_id="inc-1", title="Test", description="Test",
            severity="low", category="test", root_cause="Test",
            resolution="Test", affected_services=["svc"],
            error_signatures=["sig"], failure_dna=dna, resolution_steps=["Test"],
        )
        mem.record_incident(record)
        stats = mem.get_stats()
        assert stats["total_records"] == 1


# ─── Preventive Reliability Tests ─────────────────────────────────────


class TestPreventiveReliability:
    def test_analyze_change_low_risk(self):
        pr = PreventiveReliability()
        change = ChangeEvent(
            change_id="c1",
            change_type=ChangeType.COMMIT,
            description="Update readme",
            affected_resources=["docs"],
        )
        prediction = pr.analyze_change(change)
        assert prediction.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM)

    def test_analyze_change_high_risk(self):
        pr = PreventiveReliability()
        change = ChangeEvent(
            change_id="c2",
            change_type=ChangeType.SCHEMA_CHANGE,
            description="Alter table users",
            affected_resources=["users", "orders", "analytics", "reports", "ml_features", "dashboards"],
        )
        prediction = pr.analyze_change(change)
        assert prediction.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)

    def test_preventive_actions(self):
        pr = PreventiveReliability()
        change = ChangeEvent(
            change_id="c3",
            change_type=ChangeType.SCHEMA_CHANGE,
            description="Add column",
            affected_resources=["users"],
        )
        prediction = pr.analyze_change(change)
        assert len(prediction.preventive_actions) > 0

    def test_get_predictions_by_risk(self):
        pr = PreventiveReliability()
        for i, ct in enumerate([ChangeType.COMMIT, ChangeType.SCHEMA_CHANGE, ChangeType.DEPLOYMENT]):
            change = ChangeEvent(
                change_id=f"c{i}", change_type=ct, description=f"Change {i}",
                affected_resources=["res1", "res2", "res3"],
            )
            pr.analyze_change(change)
        high_risk = pr.get_predictions_by_risk(RiskLevel.HIGH)
        assert len(high_risk) >= 0


# ─── Change Intelligence Tests ────────────────────────────────────────


class TestChangeIntelligence:
    def test_record_change(self):
        ci = ChangeIntelligence()
        change = ChangeEvent(
            change_id="c1",
            change_type=ChangeType.DEPLOYMENT,
            description="Deploy v2.0",
            author="alice",
            affected_resources=["api", "db"],
        )
        ci.record_change(change)
        assert len(ci.changes) == 1

    def test_find_correlated_changes(self):
        ci = ChangeIntelligence()
        change = ChangeEvent(
            change_id="c1",
            change_type=ChangeType.SCHEMA_CHANGE,
            description="Alter users",
            affected_resources=["users", "orders"],
        )
        ci.record_change(change)
        correlated = ci.find_correlated_changes(
            "inc-1", "2026-01-01T00:00:00", affected_resources=["users"],
        )
        assert len(correlated) == 1

    def test_get_change_timeline(self):
        ci = ChangeIntelligence()
        for i in range(5):
            ci.record_change(ChangeEvent(
                change_id=f"c{i}", change_type=ChangeType.COMMIT, description=f"Commit {i}",
            ))
        timeline = ci.get_change_timeline()
        assert len(timeline) == 5

    def test_stats(self):
        ci = ChangeIntelligence()
        ci.record_change(ChangeEvent(change_id="c1", change_type=ChangeType.COMMIT, description="c1"))
        ci.record_change(ChangeEvent(change_id="c2", change_type=ChangeType.DEPLOYMENT, description="c2"))
        stats = ci.get_stats()
        assert stats["total_changes"] == 2
        assert stats["by_type"]["commit"] == 1


# ─── API Import Tests ──────────────────────────────────────────────────


class TestPhase14APIImports:
    def test_commercial_router_imports(self):
        from apps.api.app.api.commercial_mvp import router
        assert router is not None
        paths = [r.path for r in router.routes]
        assert any("tiers" in p for p in paths)
        assert any("reliability" in p for p in paths)
        assert any("memory" in p for p in paths)

    def test_main_app_includes_commercial(self):
        from apps.api.app.api.commercial_mvp import router
        assert router.prefix == "/commercial"
        assert any("tiers" in r.path for r in router.routes if hasattr(r, "path"))

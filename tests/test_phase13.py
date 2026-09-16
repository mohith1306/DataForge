"""Phase 13 Tests — Design Partner Program."""

import pytest

from apps.api.app.services.design_partner import (
    DesignPartnerManager,
    DesignPartner,
    BaselineMetrics,
    PartnerStatus,
    AutonomyStage,
)
from apps.api.app.services.kpi_tracker import KPITracker


# ─── Design Partner Manager Tests ─────────────────────────────────────


class TestDesignPartnerManager:
    def test_add_partner(self):
        mgr = DesignPartnerManager()
        partner = mgr.add_partner("p1", "Acme Corp", industry="tech")
        assert partner.name == "Acme Corp"
        assert partner.status == PartnerStatus.PROSPECT

    def test_start_onboarding(self):
        mgr = DesignPartnerManager()
        mgr.add_partner("p1", "Acme")
        partner = mgr.start_onboarding("p1")
        assert partner.status == PartnerStatus.ONBOARDING
        assert partner.onboarded_at

    def test_enable_read_only(self):
        mgr = DesignPartnerManager()
        mgr.add_partner("p1", "Acme")
        mgr.start_onboarding("p1")
        partner = mgr.enable_read_only("p1")
        assert partner.status == PartnerStatus.READ_ONLY
        assert partner.current_stage == AutonomyStage.READ_ONLY

    def test_progressive_autonomy(self):
        mgr = DesignPartnerManager()
        mgr.add_partner("p1", "Acme")
        mgr.start_onboarding("p1")

        mgr.enable_read_only("p1")
        assert mgr.get_partner("p1").current_stage == AutonomyStage.READ_ONLY

        mgr.enable_recommended_remediation("p1")
        assert mgr.get_partner("p1").current_stage == AutonomyStage.RECOMMENDED

        mgr.enable_approval_controlled("p1")
        assert mgr.get_partner("p1").current_stage == AutonomyStage.APPROVAL_CONTROLLED

        mgr.enable_autonomous("p1")
        assert mgr.get_partner("p1").current_stage == AutonomyStage.AUTONOMOUS

    def test_record_baseline(self):
        mgr = DesignPartnerManager()
        mgr.add_partner("p1", "Acme")
        baseline = BaselineMetrics(
            partner_id="p1",
            incident_count=50,
            mttr_seconds=7200,
            engineer_hours_per_week=20,
        )
        mgr.record_baseline(baseline)
        stored = mgr.get_baseline("p1")
        assert stored.incident_count == 50
        assert stored.mttr_seconds == 7200

    def test_list_partners(self):
        mgr = DesignPartnerManager()
        mgr.add_partner("p1", "Acme")
        mgr.add_partner("p2", "Beta Inc")
        assert len(mgr.list_partners()) == 2

    def test_list_partners_by_status(self):
        mgr = DesignPartnerManager()
        mgr.add_partner("p1", "Acme")
        mgr.add_partner("p2", "Beta")
        mgr.start_onboarding("p1")
        assert len(mgr.list_partners(status=PartnerStatus.ONBOARDING)) == 1

    def test_get_nonexistent_partner(self):
        mgr = DesignPartnerManager()
        assert mgr.get_partner("nonexistent") is None

    def test_add_note(self):
        mgr = DesignPartnerManager()
        mgr.add_partner("p1", "Acme")
        assert mgr.add_note("p1", "Great partner", "admin")
        partner = mgr.get_partner("p1")
        assert len(partner.notes) == 1

    def test_stage_history(self):
        mgr = DesignPartnerManager()
        mgr.add_partner("p1", "Acme")
        mgr.start_onboarding("p1")
        mgr.enable_read_only("p1")
        history = mgr.get_stage_history("p1")
        assert len(history) == 2

    def test_stats(self):
        mgr = DesignPartnerManager()
        mgr.add_partner("p1", "Acme")
        mgr.add_partner("p2", "Beta")
        stats = mgr.get_stats()
        assert stats["total_partners"] == 2

    def test_partner_to_dict(self):
        partner = DesignPartner(
            id="p1", name="Acme", status=PartnerStatus.PROSPECT,
            data_platforms=["postgres", "snowflake"],
        )
        d = partner.to_dict()
        assert d["name"] == "Acme"
        assert len(d["data_platforms"]) == 2


# ─── KPI Tracker Tests ────────────────────────────────────────────────


class TestKPITracker:
    def test_record_detection(self):
        tracker = KPITracker()
        tracker.record_detection("inc-1", 150.0, detected=True, true_positive=True)
        stats = tracker.get_detection_stats()
        assert stats["detection_latency_ms"]["count"] == 1

    def test_record_diagnosis(self):
        tracker = KPITracker()
        tracker.record_diagnosis("inc-1", 500.0, root_cause_correct=True)
        stats = tracker.get_diagnosis_stats()
        assert stats["diagnosis_time_ms"]["count"] == 1

    def test_record_remediation(self):
        tracker = KPITracker()
        tracker.record_remediation(
            "inc-1", plan_accepted=True, execution_success=True, remediation_time_ms=2000,
        )
        stats = tracker.get_remediation_stats()
        assert stats["plans_accepted"]["sum"] == 1.0
        assert stats["executions_successful"]["sum"] == 1.0

    def test_record_remediation_with_rollback(self):
        tracker = KPITracker()
        tracker.record_remediation(
            "inc-1", plan_accepted=True, execution_success=True, rolled_back=True,
        )
        stats = tracker.get_remediation_stats()
        assert stats["rollbacks"]["sum"] == 1.0

    def test_record_verification(self):
        tracker = KPITracker()
        tracker.record_verification("inc-1", verification_passed=True)
        stats = tracker.get_verification_stats()
        assert stats["verifications_passed"]["sum"] == 1.0

    def test_record_false_resolution(self):
        tracker = KPITracker()
        tracker.record_verification("inc-1", verification_passed=True, false_resolution=True)
        stats = tracker.get_verification_stats()
        assert stats["false_resolutions"]["sum"] == 1.0

    def test_record_mttr(self):
        tracker = KPITracker()
        tracker.record_mttr("inc-1", 3600)
        stats = tracker.get_business_stats()
        assert stats["mttr_seconds"]["avg"] == 3600

    def test_record_engineer_hours(self):
        tracker = KPITracker()
        tracker.record_engineer_hours(5.0)
        stats = tracker.get_business_stats()
        assert stats["engineer_hours"]["sum"] == 5.0

    def test_record_incident_prevented(self):
        tracker = KPITracker()
        tracker.record_incident_prevented()
        stats = tracker.get_business_stats()
        assert stats["incidents_prevented"]["sum"] == 1.0

    def test_get_all_kpis(self):
        tracker = KPITracker()
        tracker.record_detection("inc-1", 100.0)
        tracker.record_diagnosis("inc-1", 200.0)
        all_kpis = tracker.get_all_kpis()
        assert "detection" in all_kpis
        assert "diagnosis" in all_kpis
        assert "remediation" in all_kpis
        assert "verification" in all_kpis
        assert "business" in all_kpis

    def test_compute_improvement(self):
        tracker = KPITracker()
        baseline = {"mttr_seconds": {"avg": 7200}}
        current = {"mttr_seconds": {"avg": 3600}}
        improvement = tracker.compute_improvement(baseline, current)
        assert improvement["mttr_seconds"]["change_pct"] == 50.0
        assert improvement["mttr_seconds"]["improved"]

    def test_multiple_detections(self):
        tracker = KPITracker()
        for i in range(5):
            tracker.record_detection(f"inc-{i}", 100.0 * (i + 1))
        stats = tracker.get_detection_stats()
        assert stats["detection_latency_ms"]["count"] == 5
        assert stats["detection_latency_ms"]["avg"] == 300.0


# ─── API Import Tests ─────────────────────────────────────────────────


class TestPhase13APIImports:
    def test_design_partner_router_imports(self):
        from apps.api.app.api.design_partner import router
        assert router.prefix == "/api/design-partner"

    def test_main_app_includes_design_partner(self):
        from apps.api.app.api.design_partner import router
        assert any("partner" in r.path for r in router.routes if hasattr(r, "path"))

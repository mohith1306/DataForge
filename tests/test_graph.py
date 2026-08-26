"""Tests for graph state management and routing."""

from agent.graph.router import (
    route_after_approval,
    route_after_diagnosis,
    route_after_investigation,
)
from agent.graph.state import IncidentState


def _make_state(**overrides) -> IncidentState:
    """Create a test IncidentState with defaults."""
    defaults = {
        "incident_id": "1",
        "user_request": "",
        "description": "",
        "status": "created",
        "events": [],
        "evidence": [],
        "database_findings": [],
        "pipeline_findings": [],
        "github_findings": [],
        "analysis_results": {},
        "root_cause": {},
        "confidence": 0.0,
        "remediation_plan": {},
        "risk_level": "",
        "approval_required": False,
        "approval_status": "",
        "execution_result": {},
        "verification_result": {},
        "incident_type": "",
        "severity": "",
        "business_impact": "",
        "data_quality_results": {},
    }
    defaults.update(overrides)
    return defaults


class TestIncidentState:
    """Test incident state initialization."""

    def test_state_has_required_fields(self):
        state = _make_state(incident_id="test-123", status="created")
        assert state["incident_id"] == "test-123"
        assert state["status"] == "created"
        assert state["evidence"] == []


class TestRouteAfterInvestigation:
    """Test routing logic after investigation phase."""

    def test_insufficient_evidence_goes_to_investigate(self):
        state = _make_state(
            evidence=[{"source": "database"}, {"source": "pipeline"}]
        )
        assert route_after_investigation(state) == "investigate"

    def test_sufficient_evidence_goes_to_diagnose(self):
        state = _make_state(
            evidence=[
                {"source": "database"},
                {"source": "pipeline"},
                {"source": "github"},
            ]
        )
        assert route_after_investigation(state) == "diagnose"


class TestRouteAfterDiagnosis:
    """Test routing logic after diagnosis phase."""

    def test_low_confidence_goes_to_investigate(self):
        state = _make_state(confidence=0.5)
        assert route_after_diagnosis(state) == "investigate"

    def test_high_confidence_goes_to_plan(self):
        state = _make_state(confidence=0.85)
        assert route_after_diagnosis(state) == "plan"


class TestRouteAfterApproval:
    """Test routing logic after approval phase."""

    def test_approved_goes_to_execute(self):
        state = _make_state(approval_status="approved")
        assert route_after_approval(state) == "execute"

    def test_rejected_goes_to_verify(self):
        state = _make_state(approval_status="rejected")
        assert route_after_approval(state) == "verify"

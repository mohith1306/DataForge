"""Tests for risk classification logic."""

from agent.tools.risk import classify_remediation_risk, get_risk_level, requires_approval


class TestGetRiskLevel:
    """Test risk level lookup for individual tools."""

    def test_rerun_pipeline_is_medium(self):
        assert get_risk_level("rerun_pipeline") == "MEDIUM"

    def test_rollback_deployment_is_high(self):
        assert get_risk_level("rollback_deployment") == "HIGH"

    def test_reprocess_partition_is_high(self):
        assert get_risk_level("reprocess_partition") == "HIGH"

    def test_create_ticket_is_medium(self):
        assert get_risk_level("create_incident_ticket") == "MEDIUM"

    def test_select_is_low(self):
        assert get_risk_level("execute_select") == "LOW"

    def test_unknown_tool_defaults_to_medium(self):
        assert get_risk_level("unknown_tool") == "MEDIUM"


class TestRequiresApproval:
    """Test approval requirement logic by tool name."""

    def test_low_risk_no_approval(self):
        assert requires_approval("execute_select") is False

    def test_medium_risk_no_approval(self):
        assert requires_approval("rerun_pipeline") is False

    def test_high_risk_requires_approval(self):
        assert requires_approval("rollback_deployment") is True

    def test_critical_risk_requires_approval(self):
        assert requires_approval("delete_data") is True


class TestClassifyRemediationRisk:
    """Test risk classification of remediation action lists."""

    def test_rerun_pipeline_is_medium(self):
        actions = [{"tool": "rerun_pipeline", "parameters": {"pipeline_id": "PL-001"}}]
        assert classify_remediation_risk(actions) == "MEDIUM"

    def test_rollback_deployment_is_high(self):
        actions = [{"tool": "rollback_deployment", "parameters": {}}]
        assert classify_remediation_risk(actions) == "HIGH"

    def test_reprocess_partition_is_high(self):
        actions = [{"tool": "reprocess_partition", "parameters": {"table": "orders"}}]
        assert classify_remediation_risk(actions) == "HIGH"

    def test_mixed_risk_takes_highest(self):
        actions = [
            {"tool": "execute_select", "parameters": {}},
            {"tool": "rerun_pipeline", "parameters": {"pipeline_id": "PL-001"}},
        ]
        assert classify_remediation_risk(actions) == "MEDIUM"

    def test_empty_actions_is_low(self):
        assert classify_remediation_risk([]) == "LOW"

    def test_unknown_tool_is_medium(self):
        actions = [{"tool": "unknown_tool", "parameters": {}}]
        assert classify_remediation_risk(actions) == "MEDIUM"

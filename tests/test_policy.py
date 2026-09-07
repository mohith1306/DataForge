"""Tests for Policy Engine and Risk Classifier."""
import pytest
from apps.api.app.core.policy_engine import (
    PolicyEngine,
    Policy,
    PolicyType,
    RiskLevel,
    AutonomyLevel,
)
from apps.api.app.core.risk_classifier import EnhancedRiskClassifier, RemediationType


def test_policy_engine_initialization():
    """Test PolicyEngine initializes with default policies."""
    engine = PolicyEngine()
    
    assert len(engine.policies) > 0
    
    # Check default policies exist
    policy_types = [p.policy_type for p in engine.policies.values()]
    assert PolicyType.RISK_CLASSIFICATION in policy_types
    assert PolicyType.AUTONOMY_LEVEL in policy_types


def test_policy_engine_add_policy():
    """Test adding a policy."""
    engine = PolicyEngine()
    initial_count = len(engine.policies)
    
    policy = Policy(
        name="test_policy",
        policy_type=PolicyType.TIME_CONSTRAINT,
        rules=[{"condition": "time == 'off_hours'", "action": "block"}],
    )
    
    engine.add_policy(policy)
    
    assert len(engine.policies) == initial_count + 1
    assert policy.id in engine.policies


def test_policy_engine_remove_policy():
    """Test removing a policy."""
    engine = PolicyEngine()
    
    policy = Policy(
        name="test_policy",
        policy_type=PolicyType.TIME_CONSTRAINT,
        rules=[],
    )
    engine.add_policy(policy)
    
    success = engine.remove_policy(policy.id)
    
    assert success is True
    assert policy.id not in engine.policies


def test_policy_engine_evaluate_risk():
    """Test risk evaluation."""
    engine = PolicyEngine()
    
    # Test database action (high risk)
    action = {"action_type": "database"}
    risk = engine.evaluate_risk(action)
    assert risk == RiskLevel.HIGH
    
    # Test cleanup action (low risk)
    action = {"action_type": "cleanup"}
    risk = engine.evaluate_risk(action)
    assert risk == RiskLevel.LOW


def test_policy_engine_get_autonomy_level():
    """Test autonomy level determination."""
    engine = PolicyEngine()
    
    # Low risk = full autonomy
    autonomy = engine.get_autonomy_level(RiskLevel.LOW)
    assert autonomy == AutonomyLevel.FULL_AUTONOMY
    
    # High risk = manual approval
    autonomy = engine.get_autonomy_level(RiskLevel.HIGH)
    assert autonomy == AutonomyLevel.MANUAL_APPROVAL_REQUIRED
    
    # Critical risk = prohibited
    autonomy = engine.get_autonomy_level(RiskLevel.CRITICAL)
    assert autonomy == AutonomyLevel.PROHIBITED


def test_policy_engine_requires_approval():
    """Test approval requirement check."""
    engine = PolicyEngine()
    
    # High risk action requires approval
    action = {"action_type": "database"}
    requires = engine.requires_approval(action)
    assert requires is True
    
    # Low risk action does not require approval
    action = {"action_type": "cleanup"}
    requires = engine.requires_approval(action)
    assert requires is False


def test_policy_engine_get_action_constraints():
    """Test getting action constraints."""
    engine = PolicyEngine()
    
    # Database actions have constraints
    constraints = engine.get_action_constraints("database")
    assert len(constraints) > 0
    assert "no_drop_table" in constraints


def test_policy_engine_validate_action():
    """Test full action validation."""
    engine = PolicyEngine()
    
    action = {"action_type": "database"}
    validation = engine.validate_action(action)
    
    assert "risk_level" in validation
    assert "autonomy_level" in validation
    assert "requires_approval" in validation
    assert "constraints" in validation
    assert "is_allowed" in validation


def test_risk_classifier_initialization():
    """Test EnhancedRiskClassifier initialization."""
    classifier = EnhancedRiskClassifier()
    
    assert classifier.policy_engine is not None


def test_risk_classifier_classify_remediation():
    """Test classifying remediation risk."""
    classifier = EnhancedRiskClassifier()
    
    # Test rollback action
    action = {"action_type": "rollback"}
    classification = classifier.classify_remediation(action)
    
    assert "risk_score" in classification
    assert "risk_level" in classification
    assert "autonomy_level" in classification
    assert classification["risk_level"] in ["low", "medium", "high", "critical"]


def test_risk_classifier_multiple_actions():
    """Test classifying multiple actions."""
    classifier = EnhancedRiskClassifier()
    
    actions = [
        {"action_type": "cleanup"},
        {"action_type": "restart"},
        {"action_type": "database"},
    ]
    
    result = classifier.classify_multiple_actions(actions)
    
    assert "individual_classifications" in result
    assert "aggregate" in result
    assert result["aggregate"]["total_actions"] == 3


def test_risk_classifier_recommendations():
    """Test getting risk recommendations."""
    classifier = EnhancedRiskClassifier()
    
    classification = {
        "risk_level": "critical",
        "requires_approval": True,
        "constraints": ["backup_required"],
    }
    
    recommendations = classifier.get_risk_recommendations(classification)
    
    assert len(recommendations) > 0
    assert any("CRITICAL" in r for r in recommendations)


def test_risk_classifier_map_to_remediation_type():
    """Test mapping action types to remediation types."""
    classifier = EnhancedRiskClassifier()
    
    assert classifier._map_to_remediation_type("rollback") == RemediationType.ROLLBACK_DEPLOYMENT
    assert classifier._map_to_remediation_type("rerun_pipeline") == RemediationType.RERUN_PIPELINE
    assert classifier._map_to_remediation_type("scale") == RemediationType.SCALE_SERVICE
    assert classifier._map_to_remediation_type("unknown_action") == RemediationType.UNKNOWN


def test_policy_engine_list_policies():
    """Test listing policies with optional filter."""
    engine = PolicyEngine()
    
    # List all policies
    all_policies = engine.list_policies()
    assert len(all_policies) > 0
    
    # List by type
    risk_policies = engine.list_policies(PolicyType.RISK_CLASSIFICATION)
    assert all(p["policy_type"] == "risk_classification" for p in risk_policies)


def test_policy_engine_get_policy_summary():
    """Test getting policy summary."""
    engine = PolicyEngine()
    
    summary = engine.get_policy_summary()
    
    assert "total_policies" in summary
    assert "enabled_policies" in summary
    assert "policy_types" in summary
    assert summary["total_policies"] > 0

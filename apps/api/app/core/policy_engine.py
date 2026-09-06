"""Policy Engine for risk-aware autonomy and governance."""
from typing import Any, Dict, List, Optional
from uuid import uuid4
from datetime import datetime, timezone
from enum import Enum


class PolicyType(str, Enum):
    """Types of policies."""
    RISK_CLASSIFICATION = "risk_classification"
    AUTONOMY_LEVEL = "autonomy_level"
    APPROVAL_REQUIRED = "approval_required"
    ACTION_CONSTRAINT = "action_constraint"
    TIME_CONSTRAINT = "time_constraint"


class RiskLevel(str, Enum):
    """Risk levels for actions."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AutonomyLevel(str, Enum):
    """Autonomy levels for AI actions."""
    FULL_AUTONOMY = "full_autonomy"
    SUPERVISED_AUTONOMY = "supervised_autonomy"
    MANUAL_APPROVAL_REQUIRED = "manual_approval_required"
    PROHIBITED = "prohibited"


class Policy:
    """Represents a governance policy."""

    def __init__(
        self,
        name: str,
        policy_type: PolicyType,
        rules: List[Dict[str, Any]],
        description: str = "",
        enabled: bool = True,
    ):
        self.id = str(uuid4())
        self.name = name
        self.policy_type = policy_type
        self.rules = rules
        self.description = description
        self.enabled = enabled
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "policy_type": self.policy_type,
            "rules": self.rules,
            "description": self.description,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class PolicyEngine:
    """Engine for evaluating policies and determining autonomy levels."""

    def __init__(self):
        self.policies: Dict[str, Policy] = {}
        self._initialize_default_policies()

    def _initialize_default_policies(self) -> None:
        """Initialize default governance policies."""
        # Risk classification policy
        self.add_policy(
            Policy(
                name="default_risk_classification",
                policy_type=PolicyType.RISK_CLASSIFICATION,
                description="Default risk classification rules",
                rules=[
                    {"condition": "action_type == 'database'", "risk_level": "high"},
                    {"condition": "action_type == 'deployment'", "risk_level": "critical"},
                    {"condition": "action_type == 'rollback'", "risk_level": "high"},
                    {"condition": "action_type == 'scale'", "risk_level": "medium"},
                    {"condition": "action_type == 'restart'", "risk_level": "medium"},
                    {"condition": "action_type == 'cleanup'", "risk_level": "low"},
                    {"condition": "action_type == 'monitoring'", "risk_level": "low"},
                ],
            )
        )
        
        # Autonomy level policy
        self.add_policy(
            Policy(
                name="default_autonomy_levels",
                policy_type=PolicyType.AUTONOMY_LEVEL,
                description="Default autonomy levels based on risk",
                rules=[
                    {"risk_level": "low", "autonomy": "full_autonomy"},
                    {"risk_level": "medium", "autonomy": "supervised_autonomy"},
                    {"risk_level": "high", "autonomy": "manual_approval_required"},
                    {"risk_level": "critical", "autonomy": "prohibited"},
                ],
            )
        )
        
        # Approval required policy
        self.add_policy(
            Policy(
                name="approval_requirements",
                policy_type=PolicyType.APPROVAL_REQUIRED,
                description="When approvals are required",
                rules=[
                    {"risk_level": "high", "requires_approval": True},
                    {"risk_level": "critical", "requires_approval": True},
                    {"risk_level": "medium", "requires_approval": False},
                    {"risk_level": "low", "requires_approval": False},
                    {"condition": "time_window == 'business_hours'", "requires_approval": False},
                    {"condition": "time_window == 'off_hours'", "requires_approval": True},
                ],
            )
        )
        
        # Action constraints policy
        self.add_policy(
            Policy(
                name="action_constraints",
                policy_type=PolicyType.ACTION_CONSTRAINT,
                description="Constraints on specific actions",
                rules=[
                    {
                        "action_type": "database",
                        "constraints": [
                            "no_drop_table",
                            "no_truncate_production",
                            "backup_required",
                        ],
                    },
                    {
                        "action_type": "deployment",
                        "constraints": [
                            "canary_required",
                            "rollback_plan_required",
                            "approval_required",
                        ],
                    },
                    {
                        "action_type": "scale",
                        "constraints": [
                            "max_replicas_10",
                            "cooldown_5_minutes",
                        ],
                    },
                ],
            )
        )

    def add_policy(self, policy: Policy) -> None:
        """Add a policy to the engine."""
        self.policies[policy.id] = policy

    def remove_policy(self, policy_id: str) -> bool:
        """Remove a policy from the engine."""
        if policy_id in self.policies:
            del self.policies[policy_id]
            return True
        return False

    def get_policy(self, policy_id: str) -> Optional[Policy]:
        """Get a policy by ID."""
        return self.policies.get(policy_id)

    def list_policies(self, policy_type: Optional[PolicyType] = None) -> List[Dict[str, Any]]:
        """List all policies, optionally filtered by type."""
        policies = list(self.policies.values())
        if policy_type:
            policies = [p for p in policies if p.policy_type == policy_type]
        return [p.to_dict() for p in policies]

    def evaluate_risk(self, action: Dict[str, Any]) -> RiskLevel:
        """Evaluate the risk level of an action."""
        action_type = action.get("action_type", "unknown")
        
        # Find risk classification policy
        for policy in self.policies.values():
            if (
                policy.policy_type == PolicyType.RISK_CLASSIFICATION
                and policy.enabled
            ):
                for rule in policy.rules:
                    if rule.get("condition", "").endswith(f"'{action_type}'"):
                        return RiskLevel(rule["risk_level"])
        
        # Default to medium risk
        return RiskLevel.MEDIUM

    def get_autonomy_level(self, risk_level: RiskLevel) -> AutonomyLevel:
        """Get the autonomy level for a given risk level."""
        for policy in self.policies.values():
            if (
                policy.policy_type == PolicyType.AUTONOMY_LEVEL
                and policy.enabled
            ):
                for rule in policy.rules:
                    if rule.get("risk_level") == risk_level.value:
                        return AutonomyLevel(rule["autonomy"])
        
        # Default to manual approval for unknown risk
        return AutonomyLevel.MANUAL_APPROVAL_REQUIRED

    def requires_approval(self, action: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> bool:
        """Determine if an action requires approval.
        
        Bug #13 fix: Evaluate conditions from context before risk-level defaults.
        """
        risk_level = self.evaluate_risk(action)
        context = context or {}
        
        # First, evaluate any condition-based rules
        for policy in self.policies.values():
            if (
                policy.policy_type == PolicyType.APPROVAL_REQUIRED
                and policy.enabled
            ):
                for rule in policy.rules:
                    condition = rule.get("condition")
                    if condition:
                        # Evaluate condition against context
                        if self._evaluate_condition(condition, context):
                            return rule.get("requires_approval", False)
        
        # Then, apply risk-level rules
        for policy in self.policies.values():
            if (
                policy.policy_type == PolicyType.APPROVAL_REQUIRED
                and policy.enabled
            ):
                for rule in policy.rules:
                    if rule.get("risk_level") == risk_level.value:
                        return rule.get("requires_approval", False)
        
        # Default: require approval for high and critical
        return risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)

    def _evaluate_condition(self, condition: str, context: Dict[str, Any]) -> bool:
        """Evaluate a condition string against context.
        
        Bug #13 fix: Simple condition evaluation for time_window and other context values.
        """
        # Parse simple conditions like "time_window == 'off_hours'"
        if "==" in condition:
            parts = condition.split("==")
            if len(parts) == 2:
                key = parts[0].strip()
                value = parts[1].strip().strip("'\"")
                return context.get(key) == value
        
        # Parse "in" conditions like "action_type in ['scale', 'restart']"
        if " in " in condition:
            parts = condition.split(" in ")
            if len(parts) == 2:
                key = parts[0].strip()
                values_str = parts[1].strip().strip("[]")
                values = [v.strip().strip("'\"") for v in values_str.split(",")]
                return context.get(key) in values
        
        return False

    def get_action_constraints(self, action_type: str) -> List[str]:
        """Get constraints for a specific action type."""
        constraints = []
        
        for policy in self.policies.values():
            if (
                policy.policy_type == PolicyType.ACTION_CONSTRAINT
                and policy.enabled
            ):
                for rule in policy.rules:
                    if rule.get("action_type") == action_type:
                        constraints.extend(rule.get("constraints", []))
        
        return constraints

    def validate_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Validate an action against all policies."""
        action_type = action.get("action_type", "unknown")
        risk_level = self.evaluate_risk(action)
        autonomy_level = self.get_autonomy_level(risk_level)
        requires_approval = self.requires_approval(action)
        constraints = self.get_action_constraints(action_type)
        
        # Check if action is prohibited
        is_allowed = autonomy_level != AutonomyLevel.PROHIBITED
        
        return {
            "action_type": action_type,
            "risk_level": risk_level.value,
            "autonomy_level": autonomy_level.value,
            "requires_approval": requires_approval,
            "constraints": constraints,
            "is_allowed": is_allowed,
            "validation_time": datetime.now(timezone.utc).isoformat(),
        }

    def get_policy_summary(self) -> Dict[str, Any]:
        """Get a summary of all policies."""
        return {
            "total_policies": len(self.policies),
            "enabled_policies": sum(1 for p in self.policies.values() if p.enabled),
            "policy_types": {
                pt.value: sum(1 for p in self.policies.values() if p.policy_type == pt)
                for pt in PolicyType
            },
        }

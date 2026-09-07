"""Enhanced risk classifier with policy awareness."""
from typing import Any, Dict, List, Optional
from enum import Enum

from .policy_engine import PolicyEngine, RiskLevel, AutonomyLevel


class RemediationType(str, Enum):
    """Types of remediation actions."""
    RERUN_PIPELINE = "rerun_pipeline"
    ROLLBACK_DEPLOYMENT = "rollback_deployment"
    REPROCESS_PARTITION = "reprocess_partition"
    CREATE_TICKET = "create_ticket"
    SCALE_SERVICE = "scale_service"
    RESTART_SERVICE = "restart_service"
    CLEANUP_RESOURCE = "cleanup_resource"
    UPDATE_CONFIG = "update_config"
    UNKNOWN = "unknown"


class EnhancedRiskClassifier:
    """Enhanced risk classifier with policy engine integration."""

    def __init__(self, policy_engine: Optional[PolicyEngine] = None):
        self.policy_engine = policy_engine or PolicyEngine()
        
        # Base risk scores for remediation types
        self._base_risk_scores = {
            RemediationType.RERUN_PIPELINE: 40,
            RemediationType.ROLLBACK_DEPLOYMENT: 70,
            RemediationType.REPROCESS_PARTITION: 60,
            RemediationType.CREATE_TICKET: 20,
            RemediationType.SCALE_SERVICE: 45,
            RemediationType.RESTART_SERVICE: 35,
            RemediationType.CLEANUP_RESOURCE: 25,
            RemediationType.UPDATE_CONFIG: 50,
            RemediationType.UNKNOWN: 50,
        }

    def classify_remediation(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Classify the risk of a remediation action with policy awareness."""
        action_type = action.get("action_type", action.get("tool", "unknown"))
        
        # Map action type to remediation type
        remediation_type = self._map_to_remediation_type(action_type)
        
        # Get base risk score
        base_score = self._base_risk_scores.get(remediation_type, 50)
        
        # Get policy validation
        policy_validation = self.policy_engine.validate_action(action)
        
        # Adjust score based on policy constraints
        constraints = policy_validation.get("constraints", [])
        if constraints:
            # More constraints = higher risk
            constraint_factor = len(constraints) * 5
            adjusted_score = min(base_score + constraint_factor, 100)
        else:
            adjusted_score = base_score
        
        # Determine risk level from score
        if adjusted_score >= 80:
            risk_level = RiskLevel.CRITICAL
        elif adjusted_score >= 60:
            risk_level = RiskLevel.HIGH
        elif adjusted_score >= 40:
            risk_level = RiskLevel.MEDIUM
        else:
            risk_level = RiskLevel.LOW
        
        # Get autonomy level from policy engine
        autonomy_level = self.policy_engine.get_autonomy_level(risk_level)
        
        return {
            "remediation_type": remediation_type.value,
            "risk_score": adjusted_score,
            "risk_level": risk_level.value,
            "autonomy_level": autonomy_level.value,
            "requires_approval": policy_validation.get("requires_approval", False),
            "constraints": constraints,
            "policy_validated": True,
            "is_allowed": policy_validation.get("is_allowed", True),
        }

    def _map_to_remediation_type(self, action_type: str) -> RemediationType:
        """Map an action type to a remediation type."""
        mapping = {
            "rerun": RemediationType.RERUN_PIPELINE,
            "rerun_pipeline": RemediationType.RERUN_PIPELINE,
            "rollback": RemediationType.ROLLBACK_DEPLOYMENT,
            "rollback_deployment": RemediationType.ROLLBACK_DEPLOYMENT,
            "reprocess": RemediationType.REPROCESS_PARTITION,
            "reprocess_partition": RemediationType.REPROCESS_PARTITION,
            "ticket": RemediationType.CREATE_TICKET,
            "create_ticket": RemediationType.CREATE_TICKET,
            "scale": RemediationType.SCALE_SERVICE,
            "scale_service": RemediationType.SCALE_SERVICE,
            "restart": RemediationType.RESTART_SERVICE,
            "restart_service": RemediationType.RESTART_SERVICE,
            "cleanup": RemediationType.CLEANUP_RESOURCE,
            "cleanup_resource": RemediationType.CLEANUP_RESOURCE,
            "config": RemediationType.UPDATE_CONFIG,
            "update_config": RemediationType.UPDATE_CONFIG,
        }
        return mapping.get(action_type.lower(), RemediationType.UNKNOWN)

    def classify_multiple_actions(self, actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Classify risk for multiple actions and return aggregate result."""
        classifications = []
        max_risk_score = 0
        max_risk_level = RiskLevel.LOW
        requires_approval = False
        all_constraints = []
        
        for action in actions:
            classification = self.classify_remediation(action)
            classifications.append(classification)
            
            # Track maximums
            if classification["risk_score"] > max_risk_score:
                max_risk_score = classification["risk_score"]
                max_risk_level = RiskLevel(classification["risk_level"])
            
            if classification["requires_approval"]:
                requires_approval = True
            
            all_constraints.extend(classification.get("constraints", []))
        
        return {
            "individual_classifications": classifications,
            "aggregate": {
                "max_risk_score": max_risk_score,
                "max_risk_level": max_risk_level.value,
                "requires_approval": requires_approval,
                "total_actions": len(actions),
                "unique_constraints": list(set(all_constraints)),
            },
        }

    def get_risk_recommendations(self, classification: Dict[str, Any]) -> List[str]:
        """Get recommendations based on risk classification."""
        recommendations = []
        
        risk_level = classification.get("risk_level", "medium")
        autonomy_level = classification.get("autonomy_level", "manual_approval_required")
        requires_approval = classification.get("requires_approval", False)
        
        if risk_level == "critical":
            recommendations.append("CRITICAL: Escalate to on-call team immediately")
            recommendations.append("Do not proceed without explicit approval")
        elif risk_level == "high":
            recommendations.append("HIGH: Review with team lead before proceeding")
            recommendations.append("Ensure rollback plan is ready")
        
        if requires_approval:
            recommendations.append("Request approval from authorized personnel")
        
        if autonomy_level == "full_autonomy":
            recommendations.append("Action can proceed automatically")
        elif autonomy_level == "supervised_autonomy":
            recommendations.append("Action can proceed with monitoring")
        
        constraints = classification.get("constraints", [])
        for constraint in constraints:
            if constraint == "backup_required":
                recommendations.append("Ensure backup is created before proceeding")
            elif constraint == "rollback_plan_required":
                recommendations.append("Prepare rollback plan")
            elif constraint == "canary_required":
                recommendations.append("Use canary deployment strategy")
        
        return recommendations

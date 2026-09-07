"""Verification Engine with 5-level verification system."""
from typing import Any, Dict, List, Optional
from uuid import uuid4
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field


class VerificationLevel(str, Enum):
    """5-level verification system."""
    LEVEL_1_SYNTAX = "syntax"           # Code/command syntax check
    LEVEL_2_SEMANTIC = "semantic"       # Logic and semantic validation
    LEVEL_3_SAFETY = "safety"           # Safety and impact assessment
    LEVEL_4_INTEGRATION = "integration" # Integration and dependency check
    LEVEL_5_BUSINESS = "business"       # Business rule validation


class VerificationStatus(str, Enum):
    """Status of a verification."""
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


class VerificationResult(BaseModel):
    """Result of a single verification level."""
    level: VerificationLevel
    status: VerificationStatus
    message: str
    details: Dict[str, Any] = {}
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FullVerificationResult(BaseModel):
    """Complete verification result across all levels."""
    verification_id: str
    overall_status: VerificationStatus
    levels: List[VerificationResult]
    execution_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: float = 0.0


class VerificationEngine:
    """Engine for performing 5-level verification of actions."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.verification_history: List[FullVerificationResult] = []

    async def verify(
        self,
        action: Dict[str, Any],
        execution_result: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> FullVerificationResult:
        """Perform full 5-level verification."""
        verification_id = str(uuid4())
        start_time = datetime.now(timezone.utc)
        
        levels = []
        
        # Level 1: Syntax verification
        level1 = await self._verify_syntax(action)
        levels.append(level1)
        
        # Level 2: Semantic verification
        level2 = await self._verify_semantic(action, context)
        levels.append(level2)
        
        # Level 3: Safety verification
        level3 = await self._verify_safety(action, execution_result)
        levels.append(level3)
        
        # Level 4: Integration verification
        level4 = await self._verify_integration(action, execution_result, context)
        levels.append(level4)
        
        # Level 5: Business verification
        level5 = await self._verify_business(action, execution_result, context)
        levels.append(level5)
        
        # Determine overall status
        statuses = [level.status for level in levels]
        if VerificationStatus.FAILED in statuses:
            overall_status = VerificationStatus.FAILED
        elif VerificationStatus.WARNING in statuses:
            overall_status = VerificationStatus.WARNING
        else:
            overall_status = VerificationStatus.PASSED
        
        end_time = datetime.now(timezone.utc)
        duration_ms = (end_time - start_time).total_seconds() * 1000
        
        result = FullVerificationResult(
            verification_id=verification_id,
            overall_status=overall_status,
            levels=levels,
            execution_id=action.get("execution_id", "unknown"),
            start_time=start_time,
            end_time=end_time,
            duration_ms=duration_ms,
        )
        
        self.verification_history.append(result)
        return result

    async def _verify_syntax(self, action: Dict[str, Any]) -> VerificationResult:
        """Level 1: Syntax verification."""
        action_type = action.get("action_type", "")
        
        # Check for required fields
        required_fields = ["action_type"]
        missing_fields = [f for f in required_fields if f not in action]
        
        if missing_fields:
            return VerificationResult(
                level=VerificationLevel.LEVEL_1_SYNTAX,
                status=VerificationStatus.FAILED,
                message=f"Missing required fields: {missing_fields}",
                details={"missing_fields": missing_fields},
            )
        
        # Validate action type format
        if not action_type.isidentifier():
            return VerificationResult(
                level=VerificationLevel.LEVEL_1_SYNTAX,
                status=VerificationStatus.FAILED,
                message=f"Invalid action type format: {action_type}",
                details={"action_type": action_type},
            )
        
        return VerificationResult(
            level=VerificationLevel.LEVEL_1_SYNTAX,
            status=VerificationStatus.PASSED,
            message="Syntax validation passed",
            details={"action_type": action_type},
        )

    async def _verify_semantic(
        self,
        action: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        """Level 2: Semantic verification."""
        action_type = action.get("action_type", "")
        parameters = action.get("parameters", {})
        
        # Check parameter types and values
        warnings = []
        
        if action_type == "scale":
            replicas = parameters.get("replicas", 1)
            if replicas > 10:
                warnings.append(f"High replica count: {replicas}")
            if replicas < 1:
                return VerificationResult(
                    level=VerificationLevel.LEVEL_2_SEMANTIC,
                    status=VerificationStatus.FAILED,
                    message="Replica count must be at least 1",
                    details={"replicas": replicas},
                )
        
        if action_type == "database":
            query = parameters.get("query", "")
            if "DROP" in query.upper():
                warnings.append("DROP operation detected")
            if "TRUNCATE" in query.upper():
                warnings.append("TRUNCATE operation detected")
        
        status = VerificationStatus.WARNING if warnings else VerificationStatus.PASSED
        message = "Semantic validation passed" if not warnings else f"Warnings: {', '.join(warnings)}"
        
        return VerificationResult(
            level=VerificationLevel.LEVEL_2_SEMANTIC,
            status=status,
            message=message,
            details={"warnings": warnings},
        )

    async def _verify_safety(
        self,
        action: Dict[str, Any],
        execution_result: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        """Level 3: Safety verification."""
        action_type = action.get("action_type", "")
        parameters = action.get("parameters", {})
        
        safety_issues = []
        
        # Check for dangerous operations
        dangerous_actions = ["delete", "drop", "truncate", "remove"]
        if any(da in action_type.lower() for da in dangerous_actions):
            safety_issues.append(f"Potentially dangerous action: {action_type}")
        
        # Check for production impacts
        environment = parameters.get("environment", "")
        if environment == "production":
            safety_issues.append("Production environment detected")
        
        # Check execution result for errors
        if execution_result and not execution_result.get("success", True):
            safety_issues.append("Execution failed")
        
        if safety_issues:
            return VerificationResult(
                level=VerificationLevel.LEVEL_3_SAFETY,
                status=VerificationStatus.WARNING,
                message=f"Safety concerns: {', '.join(safety_issues)}",
                details={"safety_issues": safety_issues},
            )
        
        return VerificationResult(
            level=VerificationLevel.LEVEL_3_SAFETY,
            status=VerificationStatus.PASSED,
            message="Safety verification passed",
            details={},
        )

    async def _verify_integration(
        self,
        action: Dict[str, Any],
        execution_result: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        """Level 4: Integration verification."""
        action_type = action.get("action_type", "")
        
        # Check if execution was successful
        if execution_result and not execution_result.get("success", True):
            return VerificationResult(
                level=VerificationLevel.LEVEL_4_INTEGRATION,
                status=VerificationStatus.FAILED,
                message="Execution failed, integration verification failed",
                details={"execution_status": execution_result.get("status")},
            )
        
        # Check dependencies
        dependencies = (context or {}).get("dependencies", [])
        if dependencies:
            # In real implementation, check if dependencies are healthy
            pass
        
        return VerificationResult(
            level=VerificationLevel.LEVEL_4_INTEGRATION,
            status=VerificationStatus.PASSED,
            message="Integration verification passed",
            details={"action_type": action_type},
        )

    async def _verify_business(
        self,
        action: Dict[str, Any],
        execution_result: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        """Level 5: Business verification."""
        action_type = action.get("action_type", "")
        business_rules = (context or {}).get("business_rules", [])
        
        violations = []
        
        # Check business rules
        for rule in business_rules:
            rule_type = rule.get("type", "")
            rule_value = rule.get("value", "")
            
            if rule_type == "max_downtime" and action_type == "maintenance":
                violations.append(f"Exceeds max downtime: {rule_value}")
            
            if rule_type == "required_approval" and not context.get("approved", False):
                violations.append("Required approval not obtained")
        
        if violations:
            return VerificationResult(
                level=VerificationLevel.LEVEL_5_BUSINESS,
                status=VerificationStatus.WARNING,
                message=f"Business rule violations: {', '.join(violations)}",
                details={"violations": violations},
            )
        
        return VerificationResult(
            level=VerificationLevel.LEVEL_5_BUSINESS,
            status=VerificationStatus.PASSED,
            message="Business verification passed",
            details={},
        )

    def get_verification_history(
        self,
        execution_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[FullVerificationResult]:
        """Get verification history."""
        history = self.verification_history
        
        if execution_id:
            history = [v for v in history if v.execution_id == execution_id]
        
        return history[-limit:]

    def get_verification_stats(self) -> Dict[str, Any]:
        """Get verification statistics."""
        total = len(self.verification_history)
        passed = sum(1 for v in self.verification_history if v.overall_status == VerificationStatus.PASSED)
        failed = sum(1 for v in self.verification_history if v.overall_status == VerificationStatus.FAILED)
        warned = sum(1 for v in self.verification_history if v.overall_status == VerificationStatus.WARNING)
        
        return {
            "total_verifications": total,
            "passed": passed,
            "failed": failed,
            "warnings": warned,
            "pass_rate": passed / total if total > 0 else 0,
        }

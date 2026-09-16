"""Pre-Execution Validator — validates remediation actions before execution.

Checks: syntax, dangerous operations, policy constraints, affected resources,
rollback availability, and dependency impact.
"""

from __future__ import annotations

import re
from typing import Any
from dataclasses import dataclass, field

from apps.api.app.core.policy_engine import PolicyEngine, RiskLevel


DANGEROUS_SQL_PATTERNS = [
    (r"\bDROP\s+TABLE\b", "DROP TABLE", "critical"),
    (r"\bDROP\s+DATABASE\b", "DROP DATABASE", "critical"),
    (r"\bTRUNCATE\b", "TRUNCATE", "critical"),
    (r"\bDELETE\s+FROM\b.*(?:WHERE\s+1\s*=|WHERE\s+TRUE|$)", "DELETE without WHERE", "critical"),
    (r"\bALTER\s+TABLE\b.*\bDROP\s+COLUMN\b", "DROP COLUMN", "high"),
    (r"\bALTER\s+TABLE\b.*\bRENAME\s+COLUMN\b", "RENAME COLUMN", "high"),
    (r"\bUPDATE\b.*(?:WHERE\s+1\s*=|WHERE\s+TRUE|$)", "UPDATE without WHERE", "high"),
]

DANGEROUS_ACTION_PATTERNS = [
    (r"delete.*production", "Delete in production", "critical"),
    (r"drop.*table", "Drop table", "critical"),
    (r"truncate", "Truncate data", "critical"),
    (r"rollback.*deployment", "Rollback deployment", "high"),
    (r"scale.*down.*0", "Scale to zero", "high"),
]


@dataclass
class ValidationResult:
    """Result of pre-execution validation."""
    passed: bool
    risk_level: str
    autonomy_level: str
    requires_approval: bool
    is_allowed: bool
    checks: list[dict[str, Any]] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "risk_level": self.risk_level,
            "autonomy_level": self.autonomy_level,
            "requires_approval": self.requires_approval,
            "is_allowed": self.is_allowed,
            "checks": self.checks,
            "blockers": self.blockers,
            "warnings": self.warnings,
        }


class PreExecutionValidator:
    """Validates remediation actions before execution."""

    def __init__(self, policy_engine: PolicyEngine | None = None):
        self.policy_engine = policy_engine or PolicyEngine()

    def validate(self, action: dict[str, Any], context: dict[str, Any] | None = None) -> ValidationResult:
        """Run all validation checks on an action."""
        context = context or {}
        checks = []
        blockers = []
        warnings = []

        syntax_check = self._check_syntax(action)
        checks.append(syntax_check)
        if not syntax_check["passed"]:
            blockers.append(syntax_check["message"])

        dangerous_check = self._check_dangerous_operations(action)
        checks.append(dangerous_check)
        if dangerous_check["blockers"]:
            blockers.extend(dangerous_check["blockers"])
        if dangerous_check["warnings"]:
            warnings.extend(dangerous_check["warnings"])

        policy_result = self.policy_engine.validate_action(action)
        policy_check = {
            "name": "policy_engine",
            "passed": policy_result["is_allowed"],
            "risk_level": policy_result["risk_level"],
            "autonomy_level": policy_result["autonomy_level"],
            "requires_approval": policy_result["requires_approval"],
            "constraints": policy_result.get("constraints", []),
        }
        checks.append(policy_check)

        if not policy_result["is_allowed"]:
            blockers.append(f"Action prohibited by policy (risk: {policy_result['risk_level']})")

        resource_check = self._check_affected_resources(action, context)
        checks.append(resource_check)
        if resource_check["warnings"]:
            warnings.extend(resource_check["warnings"])

        rollback_check = self._check_rollback_availability(action, context)
        checks.append(rollback_check)
        if not rollback_check["passed"] and policy_result["risk_level"] in ("high", "critical"):
            blockers.append("High-risk action requires rollback plan but none provided")

        dependency_check = self._check_dependency_impact(action, context)
        checks.append(dependency_check)
        if dependency_check["warnings"]:
            warnings.extend(dependency_check["warnings"])

        risk_level = policy_result["risk_level"]
        autonomy_level = policy_result["autonomy_level"]
        requires_approval = policy_result["requires_approval"]
        is_allowed = policy_result["is_allowed"] and len(blockers) == 0

        return ValidationResult(
            passed=len(blockers) == 0,
            risk_level=risk_level,
            autonomy_level=autonomy_level,
            requires_approval=requires_approval,
            is_allowed=is_allowed,
            checks=checks,
            blockers=blockers,
            warnings=warnings,
        )

    def _check_syntax(self, action: dict[str, Any]) -> dict[str, Any]:
        """Validate action has required fields and correct types."""
        required_fields = ["action_type", "action"]
        missing = [f for f in required_fields if f not in action]

        action_type = action.get("action_type", "")
        if action_type and not action_type.replace("_", "").isalnum():
            return {
                "name": "syntax",
                "passed": False,
                "message": f"Invalid action_type format: '{action_type}'",
            }

        if missing:
            return {
                "name": "syntax",
                "passed": False,
                "message": f"Missing required fields: {', '.join(missing)}",
            }

        return {"name": "syntax", "passed": True, "message": "Syntax OK"}

    def _check_dangerous_operations(self, action: dict[str, Any]) -> dict[str, Any]:
        """Detect dangerous SQL or operations."""
        blockers = []
        warnings = []

        sql = action.get("sql", "") or action.get("action", "")
        sql_upper = sql.upper()

        for pattern, desc, severity in DANGEROUS_SQL_PATTERNS:
            if re.search(pattern, sql, re.IGNORECASE):
                if severity == "critical":
                    blockers.append(f"Dangerous SQL detected: {desc}")
                else:
                    warnings.append(f"Potentially dangerous SQL: {desc}")

        action_str = str(action).lower()
        for pattern, desc, severity in DANGEROUS_ACTION_PATTERNS:
            if re.search(pattern, action_str):
                if severity == "critical":
                    blockers.append(f"Dangerous action detected: {desc}")
                else:
                    warnings.append(f"Potentially dangerous action: {desc}")

        return {
            "name": "dangerous_operations",
            "passed": len(blockers) == 0,
            "blockers": blockers,
            "warnings": warnings,
        }

    def _check_affected_resources(self, action: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Check what resources will be affected."""
        warnings = []
        target = action.get("target", "")

        critical_tables = context.get("critical_tables", [])
        if any(t in target for t in critical_tables):
            warnings.append(f"Action targets a critical table: {target}")

        production_indicators = ["prod", "production", "main", "master"]
        if any(ind in target.lower() for ind in production_indicators):
            warnings.append(f"Action appears to target production: {target}")

        return {"name": "affected_resources", "passed": True, "warnings": warnings}

    def _check_rollback_availability(self, action: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Check if rollback plan is available for high-risk actions."""
        has_rollback = bool(action.get("rollback_plan"))
        has_backup = bool(context.get("backup_available"))

        return {
            "name": "rollback_availability",
            "passed": has_rollback or has_backup,
            "has_rollback_plan": has_rollback,
            "backup_available": has_backup,
        }

    def _check_dependency_impact(self, action: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Check dependency impact from blast radius."""
        warnings = []
        blast_radius = context.get("blast_radius", {})

        affected_count = blast_radius.get("total_affected", 0)
        if affected_count > 10:
            warnings.append(f"High blast radius: {affected_count} downstream resources affected")

        business_impact = blast_radius.get("business_impact", "low")
        if business_impact in ("critical", "high"):
            warnings.append(f"Business impact is {business_impact}")

        return {"name": "dependency_impact", "passed": True, "warnings": warnings}

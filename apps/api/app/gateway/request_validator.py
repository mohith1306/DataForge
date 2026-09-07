"""Request Validator middleware for API Gateway."""
from typing import Any, Callable, Dict, List, Optional, Set
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from enum import Enum
import re
import json


class ValidationSeverity(str, Enum):
    """Severity levels for validation errors."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ValidationRule(BaseModel):
    """A validation rule for request fields."""
    name: str
    field_path: str
    rule_type: str  # required, type, pattern, range, custom
    parameters: Dict[str, Any] = {}
    severity: ValidationSeverity = ValidationSeverity.ERROR
    message: Optional[str] = None


class ValidationError(BaseModel):
    """A validation error."""
    rule: str
    field: str
    message: str
    severity: ValidationSeverity
    value: Any = None


class ValidationResult(BaseModel):
    """Result of request validation."""
    valid: bool
    errors: List[ValidationError] = []
    warnings: List[ValidationError] = []
    metadata: Dict[str, Any] = {}


class RequestValidator:
    """Validates API requests against rules."""

    def __init__(self):
        self.rules: Dict[str, ValidationRule] = {}
        self.custom_validators: Dict[str, Callable] = {}
        self.blocked_patterns: List[str] = []
        self.allowed_methods: Set[str] = {"GET", "POST", "PUT", "DELETE", "PATCH"}
        self.max_body_size: int = 10 * 1024 * 1024  # 10MB

    def add_rule(self, rule: ValidationRule) -> None:
        """Add a validation rule."""
        self.rules[rule.name] = rule

    def add_custom_validator(self, name: str, validator: Callable[[Any], bool]) -> None:
        """Add a custom validator function."""
        self.custom_validators[name] = validator

    def add_blocked_pattern(self, pattern: str) -> None:
        """Add a blocked pattern (regex)."""
        self.blocked_patterns.append(pattern)

    def validate_request(
        self,
        method: str,
        path: str,
        headers: Dict[str, str],
        body: Optional[Any] = None,
        query_params: Optional[Dict[str, str]] = None
    ) -> ValidationResult:
        """Validate an API request."""
        errors: List[ValidationError] = []
        warnings: List[ValidationError] = []

        # Check HTTP method
        if method.upper() not in self.allowed_methods:
            errors.append(ValidationError(
                rule="method",
                field="method",
                message=f"Method {method} not allowed",
                severity=ValidationSeverity.ERROR,
                value=method
            ))

        # Check for blocked patterns in path
        for pattern in self.blocked_patterns:
            if re.search(pattern, path):
                errors.append(ValidationError(
                    rule="blocked_pattern",
                    field="path",
                    message=f"Path matches blocked pattern: {pattern}",
                    severity=ValidationSeverity.ERROR,
                    value=path
                ))

        # Validate body size
        if body:
            body_str = json.dumps(body) if isinstance(body, (dict, list)) else str(body)
            if len(body_str) > self.max_body_size:
                errors.append(ValidationError(
                    rule="body_size",
                    field="body",
                    message=f"Body size exceeds limit of {self.max_body_size} bytes",
                    severity=ValidationSeverity.ERROR,
                    value=len(body_str)
                ))

        # Validate headers
        header_errors = self._validate_headers(headers)
        errors.extend(header_errors)

        # Validate query params
        if query_params:
            param_errors = self._validate_query_params(query_params)
            errors.extend(param_errors)

        # Apply field rules
        if body and isinstance(body, dict):
            for rule in self.rules.values():
                result = self._apply_rule(rule, body)
                if result:
                    if result.severity == ValidationSeverity.ERROR:
                        errors.append(result)
                    else:
                        warnings.append(result)

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            metadata={
                "method": method,
                "path": path,
                "rules_applied": len(self.rules)
            }
        )

    def _validate_headers(self, headers: Dict[str, str]) -> List[ValidationError]:
        """Validate request headers."""
        errors = []

        # Check content-type for POST/PUT
        content_type = headers.get("content-type", "")
        if content_type and "json" not in content_type and "form" not in content_type:
            errors.append(ValidationError(
                rule="content_type",
                field="headers.content-type",
                message="Content-Type should be JSON or form-data",
                severity=ValidationSeverity.WARNING,
                value=content_type
            ))

        # Check for suspicious headers
        suspicious = ["x-forwarded-for", "x-real-ip"]
        for header in suspicious:
            if header in headers:
                errors.append(ValidationError(
                    rule="suspicious_header",
                    field=f"headers.{header}",
                    message=f"Header {header} may indicate proxy manipulation",
                    severity=ValidationSeverity.WARNING,
                    value=headers[header]
                ))

        return errors

    def _validate_query_params(self, params: Dict[str, str]) -> List[ValidationError]:
        """Validate query parameters."""
        errors = []

        for key, value in params.items():
            # Check for SQL injection patterns
            sql_patterns = ["union", "select", "drop", "insert", "update", "delete", "--"]
            for pattern in sql_patterns:
                if pattern in value.lower():
                    errors.append(ValidationError(
                        rule="sql_injection",
                        field=f"query.{key}",
                        message=f"Possible SQL injection detected in parameter {key}",
                        severity=ValidationSeverity.ERROR,
                        value=value
                    ))

            # Check for XSS patterns
            xss_patterns = ["<script", "javascript:", "onerror="]
            for pattern in xss_patterns:
                if pattern in value.lower():
                    errors.append(ValidationError(
                        rule="xss",
                        field=f"query.{key}",
                        message=f"Possible XSS detected in parameter {key}",
                        severity=ValidationSeverity.ERROR,
                        value=value
                    ))

        return errors

    def _apply_rule(self, rule: ValidationRule, body: Dict[str, Any]) -> Optional[ValidationError]:
        """Apply a validation rule to the body."""
        value = self._get_nested_value(body, rule.field_path)

        if rule.rule_type == "required" and value is None:
            return ValidationError(
                rule=rule.name,
                field=rule.field_path,
                message=rule.message or f"Field {rule.field_path} is required",
                severity=rule.severity
            )

        if value is None:
            return None

        if rule.rule_type == "type":
            expected_type = rule.parameters.get("type", "string")
            if expected_type == "string" and not isinstance(value, str):
                return ValidationError(
                    rule=rule.name,
                    field=rule.field_path,
                    message=rule.message or f"Field {rule.field_path} must be a string",
                    severity=rule.severity,
                    value=value
                )
            elif expected_type == "integer" and not isinstance(value, int):
                return ValidationError(
                    rule=rule.name,
                    field=rule.field_path,
                    message=rule.message or f"Field {rule.field_path} must be an integer",
                    severity=rule.severity,
                    value=value
                )
            elif expected_type == "array" and not isinstance(value, list):
                return ValidationError(
                    rule=rule.name,
                    field=rule.field_path,
                    message=rule.message or f"Field {rule.field_path} must be an array",
                    severity=rule.severity,
                    value=value
                )

        if rule.rule_type == "pattern":
            pattern = rule.parameters.get("pattern", "")
            if isinstance(value, str) and not re.match(pattern, value):
                return ValidationError(
                    rule=rule.name,
                    field=rule.field_path,
                    message=rule.message or f"Field {rule.field_path} doesn't match pattern {pattern}",
                    severity=rule.severity,
                    value=value
                )

        if rule.rule_type == "range":
            min_val = rule.parameters.get("min")
            max_val = rule.parameters.get("max")
            if isinstance(value, (int, float)):
                if min_val is not None and value < min_val:
                    return ValidationError(
                        rule=rule.name,
                        field=rule.field_path,
                        message=rule.message or f"Field {rule.field_path} must be >= {min_val}",
                        severity=rule.severity,
                        value=value
                    )
                if max_val is not None and value > max_val:
                    return ValidationError(
                        rule=rule.name,
                        field=rule.field_path,
                        message=rule.message or f"Field {rule.field_path} must be <= {max_val}",
                        severity=rule.severity,
                        value=value
                    )

        if rule.rule_type == "custom":
            validator_name = rule.parameters.get("validator")
            if validator_name and validator_name in self.custom_validators:
                validator = self.custom_validators[validator_name]
                if not validator(value):
                    return ValidationError(
                        rule=rule.name,
                        field=rule.field_path,
                        message=rule.message or f"Custom validation failed for {rule.field_path}",
                        severity=rule.severity,
                        value=value
                    )

        return None

    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """Get nested value from dict using dot notation."""
        keys = path.split(".")
        current = data

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None

        return current

    def sanitize_input(self, value: str) -> str:
        """Sanitize input string."""
        # Remove HTML tags
        value = re.sub(r'<[^>]+>', '', value)
        # Remove script tags
        value = re.sub(r'<script[^>]*>.*?</script>', '', value, flags=re.DOTALL)
        # Escape special characters
        value = value.replace('&', '&amp;')
        value = value.replace('<', '&lt;')
        value = value.replace('>', '&gt;')
        return value

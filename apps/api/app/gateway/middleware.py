"""Gateway middleware for FastAPI."""
from typing import Any, Callable, Dict, Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import time
import uuid

from .rate_limiter import RateLimiter, RateLimitConfig
from .request_validator import RequestValidator, ValidationRule
from .audit_logger import AuditLogger, AuditLevel


class GatewayMiddleware(BaseHTTPMiddleware):
    """API Gateway middleware combining rate limiting, validation, and audit logging."""

    def __init__(
        self,
        app,
        rate_config: Optional[RateLimitConfig] = None,
        enable_validation: bool = True,
        enable_audit: bool = True
    ):
        super().__init__(app)
        self.rate_limiter = RateLimiter(rate_config)
        self.validator = RequestValidator() if enable_validation else None
        self.audit_logger = AuditLogger() if enable_audit else None
        self._setup_default_rules()

    def _setup_default_rules(self):
        """Setup default validation rules."""
        if self.validator:
            # Add common validation rules
            self.validator.add_rule(ValidationRule(
                name="body_required",
                field_path="body",
                rule_type="required",
                severity="warning"
            ))

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request through gateway."""
        request_id = str(uuid.uuid4())
        start_time = time.time()

        # Get client identifier
        client_id = self._get_client_id(request)

        # Rate limiting
        rate_result = self.rate_limiter.check_rate_limit(client_id, request.url.path)
        if not rate_result.allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "limit": rate_result.limit,
                    "remaining": rate_result.remaining,
                    "retry_after": rate_result.retry_after
                },
                headers={
                    "X-RateLimit-Limit": str(rate_result.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(rate_result.reset_at.timestamp())),
                    "Retry-After": str(rate_result.retry_after or 60)
                }
            )

        # Request validation
        if self.validator:
            body = None
            if request.method in ("POST", "PUT", "PATCH"):
                try:
                    body = await request.json()
                except Exception:
                    pass

            validation_result = self.validator.validate_request(
                method=request.method,
                path=str(request.url.path),
                headers=dict(request.headers),
                body=body
            )

            if not validation_result.valid:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "Validation failed",
                        "errors": [e.model_dump() for e in validation_result.errors]
                    }
                )

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000

        # Audit logging
        if self.audit_logger:
            self.audit_logger.log_api_request(
                method=request.method,
                path=str(request.url.path),
                actor=client_id,
                status_code=response.status_code,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
                request_id=request_id,
                duration_ms=duration_ms
            )

        # Add gateway headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-RateLimit-Limit"] = str(rate_result.limit)
        response.headers["X-RateLimit-Remaining"] = str(rate_result.remaining)

        return response

    def _get_client_id(self, request: Request) -> str:
        """Get client identifier from request."""
        # Check for API key
        api_key = request.headers.get("x-api-key")
        if api_key:
            return f"api_key:{api_key[:8]}..."

        # Check for auth token
        auth = request.headers.get("authorization")
        if auth:
            return f"auth:{auth[:20]}..."

        # Fall back to IP
        if request.client:
            return f"ip:{request.client.host}"

        return "unknown"

    def add_rate_limit_config(self, config: RateLimitConfig) -> None:
        """Update rate limit configuration."""
        self.rate_limiter = RateLimiter(config)

    def add_validation_rule(self, rule: ValidationRule) -> None:
        """Add a validation rule."""
        if self.validator:
            self.validator.add_rule(rule)

    def get_rate_limiter(self) -> RateLimiter:
        """Get the rate limiter instance."""
        return self.rate_limiter

    def get_audit_logger(self) -> Optional[AuditLogger]:
        """Get the audit logger instance."""
        return self.audit_logger

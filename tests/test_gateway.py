"""Tests for API Gateway — Rate Limiting, Validation, Audit Logging."""
import pytest
from datetime import datetime, timezone
from apps.api.app.gateway.rate_limiter import RateLimiter, RateLimitConfig, RateLimitStrategy
from apps.api.app.gateway.request_validator import RequestValidator, ValidationRule, ValidationSeverity
from apps.api.app.gateway.audit_logger import AuditLogger, AuditLevel


class TestRateLimiter:
    """Tests for RateLimiter."""

    def setup_method(self):
        self.config = RateLimitConfig(requests_per_minute=5)
        self.limiter = RateLimiter(self.config)

    def test_sliding_window_allows_requests(self):
        result = self.limiter.check_rate_limit("client1")
        assert result.allowed is True
        assert result.remaining == 4

    def test_sliding_window_blocks_after_limit(self):
        for _ in range(5):
            self.limiter.check_rate_limit("client2")
        result = self.limiter.check_rate_limit("client2")
        assert result.allowed is False
        assert result.retry_after is not None

    def test_token_bucket_allows_burst(self):
        limiter = RateLimiter(RateLimitConfig(strategy=RateLimitStrategy.TOKEN_BUCKET, burst_size=3))
        for _ in range(3):
            result = limiter.check_rate_limit("client3")
            assert result.allowed is True

    def test_token_bucket_blocks_after_burst(self):
        limiter = RateLimiter(RateLimitConfig(strategy=RateLimitStrategy.TOKEN_BUCKET, burst_size=2))
        for _ in range(2):
            limiter.check_rate_limit("client4")
        result = limiter.check_rate_limit("client4")
        assert result.allowed is False

    def test_fixed_window(self):
        limiter = RateLimiter(RateLimitConfig(strategy=RateLimitStrategy.FIXED_WINDOW, requests_per_minute=3))
        for _ in range(3):
            result = limiter.check_rate_limit("client5")
            assert result.allowed is True
        result = limiter.check_rate_limit("client5")
        assert result.allowed is False

    def test_separate_clients(self):
        self.limiter.check_rate_limit("clientA")
        self.limiter.check_rate_limit("clientB")
        result_a = self.limiter.check_rate_limit("clientA")
        result_b = self.limiter.check_rate_limit("clientB")
        assert result_a.remaining == 3
        assert result_b.remaining == 3

    def test_reset(self):
        for _ in range(5):
            self.limiter.check_rate_limit("client6")
        self.limiter.reset("client6")
        result = self.limiter.check_rate_limit("client6")
        assert result.allowed is True

    def test_get_usage(self):
        self.limiter.check_rate_limit("client7")
        usage = self.limiter.get_usage("client7")
        assert usage["requests_last_minute"] == 1


class TestRequestValidator:
    """Tests for RequestValidator."""

    def setup_method(self):
        self.validator = RequestValidator()

    def test_valid_request(self):
        result = self.validator.validate_request(
            method="POST",
            path="/api/test",
            headers={"content-type": "application/json"},
            body={"name": "test"}
        )
        assert result.valid is True

    def test_invalid_method(self):
        result = self.validator.validate_request(
            method="INVALID",
            path="/api/test",
            headers={}
        )
        assert result.valid is False
        assert any(e.rule == "method" for e in result.errors)

    def test_blocked_pattern(self):
        self.validator.add_blocked_pattern(r"/admin/.*")
        result = self.validator.validate_request(
            method="GET",
            path="/admin/secret",
            headers={}
        )
        assert result.valid is False
        assert any(e.rule == "blocked_pattern" for e in result.errors)

    def test_sql_injection_detection(self):
        result = self.validator.validate_request(
            method="GET",
            path="/api/test",
            headers={},
            query_params={"q": "SELECT * FROM users"}
        )
        assert result.valid is False
        assert any(e.rule == "sql_injection" for e in result.errors)

    def test_xss_detection(self):
        result = self.validator.validate_request(
            method="GET",
            path="/api/test",
            headers={},
            query_params={"q": "<script>alert(1)</script>"}
        )
        assert result.valid is False
        assert any(e.rule == "xss" for e in result.errors)

    def test_type_validation(self):
        self.validator.add_rule(ValidationRule(
            name="name_string",
            field_path="name",
            rule_type="type",
            parameters={"type": "string"}
        ))
        result = self.validator.validate_request(
            method="POST",
            path="/api/test",
            headers={"content-type": "application/json"},
            body={"name": 123}
        )
        assert result.valid is False

    def test_range_validation(self):
        self.validator.add_rule(ValidationRule(
            name="age_range",
            field_path="age",
            rule_type="range",
            parameters={"min": 0, "max": 150}
        ))
        result = self.validator.validate_request(
            method="POST",
            path="/api/test",
            headers={"content-type": "application/json"},
            body={"age": 200}
        )
        assert result.valid is False

    def test_sanitize_input(self):
        dirty = "<script>alert('xss')</script>Hello"
        clean = self.validator.sanitize_input(dirty)
        assert "<script>" not in clean
        assert "Hello" in clean


class TestAuditLogger:
    """Tests for AuditLogger."""

    def setup_method(self):
        self.logger = AuditLogger()

    def test_log_event(self):
        event = self.logger.log_event(
            level=AuditLevel.INFO,
            event_type="test",
            actor="user1",
            resource="resource1",
            action="read"
        )
        assert event.id is not None
        assert len(self.logger.events) == 1

    def test_log_api_request(self):
        event = self.logger.log_api_request(
            method="GET",
            path="/api/test",
            actor="user1",
            status_code=200
        )
        assert event.success is True

    def test_log_auth_event(self):
        event = self.logger.log_auth_event(
            event_type="login",
            actor="user1",
            success=True
        )
        assert event.level == AuditLevel.INFO

    def test_log_failed_auth(self):
        event = self.logger.log_auth_event(
            event_type="login_failed",
            actor="user1",
            success=False
        )
        assert event.level == AuditLevel.SECURITY

    def test_log_security_event(self):
        event = self.logger.log_security_event(
            event_type="brute_force",
            actor="attacker",
            resource="auth",
            ip_address="192.168.1.1"
        )
        assert event.level == AuditLevel.SECURITY

    def test_get_events_by_type(self):
        self.logger.log_event(AuditLevel.INFO, "type_a", "u1", "r1", "a1")
        self.logger.log_event(AuditLevel.INFO, "type_b", "u1", "r1", "a1")
        events = self.logger.get_events(event_type="type_a")
        assert len(events) == 1

    def test_get_events_by_actor(self):
        self.logger.log_event(AuditLevel.INFO, "t1", "actor_a", "r1", "a1")
        self.logger.log_event(AuditLevel.INFO, "t1", "actor_b", "r1", "a1")
        events = self.logger.get_events(actor="actor_a")
        assert len(events) == 1

    def test_get_stats(self):
        self.logger.log_event(AuditLevel.INFO, "t1", "u1", "r1", "a1")
        self.logger.log_event(AuditLevel.ERROR, "t2", "u2", "r2", "a2")
        stats = self.logger.get_stats()
        assert stats["total_events"] == 2
        assert stats["events_by_level"]["info"] == 1
        assert stats["events_by_level"]["error"] == 1

    def test_export_json(self):
        self.logger.log_event(AuditLevel.INFO, "t1", "u1", "r1", "a1")
        exported = self.logger.export_events("json")
        assert "t1" in exported

    def test_clear_old_events(self):
        self.logger.log_event(AuditLevel.INFO, "t1", "u1", "r1", "a1")
        cleared = self.logger.clear_old_events(days=0)
        assert cleared >= 0

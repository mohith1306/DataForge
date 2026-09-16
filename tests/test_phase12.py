"""Phase 12 Tests — Enterprise Security, Deployment & Operations."""

import pytest
from datetime import datetime, timezone

from apps.api.app.core.rbac import (
    RBACEngine,
    Role,
    Permission,
    AccessContext,
)
from apps.api.app.services.audit_trail import (
    AuditTrail,
    AuditAction,
    AuditSeverity,
)
from apps.api.app.services.secrets_manager import SecretsManager
from apps.api.app.core.observability import Observability


# ─── RBAC Tests ───────────────────────────────────────────────────────


class TestRBAC:
    def test_org_admin_has_all_permissions(self):
        engine = RBACEngine()
        for perm in Permission:
            assert engine.has_permission(Role.ORG_ADMIN, perm)

    def test_viewer_limited_permissions(self):
        engine = RBACEngine()
        assert engine.has_permission(Role.VIEWER, Permission.ORG_READ)
        assert engine.has_permission(Role.VIEWER, Permission.INCIDENT_READ)
        assert not engine.has_permission(Role.VIEWER, Permission.INCIDENT_WRITE)
        assert not engine.has_permission(Role.VIEWER, Permission.EXECUTE_HIGH_RISK)

    def test_sre_can_approve_incidents(self):
        engine = RBACEngine()
        assert engine.has_permission(Role.SRE, Permission.INCIDENT_APPROVE)
        assert engine.has_permission(Role.SRE, Permission.EXECUTE_HIGH_RISK)

    def test_data_engineer_cannot_approve(self):
        engine = RBACEngine()
        assert not engine.has_permission(Role.DATA_ENGINEER, Permission.INCIDENT_APPROVE)

    def test_analyst_read_only(self):
        engine = RBACEngine()
        assert engine.has_permission(Role.ANALYST, Permission.INCIDENT_READ)
        assert not engine.has_permission(Role.ANALYST, Permission.INCIDENT_WRITE)
        assert not engine.has_permission(Role.ANALYST, Permission.CONNECTOR_WRITE)

    def test_check_access_allowed(self):
        engine = RBACEngine()
        ctx = AccessContext(user_id="u1", org_id="o1", role=Role.SRE)
        result = engine.check_access(ctx, Permission.INCIDENT_READ)
        assert result.allowed

    def test_check_access_denied_wrong_role(self):
        engine = RBACEngine()
        ctx = AccessContext(user_id="u1", org_id="o1", role=Role.VIEWER)
        result = engine.check_access(ctx, Permission.INCIDENT_EXECUTE)
        assert not result.allowed

    def test_check_access_cross_org_denied(self):
        engine = RBACEngine()
        ctx = AccessContext(
            user_id="u1", org_id="o1", role=Role.ORG_ADMIN,
            resource_org_id="o2",
        )
        result = engine.check_access(ctx, Permission.INCIDENT_READ)
        assert not result.allowed

    def test_check_risk_permission(self):
        engine = RBACEngine()
        assert engine.check_risk_permission(Role.SRE, "high").allowed
        assert not engine.check_risk_permission(Role.DATA_ENGINEER, "high").allowed
        assert not engine.check_risk_permission(Role.ANALYST, "low").allowed

    def test_get_allowed_roles(self):
        engine = RBACEngine()
        roles = engine.get_allowed_roles(Permission.EXECUTE_CRITICAL)
        assert Role.ORG_ADMIN in roles
        assert Role.VIEWER not in roles

    def test_list_roles(self):
        engine = RBACEngine()
        roles = engine.list_roles()
        assert len(roles) == 6
        role_names = [r["role"] for r in roles]
        assert "org_admin" in role_names


# ─── Audit Trail Tests ────────────────────────────────────────────────


class TestAuditTrail:
    def test_log_entry(self):
        trail = AuditTrail()
        entry = trail.log(
            action=AuditAction.LOGIN,
            user_id="u1",
            org_id="o1",
            resource_type="user",
            resource_id="u1",
        )
        assert entry.action == AuditAction.LOGIN
        assert entry.user_id == "u1"
        assert entry.checksum

    def test_chain_integrity(self):
        trail = AuditTrail()
        for i in range(5):
            trail.log(
                action=AuditAction.INCIDENT_CREATE,
                user_id="u1",
                org_id="o1",
                resource_type="incident",
                resource_id=f"inc-{i}",
            )
        assert trail.verify_chain()

    def test_chain_broken_detection(self):
        trail = AuditTrail()
        trail.log(
            action=AuditAction.LOGIN,
            user_id="u1",
            org_id="o1",
            resource_type="user",
            resource_id="u1",
        )
        trail.entries[0].checksum = "tampered"
        assert not trail.verify_chain()

    def test_query_by_user(self):
        trail = AuditTrail()
        trail.log(action=AuditAction.LOGIN, user_id="u1", org_id="o1", resource_type="user", resource_id="u1")
        trail.log(action=AuditAction.LOGIN, user_id="u2", org_id="o1", resource_type="user", resource_id="u2")
        results = trail.query(user_id="u1")
        assert len(results) == 1

    def test_query_by_action(self):
        trail = AuditTrail()
        trail.log(action=AuditAction.LOGIN, user_id="u1", org_id="o1", resource_type="user", resource_id="u1")
        trail.log(action=AuditAction.CONNECTOR_CREATE, user_id="u1", org_id="o1", resource_type="connector", resource_id="c1")
        results = trail.query(action=AuditAction.LOGIN)
        assert len(results) == 1

    def test_query_by_severity(self):
        trail = AuditTrail()
        trail.log(action=AuditAction.LOGIN, user_id="u1", org_id="o1", resource_type="user", resource_id="u1", severity=AuditSeverity.INFO)
        trail.log(action=AuditAction.CONNECTOR_DELETE, user_id="u1", org_id="o1", resource_type="connector", resource_id="c1", severity=AuditSeverity.CRITICAL)
        results = trail.query(severity=AuditSeverity.CRITICAL)
        assert len(results) == 1

    def test_stats(self):
        trail = AuditTrail()
        trail.log(action=AuditAction.LOGIN, user_id="u1", org_id="o1", resource_type="user", resource_id="u1")
        trail.log(action=AuditAction.CONNECTOR_CREATE, user_id="u1", org_id="o1", resource_type="connector", resource_id="c1")
        stats = trail.get_stats()
        assert stats["total_entries"] == 2
        assert stats["chain_valid"]

    def test_entry_to_dict(self):
        trail = AuditTrail()
        entry = trail.log(
            action=AuditAction.INCIDENT_APPROVE,
            user_id="u1",
            org_id="o1",
            resource_type="incident",
            resource_id="inc-1",
            details={"reason": "approved"},
        )
        d = entry.to_dict()
        assert d["action"] == "incident_approve"
        assert d["details"]["reason"] == "approved"


# ─── Secrets Manager Tests ────────────────────────────────────────────


class TestSecretsManager:
    def test_store_and_retrieve(self):
        sm = SecretsManager(encryption_key="test-key-for-dev")
        sm.store_secret("db_password", "super-secret-123")
        value = sm.get_secret("db_password")
        assert value == "super-secret-123"

    def test_retrieve_nonexistent(self):
        sm = SecretsManager(encryption_key="test-key")
        assert sm.get_secret("nonexistent") is None

    def test_rotate_secret(self):
        sm = SecretsManager(encryption_key="test-key")
        sm.store_secret("api_key", "old-value")
        sm.rotate_secret("api_key", "new-value")
        assert sm.get_secret("api_key") == "new-value"

    def test_delete_secret(self):
        sm = SecretsManager(encryption_key="test-key")
        sm.store_secret("temp", "value")
        assert sm.delete_secret("temp")
        assert sm.get_secret("temp") is None

    def test_list_secrets(self):
        sm = SecretsManager(encryption_key="test-key")
        sm.store_secret("key1", "val1")
        sm.store_secret("key2", "val2")
        keys = sm.list_secrets()
        assert len(keys) == 2

    def test_mask_value(self):
        sm = SecretsManager()
        assert sm.mask_value("short") == "****"
        masked = sm.mask_value("super-secret-123")
        assert len(masked) == len("super-secret-123")
        assert masked.startswith("sup")
        assert masked.endswith("123")

    def test_export_import(self):
        sm = SecretsManager(encryption_key="test-key")
        sm.store_secret("k1", "v1")
        sm.store_secret("k2", "v2")
        exported = sm.export_encrypted()
        sm2 = SecretsManager(encryption_key="test-key")
        count = sm2.import_encrypted(exported)
        assert count == 2

    def test_entry_to_dict(self):
        sm = SecretsManager(encryption_key="test-key")
        secret = sm.store_secret("test", "value")
        d = secret.to_dict()
        assert d["key"] == "test"
        assert "encrypted_value" in d


# ─── Observability Tests ──────────────────────────────────────────────


class TestObservability:
    def test_increment(self):
        obs = Observability()
        obs.increment("requests_total")
        obs.increment("requests_total")
        assert obs.get_counter("requests_total") == 2

    def test_gauge(self):
        obs = Observability()
        obs.gauge("queue_depth", 42.0)
        assert obs.get_gauge("queue_depth") == 42.0

    def test_histogram(self):
        obs = Observability()
        obs.histogram("latency", 100.0)
        obs.histogram("latency", 200.0)
        stats = obs.get_histogram_stats("latency")
        assert stats["count"] == 2
        assert stats["avg"] == 150.0

    def test_timer(self):
        obs = Observability()
        obs.start_timer("test_op")
        import time
        time.sleep(0.01)
        duration = obs.stop_timer("test_op")
        assert duration > 0

    def test_record_api_latency(self):
        obs = Observability()
        labels = {"endpoint": "/api/incidents", "method": "GET", "status": "200"}
        obs.record_api_latency("/api/incidents", "GET", 50.0, 200)
        stats = obs.get_histogram_stats("api_latency_ms", labels)
        assert stats["count"] == 1

    def test_record_agent_latency(self):
        obs = Observability()
        labels = {"agent": "investigator", "success": "True"}
        obs.record_agent_latency("investigator", 1000.0, True)
        assert obs.get_counter("agent_executions_total", labels) == 1

    def test_record_connector_health(self):
        obs = Observability()
        labels = {"connector": "pg-1"}
        obs.record_connector_health("pg-1", True)
        assert obs.get_gauge("connector_healthy", labels) == 1.0

    def test_record_execution(self):
        obs = Observability()
        labels = {"executor": "sql", "success": "True", "risk": "low"}
        obs.record_execution("sql", True, "low")
        assert obs.get_counter("executions_total", labels) == 1

    def test_get_all_metrics(self):
        obs = Observability()
        obs.increment("test_counter")
        obs.gauge("test_gauge", 1.0)
        obs.histogram("test_hist", 42.0)
        metrics = obs.get_all_metrics()
        assert "counters" in metrics
        assert "gauges" in metrics
        assert "histograms" in metrics

    def test_labels(self):
        obs = Observability()
        obs.increment("req", labels={"method": "GET"})
        obs.increment("req", labels={"method": "POST"})
        assert obs.get_counter("req", {"method": "GET"}) == 1
        assert obs.get_counter("req", {"method": "POST"}) == 1

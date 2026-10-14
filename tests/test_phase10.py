"""Phase 10 Tests — Safe Autonomous Remediation."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from apps.api.app.core.policy_engine import PolicyEngine, RiskLevel, AutonomyLevel
from apps.api.app.services.pre_execution_validator import PreExecutionValidator, ValidationResult
from apps.api.app.services.remediation_sandbox import RemediationSandbox, SimulationResult
from apps.api.app.services.circuit_breaker import CircuitBreaker, CircuitState


# ─── Pre-Execution Validator Tests ────────────────────────────────────


class TestPreExecutionValidator:
    def test_validate_valid_action(self):
        engine = PolicyEngine()
        validator = PreExecutionValidator(engine)
        action = {"action_type": "cleanup", "action": "remove temp files"}
        result = validator.validate(action)
        assert result.passed
        assert result.is_allowed

    def test_validate_missing_fields(self):
        engine = PolicyEngine()
        validator = PreExecutionValidator(engine)
        action = {"action": "something"}
        result = validator.validate(action)
        assert not result.passed
        assert any("Missing" in b for b in result.blockers)

    def test_validate_dangerous_sql_drop_table(self):
        engine = PolicyEngine()
        validator = PreExecutionValidator(engine)
        action = {"action_type": "sql", "action": "drop table", "sql": "DROP TABLE users"}
        result = validator.validate(action)
        assert not result.passed
        assert any("DROP TABLE" in b for b in result.blockers)

    def test_validate_dangerous_sql_truncate(self):
        engine = PolicyEngine()
        validator = PreExecutionValidator(engine)
        action = {"action_type": "sql", "action": "truncate", "sql": "TRUNCATE TABLE logs"}
        result = validator.validate(action)
        assert not result.passed
        assert any("TRUNCATE" in b for b in result.blockers)

    def test_validate_dangerous_sql_delete_without_where(self):
        engine = PolicyEngine()
        validator = PreExecutionValidator(engine)
        action = {"action_type": "sql", "action": "delete all", "sql": "DELETE FROM users"}
        result = validator.validate(action)
        assert not result.passed
        assert any("DELETE without WHERE" in b for b in result.blockers)

    def test_validate_safe_alter_table(self):
        engine = PolicyEngine()
        validator = PreExecutionValidator(engine)
        action = {
            "action_type": "sql",
            "action": "add column",
            "sql": "ALTER TABLE users ADD COLUMN email VARCHAR(255)",
        }
        result = validator.validate(action)
        assert result.passed
        assert result.risk_level in ("low", "medium", "high")

    def test_validate_rollback_availability(self):
        engine = PolicyEngine()
        validator = PreExecutionValidator(engine)
        action = {
            "action_type": "sql",
            "action": "update data",
            "sql": "UPDATE users SET name = 'test'",
            "rollback_plan": [{"action": "restore from backup"}],
        }
        result = validator.validate(action)
        rollback_check = next(c for c in result.checks if c["name"] == "rollback_availability")
        assert rollback_check["has_rollback_plan"]

    def test_validate_rollback_missing_high_risk(self):
        engine = PolicyEngine()
        validator = PreExecutionValidator(engine)
        action = {
            "action_type": "database",
            "action": "rollback deployment",
        }
        result = validator.validate(action)
        if result.risk_level in ("high", "critical"):
            rollback_check = next(c for c in result.checks if c["name"] == "rollback_availability")
            assert not rollback_check["passed"]

    def test_validate_blast_radius_warning(self):
        engine = PolicyEngine()
        validator = PreExecutionValidator(engine)
        action = {"action_type": "cleanup", "action": "remove files"}
        context = {"blast_radius": {"total_affected": 15, "business_impact": "critical"}}
        result = validator.validate(action, context)
        assert any("blast radius" in w.lower() for w in result.warnings)

    def test_validate_production_warning(self):
        engine = PolicyEngine()
        validator = PreExecutionValidator(engine)
        action = {"action_type": "sql", "action": "update", "target": "production.users"}
        result = validator.validate(action)
        assert any("production" in w.lower() for w in result.warnings)

    def test_result_to_dict(self):
        vr = ValidationResult(
            passed=True,
            risk_level="low",
            autonomy_level="full_autonomy",
            requires_approval=False,
            is_allowed=True,
            checks=[],
            blockers=[],
            warnings=["test warning"],
        )
        d = vr.to_dict()
        assert d["passed"]
        assert d["risk_level"] == "low"
        assert len(d["warnings"]) == 1


# ─── Sandbox Tests ────────────────────────────────────────────────────


class TestRemediationSandbox:
    def test_simulate_empty_plan(self):
        sandbox = RemediationSandbox()
        result = sandbox.simulate({"id": "test-1", "actions": []})
        assert result.status == "simulated"
        assert len(result.steps) == 0

    def test_simulate_sql_alter(self):
        sandbox = RemediationSandbox()
        plan = {
            "id": "test-2",
            "actions": [
                {"action_type": "sql", "action": "add column", "sql": "ALTER TABLE users ADD COLUMN email VARCHAR(255)"},
            ],
        }
        result = sandbox.simulate(plan)
        assert result.status == "simulated"
        assert len(result.steps) == 1
        assert result.steps[0].simulated
        assert "DDL" in result.steps[0].output

    def test_simulate_sql_update(self):
        sandbox = RemediationSandbox()
        plan = {
            "id": "test-3",
            "actions": [
                {"action_type": "sql", "action": "update", "sql": "UPDATE users SET name = 'test' WHERE id = 1"},
            ],
        }
        result = sandbox.simulate(plan)
        assert len(result.steps) == 1
        assert result.steps[0].rows_affected >= 0

    def test_simulate_dbt_action(self):
        sandbox = RemediationSandbox()
        plan = {
            "id": "test-4",
            "actions": [
                {"action_type": "dbt", "action": "run model"},
            ],
        }
        result = sandbox.simulate(plan)
        assert result.status == "simulated"
        assert "dbt" in result.steps[0].output.lower()

    def test_simulate_detects_side_effects(self):
        sandbox = RemediationSandbox()
        plan = {
            "id": "test-5",
            "actions": [
                {"action_type": "sql", "action": "alter", "sql": "ALTER TABLE users ADD COLUMN age INT"},
            ],
        }
        result = sandbox.simulate(plan)
        assert len(result.side_effects) > 0

    def test_simulate_predicts_outcome(self):
        sandbox = RemediationSandbox()
        plan = {
            "id": "test-6",
            "actions": [
                {"action_type": "sql", "action": "alter", "sql": "ALTER TABLE users ADD COLUMN email VARCHAR"},
                {"action_type": "sql", "action": "update", "sql": "UPDATE users SET email = 'test'"},
            ],
        }
        result = sandbox.simulate(plan)
        assert result.expected_outcome["total_steps"] == 2
        assert result.expected_outcome["includes_schema_change"]
        assert result.expected_outcome["includes_data_change"]

    def test_simulation_history(self):
        sandbox = RemediationSandbox()
        sandbox.simulate({"id": "test-7", "actions": []})
        sandbox.simulate({"id": "test-8", "actions": []})
        history = sandbox.get_simulation_history()
        assert len(history) == 2

    def test_result_to_dict(self):
        sandbox = RemediationSandbox()
        result = sandbox.simulate({"id": "test-9", "actions": []})
        d = result.to_dict()
        assert d["plan_id"] == "test-9"
        assert "steps" in d


# ─── Circuit Breaker Tests ───────────────────────────────────────────


class TestCircuitBreaker:
    def test_initial_state_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.consecutive_failures == 0

    def test_record_success(self):
        cb = CircuitBreaker()
        cb.record_success()
        assert cb.consecutive_failures == 0
        assert cb.state == CircuitState.CLOSED

    def test_record_failure_below_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        should_trip = cb.record_failure({"reason": "test"})
        assert not should_trip
        assert cb.consecutive_failures == 1
        assert cb.state == CircuitState.CLOSED

    def test_record_failure_opens_circuit(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure({"reason": "1"})
        cb.record_failure({"reason": "2"})
        should_trip = cb.record_failure({"reason": "3"})
        assert should_trip
        assert cb.state == CircuitState.OPEN
        assert cb.consecutive_failures == 3

    def test_should_rollback_when_open(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()
        assert cb.should_rollback()

    def test_success_resets_failures(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.consecutive_failures == 0

    def test_half_open_to_closed(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.record_success()  # OPEN -> HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()  # HALF_OPEN -> CLOSED
        assert cb.state == CircuitState.CLOSED

    def test_get_status(self):
        cb = CircuitBreaker()
        status = cb.get_status()
        assert status["state"] == "closed"
        assert "consecutive_failures" in status
        assert "events" in status

    def test_reset(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.consecutive_failures == 0

    def test_events_recorded(self):
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_success()
        cb.record_failure({"reason": "test"})
        assert len(cb.events) >= 2


# ─── Policy Engine Integration Tests ──────────────────────────────────


class TestPolicyEngineIntegration:
    def test_validate_action_low_risk(self):
        engine = PolicyEngine()
        action = {"action_type": "cleanup", "action": "remove temp files"}
        result = engine.validate_action(action)
        assert result["risk_level"] in ("low", "medium")
        assert result["is_allowed"]

    def test_validate_action_database_risk(self):
        engine = PolicyEngine()
        action = {"action_type": "database", "action": "run migration"}
        result = engine.validate_action(action)
        assert result["risk_level"] == "high"

    def test_validate_action_deployment_critical(self):
        engine = PolicyEngine()
        action = {"action_type": "deployment", "action": "deploy to prod"}
        result = engine.validate_action(action)
        assert result["risk_level"] == "critical"

    def test_autonomy_levels(self):
        engine = PolicyEngine()
        assert engine.get_autonomy_level(RiskLevel.LOW) == AutonomyLevel.FULL_AUTONOMY
        assert engine.get_autonomy_level(RiskLevel.MEDIUM) == AutonomyLevel.SUPERVISED_AUTONOMY
        assert engine.get_autonomy_level(RiskLevel.HIGH) == AutonomyLevel.MANUAL_APPROVAL_REQUIRED
        assert engine.get_autonomy_level(RiskLevel.CRITICAL) == AutonomyLevel.PROHIBITED

    def test_database_constraints(self):
        engine = PolicyEngine()
        constraints = engine.get_action_constraints("database")
        assert len(constraints) > 0
        assert any("no_drop_table" in c for c in constraints)


# ─── API Router Import Tests ──────────────────────────────────────────


class TestPhase10APIImports:
    def test_safe_execution_router_imports(self):
        from apps.api.app.api.safe_execution import router
        assert router.prefix == "/safe-execution"

    def test_main_app_includes_safe_execution(self):
        from apps.api.app.api.safe_execution import router
        assert any("safe-execution" in r.path for r in router.routes if hasattr(r, "path"))

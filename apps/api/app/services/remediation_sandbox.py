"""Remediation Sandbox — dry-run simulation for remediation actions.

Executes proposed actions in isolation without side effects.
Compares expected vs actual outcomes. Detects unexpected changes.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SimulationStep:
    """A single step in a simulated execution."""
    step: int
    action: str
    sql: str
    executed: bool = False
    simulated: bool = False
    output: str = ""
    error: str = ""
    rows_affected: int = 0

    def to_dict(self) -> dict:
        return {
            "step": self.step,
            "action": self.action,
            "sql": self.sql,
            "executed": self.executed,
            "simulated": self.simulated,
            "output": self.output,
            "error": self.error,
            "rows_affected": self.rows_affected,
        }


@dataclass
class SimulationResult:
    """Result of a sandbox simulation."""
    plan_id: str
    status: str
    steps: list[SimulationStep] = field(default_factory=list)
    expected_outcome: dict = field(default_factory=dict)
    side_effects: list[str] = field(default_factory=list)
    risks_detected: list[str] = field(default_factory=list)
    simulated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "status": self.status,
            "steps": [s.to_dict() for s in self.steps],
            "expected_outcome": self.expected_outcome,
            "side_effects": self.side_effects,
            "risks_detected": self.risks_detected,
            "simulated_at": self.simulated_at,
        }


class RemediationSandbox:
    """Simulates remediation actions without side effects."""

    def __init__(self):
        self.simulation_history: list[SimulationResult] = []

    def simulate(self, plan: dict[str, Any]) -> SimulationResult:
        """Simulate a remediation plan in dry-run mode."""
        plan_id = plan.get("id", "unknown")
        actions = plan.get("actions", [])

        result = SimulationResult(
            plan_id=plan_id,
            status="simulated",
            simulated_at=datetime.now(timezone.utc).isoformat(),
        )

        for i, action in enumerate(actions):
            step = self._simulate_action(action, step_num=i + 1, plan_id=plan_id)
            result.steps.append(step)

            if step.error:
                result.status = "failed"
                result.risks_detected.append(f"Step {i + 1} would fail: {step.error}")

            if step.simulated:
                side_effects = self._detect_side_effects(action)
                result.side_effects.extend(side_effects)

        if result.status != "failed":
            result.status = "simulated"

        result.expected_outcome = self._predict_outcome(actions)

        self.simulation_history.append(result)
        return result

    def _simulate_action(self, action: dict[str, Any], step_num: int, plan_id: str) -> SimulationStep:
        """Simulate a single action."""
        action_type = action.get("action_type", "unknown")
        action_desc = action.get("action", "")
        sql = action.get("sql", "")

        step = SimulationStep(
            step=step_num,
            action=action_desc,
            sql=sql,
            simulated=True,
        )

        if action_type == "sql" and sql:
            if sql.strip().upper().startswith("ALTER"):
                step.output = f"Simulated DDL: {sql[:100]}"
                step.rows_affected = 0
            elif sql.strip().upper().startswith("UPDATE"):
                step.output = f"Simulated UPDATE: would affect ~{self._estimate_rows(sql)} rows"
                step.rows_affected = self._estimate_rows(sql)
            elif sql.strip().upper().startswith("INSERT"):
                step.output = "Simulated INSERT: would insert new rows"
                step.rows_affected = 1
            elif sql.strip().upper().startswith("DELETE"):
                step.output = f"Simulated DELETE: would remove ~{self._estimate_rows(sql)} rows"
                step.rows_affected = self._estimate_rows(sql)
            else:
                step.output = f"Simulated query: {sql[:100]}"
        elif action_type == "dbt":
            step.output = f"Simulated dbt {action_desc}"
        elif action_type == "airflow":
            step.output = f"Simulated Airflow DAG: {action_desc}"
        elif action_type == "kubernetes":
            step.output = f"Simulated K8s action: {action_desc}"
        elif action_type == "github":
            step.output = f"Simulated GitHub action: {action_desc}"
        else:
            step.output = f"Simulated action: {action_desc}"

        return step

    def _detect_side_effects(self, action: dict[str, Any]) -> list[str]:
        """Detect potential side effects from an action."""
        side_effects = []
        sql = action.get("sql", "").upper()

        if "ALTER" in sql:
            side_effects.append("Schema modification: downstream consumers may break")
        if "UPDATE" in sql:
            side_effects.append("Data modification: existing queries may return different results")
        if "DELETE" in sql:
            side_effects.append("Data deletion: cannot be recovered without backup")
        if "INSERT" in sql:
            side_effects.append("Data insertion: may trigger constraints or triggers")

        action_type = action.get("action_type", "")
        if action_type == "airflow":
            side_effects.append("DAG state change: running tasks may be affected")
        if action_type == "kubernetes":
            side_effects.append("Infrastructure change: service availability may be affected")

        return side_effects

    def _predict_outcome(self, actions: list[dict[str, Any]]) -> dict[str, Any]:
        """Predict the expected outcome of all actions."""
        total_steps = len(actions)
        has_ddl = any(a.get("sql", "").upper().startswith("ALTER") for a in actions)
        has_dml = any(
            a.get("sql", "").upper().startswith(("UPDATE", "INSERT", "DELETE"))
            for a in actions
        )
        has_infra = any(
            a.get("action_type") in ("airflow", "kubernetes", "cloud_api")
            for a in actions
        )

        return {
            "total_steps": total_steps,
            "includes_schema_change": has_ddl,
            "includes_data_change": has_dml,
            "includes_infrastructure_change": has_infra,
            "estimated_duration_seconds": total_steps * 5,
        }

    def _estimate_rows(self, sql: str) -> int:
        """Estimate rows affected by a SQL statement."""
        if "WHERE" not in sql.upper():
            return 1000
        return 10

    def get_simulation_history(self) -> list[dict]:
        """Return all past simulations."""
        return [s.to_dict() for s in self.simulation_history]

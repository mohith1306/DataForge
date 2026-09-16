"""KPI Tracking — tracks detection, diagnosis, remediation, and business KPIs.

Core KPIs:
- Detection: latency, precision, recall
- Diagnosis: root-cause accuracy, evidence relevance, false diagnosis rate
- Remediation: repair-plan acceptance, execution success, rollback rate
- Verification: verification precision, false resolution rate
- Business: MTTR reduction, engineer hours saved, incidents prevented
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class KPIValue:
    """A single KPI measurement."""
    name: str
    value: float
    unit: str = ""
    timestamp: str = ""
    labels: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "timestamp": self.timestamp,
            "labels": self.labels,
        }


class KPITracker:
    """Tracks KPIs for design partner evaluation."""

    def __init__(self):
        self.kpis: dict[str, list[KPIValue]] = {}
        self.incidents: list[dict] = []

    def record_detection(
        self,
        incident_id: str,
        detection_latency_ms: float,
        detected: bool = True,
        true_positive: bool | None = None,
    ):
        """Record a detection event."""
        now = datetime.now(timezone.utc).isoformat()

        self._add_kpi("detection_latency_ms", detection_latency_ms, "ms")
        self._add_kpi("incidents_detected", 1.0 if detected else 0.0)

        if true_positive is not None:
            self._add_kpi("true_positives", 1.0 if true_positive else 0.0)
            self._add_kpi("false_positives", 0.0 if true_positive else 1.0)

    def record_diagnosis(
        self,
        incident_id: str,
        diagnosis_time_ms: float,
        root_cause_correct: bool | None = None,
        evidence_relevant: bool | None = None,
    ):
        """Record a diagnosis event."""
        self._add_kpi("diagnosis_time_ms", diagnosis_time_ms, "ms")

        if root_cause_correct is not None:
            self._add_kpi("correct_diagnoses", 1.0 if root_cause_correct else 0.0)
            self._add_kpi("incorrect_diagnoses", 0.0 if root_cause_correct else 1.0)

        if evidence_relevant is not None:
            self._add_kpi("relevant_evidence", 1.0 if evidence_relevant else 0.0)

    def record_remediation(
        self,
        incident_id: str,
        plan_accepted: bool,
        execution_success: bool,
        rolled_back: bool = False,
        remediation_time_ms: float = 0.0,
    ):
        """Record a remediation event."""
        self._add_kpi("remediation_time_ms", remediation_time_ms, "ms")
        self._add_kpi("plans_accepted", 1.0 if plan_accepted else 0.0)
        self._add_kpi("plans_rejected", 0.0 if plan_accepted else 1.0)
        self._add_kpi("executions_successful", 1.0 if execution_success else 0.0)
        self._add_kpi("executions_failed", 0.0 if execution_success else 1.0)
        self._add_kpi("rollbacks", 1.0 if rolled_back else 0.0)

    def record_verification(
        self,
        incident_id: str,
        verification_passed: bool,
        false_resolution: bool = False,
    ):
        """Record a verification event."""
        self._add_kpi("verifications_passed", 1.0 if verification_passed else 0.0)
        self._add_kpi("verifications_failed", 0.0 if verification_passed else 1.0)
        if false_resolution:
            self._add_kpi("false_resolutions", 1.0)

    def record_mttr(self, incident_id: str, mttr_seconds: float):
        """Record mean time to resolution."""
        self._add_kpi("mttr_seconds", mttr_seconds, "seconds")

    def record_engineer_hours(self, hours: float):
        """Record engineer hours spent on incidents."""
        self._add_kpi("engineer_hours", hours, "hours")

    def record_incident_prevented(self):
        """Record an incident that was prevented."""
        self._add_kpi("incidents_prevented", 1.0)

    def get_detection_stats(self) -> dict:
        """Get detection KPI statistics."""
        return self._compute_stats("detection", [
            "detection_latency_ms",
            "incidents_detected",
            "true_positives",
            "false_positives",
        ])

    def get_diagnosis_stats(self) -> dict:
        """Get diagnosis KPI statistics."""
        return self._compute_stats("diagnosis", [
            "diagnosis_time_ms",
            "correct_diagnoses",
            "incorrect_diagnoses",
            "relevant_evidence",
        ])

    def get_remediation_stats(self) -> dict:
        """Get remediation KPI statistics."""
        return self._compute_stats("remediation", [
            "remediation_time_ms",
            "plans_accepted",
            "plans_rejected",
            "executions_successful",
            "executions_failed",
            "rollbacks",
        ])

    def get_verification_stats(self) -> dict:
        """Get verification KPI statistics."""
        return self._compute_stats("verification", [
            "verifications_passed",
            "verifications_failed",
            "false_resolutions",
        ])

    def get_business_stats(self) -> dict:
        """Get business KPI statistics."""
        return self._compute_stats("business", [
            "mttr_seconds",
            "engineer_hours",
            "incidents_prevented",
        ])

    def get_all_kpis(self) -> dict:
        """Get all KPI statistics."""
        return {
            "detection": self.get_detection_stats(),
            "diagnosis": self.get_diagnosis_stats(),
            "remediation": self.get_remediation_stats(),
            "verification": self.get_verification_stats(),
            "business": self.get_business_stats(),
        }

    def compute_improvement(self, baseline: dict, current: dict) -> dict:
        """Compute improvement from baseline to current."""
        improvements = {}

        for key in baseline:
            if key in current:
                base_val = baseline[key].get("avg", 0)
                curr_val = current[key].get("avg", 0)
                if base_val > 0:
                    change_pct = ((base_val - curr_val) / base_val) * 100
                    improvements[key] = {
                        "baseline": base_val,
                        "current": curr_val,
                        "change_pct": round(change_pct, 1),
                        "improved": change_pct > 0,
                    }

        return improvements

    def _add_kpi(self, name: str, value: float, unit: str = ""):
        """Add a KPI value."""
        if name not in self.kpis:
            self.kpis[name] = []
        self.kpis[name].append(KPIValue(
            name=name,
            value=value,
            unit=unit,
            timestamp=datetime.now(timezone.utc).isoformat(),
        ))

    def _compute_stats(self, category: str, kpi_names: list[str]) -> dict:
        """Compute statistics for a set of KPIs."""
        stats = {}
        for name in kpi_names:
            values = self.kpis.get(name, [])
            if not values:
                stats[name] = {"count": 0, "sum": 0, "avg": 0, "min": 0, "max": 0}
                continue

            nums = [v.value for v in values]
            stats[name] = {
                "count": len(nums),
                "sum": sum(nums),
                "avg": sum(nums) / len(nums),
                "min": min(nums),
                "max": max(nums),
                "unit": values[0].unit,
            }
        return stats

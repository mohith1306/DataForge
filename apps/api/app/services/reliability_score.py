"""Reliability Score — organization-level reliability scoring.

Dimensions:
- Pipeline health
- Data quality
- Freshness
- Schema stability
- Incident frequency
- MTTR
- Dependency risk
- Remediation success
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DimensionScore:
    """A single reliability dimension score."""
    name: str
    score: float
    weight: float
    details: dict = field(default_factory=dict)

    @property
    def weighted_score(self) -> float:
        return self.score * self.weight

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "score": round(self.score, 1),
            "weight": self.weight,
            "weighted_score": round(self.weighted_score, 1),
            "details": self.details,
        }


@dataclass
class ReliabilityReport:
    """Full reliability report for an organization."""
    org_id: str
    overall_score: float
    dimensions: list[DimensionScore]
    grade: str
    summary: str
    recommendations: list[str]

    def to_dict(self) -> dict:
        return {
            "org_id": self.org_id,
            "overall_score": round(self.overall_score, 1),
            "grade": self.grade,
            "summary": self.summary,
            "dimensions": [d.to_dict() for d in self.dimensions],
            "recommendations": self.recommendations,
        }


class ReliabilityScorer:
    """Computes organization-level reliability scores."""

    DIMENSION_WEIGHTS = {
        "pipeline_health": 0.15,
        "data_quality": 0.15,
        "freshness": 0.15,
        "schema_stability": 0.10,
        "incident_frequency": 0.15,
        "mttr": 0.10,
        "dependency_risk": 0.10,
        "remediation_success": 0.10,
    }

    def compute_score(
        self,
        org_id: str,
        metrics: dict[str, Any],
    ) -> ReliabilityReport:
        """Compute the overall reliability score from metrics."""
        dimensions = []

        pipeline_health = self._score_pipeline_health(metrics.get("pipeline_health", {}))
        dimensions.append(pipeline_health)

        data_quality = self._score_data_quality(metrics.get("data_quality", {}))
        dimensions.append(data_quality)

        freshness = self._score_freshness(metrics.get("freshness", {}))
        dimensions.append(freshness)

        schema_stability = self._score_schema_stability(metrics.get("schema_stability", {}))
        dimensions.append(schema_stability)

        incident_frequency = self._score_incident_frequency(metrics.get("incident_frequency", {}))
        dimensions.append(incident_frequency)

        mttr = self._score_mttr(metrics.get("mttr", {}))
        dimensions.append(mttr)

        dependency_risk = self._score_dependency_risk(metrics.get("dependency_risk", {}))
        dimensions.append(dependency_risk)

        remediation_success = self._score_remediation_success(metrics.get("remediation_success", {}))
        dimensions.append(remediation_success)

        overall = sum(d.weighted_score for d in dimensions)
        grade = self._compute_grade(overall)
        summary = self._compute_summary(overall, grade, dimensions)
        recommendations = self._compute_recommendations(dimensions)

        return ReliabilityReport(
            org_id=org_id,
            overall_score=overall,
            dimensions=dimensions,
            grade=grade,
            summary=summary,
            recommendations=recommendations,
        )

    def _score_pipeline_health(self, metrics: dict) -> DimensionScore:
        success_rate = metrics.get("success_rate", 100.0)
        score = min(100.0, success_rate)
        return DimensionScore(
            name="pipeline_health",
            score=score,
            weight=self.DIMENSION_WEIGHTS["pipeline_health"],
            details={"success_rate": success_rate},
        )

    def _score_data_quality(self, metrics: dict) -> DimensionScore:
        null_rate = metrics.get("null_rate", 0.0)
        score = max(0, 100 - (null_rate * 10))
        return DimensionScore(
            name="data_quality",
            score=score,
            weight=self.DIMENSION_WEIGHTS["data_quality"],
            details={"null_rate": null_rate},
        )

    def _score_freshness(self, metrics: dict) -> DimensionScore:
        avg_lag_minutes = metrics.get("avg_lag_minutes", 0)
        if avg_lag_minutes <= 5:
            score = 100.0
        elif avg_lag_minutes <= 30:
            score = 80.0
        elif avg_lag_minutes <= 60:
            score = 60.0
        elif avg_lag_minutes <= 360:
            score = 40.0
        else:
            score = 20.0
        return DimensionScore(
            name="freshness",
            score=score,
            weight=self.DIMENSION_WEIGHTS["freshness"],
            details={"avg_lag_minutes": avg_lag_minutes},
        )

    def _score_schema_stability(self, metrics: dict) -> DimensionScore:
        drift_count = metrics.get("drift_count_30d", 0)
        score = max(0, 100 - (drift_count * 5))
        return DimensionScore(
            name="schema_stability",
            score=score,
            weight=self.DIMENSION_WEIGHTS["schema_stability"],
            details={"drift_count_30d": drift_count},
        )

    def _score_incident_frequency(self, metrics: dict) -> DimensionScore:
        incidents_per_week = metrics.get("incidents_per_week", 0)
        if incidents_per_week <= 1:
            score = 100.0
        elif incidents_per_week <= 5:
            score = 75.0
        elif incidents_per_week <= 10:
            score = 50.0
        else:
            score = 25.0
        return DimensionScore(
            name="incident_frequency",
            score=score,
            weight=self.DIMENSION_WEIGHTS["incident_frequency"],
            details={"incidents_per_week": incidents_per_week},
        )

    def _score_mttr(self, metrics: dict) -> DimensionScore:
        mttr_minutes = metrics.get("mttr_minutes", 0)
        if mttr_minutes <= 15:
            score = 100.0
        elif mttr_minutes <= 60:
            score = 80.0
        elif mttr_minutes <= 240:
            score = 60.0
        elif mttr_minutes <= 1440:
            score = 40.0
        else:
            score = 20.0
        return DimensionScore(
            name="mttr",
            score=score,
            weight=self.DIMENSION_WEIGHTS["mttr"],
            details={"mttr_minutes": mttr_minutes},
        )

    def _score_dependency_risk(self, metrics: dict) -> DimensionScore:
        critical_deps = metrics.get("critical_dependencies", 0)
        score = max(0, 100 - (critical_deps * 10))
        return DimensionScore(
            name="dependency_risk",
            score=score,
            weight=self.DIMENSION_WEIGHTS["dependency_risk"],
            details={"critical_dependencies": critical_deps},
        )

    def _score_remediation_success(self, metrics: dict) -> DimensionScore:
        success_rate = metrics.get("success_rate", 100.0)
        score = min(100.0, success_rate)
        return DimensionScore(
            name="remediation_success",
            score=score,
            weight=self.DIMENSION_WEIGHTS["remediation_success"],
            details={"success_rate": success_rate},
        )

    def _compute_grade(self, score: float) -> str:
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        else:
            return "F"

    def _compute_summary(self, score: float, grade: str, dimensions: list[DimensionScore]) -> str:
        weakest = min(dimensions, key=lambda d: d.score)
        strongest = max(dimensions, key=lambda d: d.score)

        if grade == "A":
            return f"Excellent reliability ({score:.0f}/100). Strongest: {strongest.name}."
        elif grade == "B":
            return f"Good reliability ({score:.0f}/100). Focus on: {weakest.name}."
        elif grade == "C":
            return f"Moderate reliability ({score:.0f}/100). Needs improvement in: {weakest.name}."
        elif grade == "D":
            return f"Below average reliability ({score:.0f}/100). Critical: {weakest.name}."
        else:
            return f"Poor reliability ({score:.0f}/100). Immediate attention needed: {weakest.name}."

    def _compute_recommendations(self, dimensions: list[DimensionScore]) -> list[str]:
        recommendations = []
        for dim in dimensions:
            if dim.score < 50:
                recommendations.append(
                    f"URGENT: {dim.name} score is {dim.score:.0f}/100. "
                    f"Review and address immediately."
                )
            elif dim.score < 70:
                recommendations.append(
                    f"IMPROVE: {dim.name} score is {dim.score:.0f}/100. "
                    f"Consider optimization."
                )
        return recommendations

"""Preventive Reliability & Change Intelligence.

Preventive Reliability:
- Predicts incidents before they happen
- Provides preventive recommendations
- Monitors changes for potential risks

Change Intelligence:
- Correlates GitHub commits, deployments, schema changes
- Links changes to incidents
- Provides change impact analysis
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ChangeType(str, Enum):
    COMMIT = "commit"
    DEPLOYMENT = "deployment"
    SCHEMA_CHANGE = "schema_change"
    PIPELINE_CHANGE = "pipeline_change"
    CONFIG_CHANGE = "config_change"
    DATA_QUALITY_CHANGE = "data_quality_change"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ChangeEvent:
    """A change event detected by the system."""
    change_id: str
    change_type: ChangeType
    description: str
    author: str = ""
    timestamp: str = ""
    affected_resources: list[str] = field(default_factory=list)
    risk_score: float = 0.0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "change_id": self.change_id,
            "change_type": self.change_type.value,
            "description": self.description,
            "author": self.author,
            "timestamp": self.timestamp,
            "affected_resources": self.affected_resources,
            "risk_score": self.risk_score,
            "metadata": self.metadata,
        }


@dataclass
class RiskPrediction:
    """A predicted risk based on change analysis."""
    prediction_id: str
    risk_level: RiskLevel
    probability: float
    description: str
    affected_resources: list[str]
    preventive_actions: list[str]
    change_id: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "prediction_id": self.prediction_id,
            "risk_level": self.risk_level.value,
            "probability": self.probability,
            "description": self.description,
            "affected_resources": self.affected_resources,
            "preventive_actions": self.preventive_actions,
            "change_id": self.change_id,
            "confidence": self.confidence,
        }


@dataclass
class ChangeCorrelation:
    """Correlation between a change and an incident."""
    change_id: str
    incident_id: str
    correlation_score: float
    description: str
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "change_id": self.change_id,
            "incident_id": self.incident_id,
            "correlation_score": self.correlation_score,
            "description": self.description,
            "timestamp": self.timestamp,
        }


class PreventiveReliability:
    """Predicts incidents before they happen based on changes."""

    def __init__(self):
        self.predictions: list[RiskPrediction] = []
        self.change_history: list[ChangeEvent] = []

    def analyze_change(self, change: ChangeEvent) -> RiskPrediction:
        """Analyze a change and predict potential risks."""
        self.change_history.append(change)

        risk_score = self._compute_risk_score(change)
        risk_level = self._risk_level_from_score(risk_score)
        probability = min(0.95, risk_score / 100)
        preventive_actions = self._suggest_preventive_actions(change, risk_level)

        prediction = RiskPrediction(
            prediction_id=f"pred-{change.change_id}",
            risk_level=risk_level,
            probability=probability,
            description=f"Change '{change.description}' may cause {risk_level.value} risk incident",
            affected_resources=change.affected_resources,
            preventive_actions=preventive_actions,
            change_id=change.change_id,
            confidence=0.7,
        )

        self.predictions.append(prediction)
        return prediction

    def get_predictions_by_risk(self, min_risk: RiskLevel = RiskLevel.MEDIUM) -> list[RiskPrediction]:
        """Get predictions above a risk threshold."""
        risk_order = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2, RiskLevel.CRITICAL: 3}
        min_level = risk_order.get(min_risk, 0)
        return [p for p in self.predictions if risk_order.get(p.risk_level, 0) >= min_level]

    def _compute_risk_score(self, change: ChangeEvent) -> float:
        """Compute risk score for a change."""
        score = 0.0

        type_scores = {
            ChangeType.COMMIT: 20,
            ChangeType.DEPLOYMENT: 60,
            ChangeType.SCHEMA_CHANGE: 70,
            ChangeType.PIPELINE_CHANGE: 50,
            ChangeType.CONFIG_CHANGE: 40,
            ChangeType.DATA_QUALITY_CHANGE: 30,
        }
        score += type_scores.get(change.change_type, 30)

        if len(change.affected_resources) > 5:
            score += 20
        elif len(change.affected_resources) > 2:
            score += 10

        return min(100, score)

    def _risk_level_from_score(self, score: float) -> RiskLevel:
        if score >= 80:
            return RiskLevel.CRITICAL
        elif score >= 60:
            return RiskLevel.HIGH
        elif score >= 40:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def _suggest_preventive_actions(self, change: ChangeEvent, risk: RiskLevel) -> list[str]:
        actions = []
        if change.change_type == ChangeType.SCHEMA_CHANGE:
            actions.append("Run dbt tests before deploying")
            actions.append("Check downstream model dependencies")
        if change.change_type == ChangeType.DEPLOYMENT:
            actions.append("Enable canary deployment")
            actions.append("Prepare rollback plan")
        if risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            actions.append("Notify team before deploying")
            actions.append("Schedule during low-traffic window")
        return actions


class ChangeIntelligence:
    """Correlates changes across systems to find incident causes."""

    def __init__(self):
        self.changes: list[ChangeEvent] = []
        self.correlations: list[ChangeCorrelation] = []

    def record_change(self, change: ChangeEvent):
        """Record a change event."""
        self.changes.append(change)

    def find_correlated_changes(
        self,
        incident_id: str,
        incident_time: str,
        window_minutes: int = 60,
        affected_resources: list[str] | None = None,
    ) -> list[ChangeEvent]:
        """Find changes that may have caused an incident."""
        candidates = []

        for change in self.changes:
            if affected_resources:
                overlap = set(change.affected_resources) & set(affected_resources)
                if not overlap:
                    continue

            score = self._compute_correlation_score(change, affected_resources or [])
            if score > 0.3:
                candidates.append(change)

        candidates.sort(key=lambda c: self._compute_correlation_score(c, affected_resources or []), reverse=True)
        return candidates[:5]

    def _compute_correlation_score(self, change: ChangeEvent, incident_resources: list[str]) -> float:
        """Compute correlation score between a change and incident resources."""
        if not incident_resources:
            return 0.5

        overlap = set(change.affected_resources) & set(incident_resources)
        if not overlap:
            return 0.0

        return len(overlap) / len(incident_resources)

    def get_change_timeline(self, hours: int = 24) -> list[dict]:
        """Get a timeline of recent changes."""
        return [c.to_dict() for c in self.changes[-50:]]

    def get_stats(self) -> dict:
        """Get change intelligence statistics."""
        by_type = {}
        for c in self.changes:
            by_type[c.change_type.value] = by_type.get(c.change_type.value, 0) + 1

        return {
            "total_changes": len(self.changes),
            "by_type": by_type,
            "correlations_found": len(self.correlations),
        }

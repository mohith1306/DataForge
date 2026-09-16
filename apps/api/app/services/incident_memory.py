"""Incident Memory — persistent Failure DNA for learning from past incidents.

Builds a knowledge base of:
- Failure patterns (DNA)
- Root causes
- Resolution strategies
- Prevention recommendations
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FailureDNA:
    """A unique fingerprint for a failure pattern."""
    hash: str
    category: str
    severity: str
    components: list[str]
    fingerprint: str

    def to_dict(self) -> dict:
        return {
            "hash": self.hash,
            "category": self.category,
            "severity": self.severity,
            "components": self.components,
            "fingerprint": self.fingerprint,
        }


@dataclass
class IncidentRecord:
    """A recorded incident with its resolution."""
    incident_id: str
    title: str
    description: str
    severity: str
    category: str
    root_cause: str
    resolution: str
    affected_services: list[str]
    error_signatures: list[str]
    failure_dna: FailureDNA
    resolution_steps: list[str]
    environment: str = "production"
    prevention_tip: str = ""
    recorded_at: str = ""

    def to_dict(self) -> dict:
        return {
            "incident_id": self.incident_id,
            "title": self.title,
            "description": self.description,
            "severity": self.severity,
            "category": self.category,
            "root_cause": self.root_cause,
            "resolution": self.resolution,
            "affected_services": self.affected_services,
            "error_signatures": self.error_signatures,
            "failure_dna": self.failure_dna.to_dict(),
            "resolution_steps": self.resolution_steps,
            "environment": self.environment,
            "prevention_tip": self.prevention_tip,
            "recorded_at": self.recorded_at,
        }


class IncidentMemory:
    """Persistent memory of past incidents for learning and prediction."""

    def __init__(self):
        self.records: list[IncidentRecord] = []
        self.dna_index: dict[str, list[str]] = {}
        self.category_index: dict[str, list[str]] = {}
        self.service_index: dict[str, list[str]] = {}

    def generate_dna(
        self,
        category: str,
        severity: str,
        error_signatures: list[str],
    ) -> FailureDNA:
        """Generate a Failure DNA fingerprint from incident characteristics."""
        components = sorted(error_signatures)
        content = json.dumps({
            "category": category,
            "severity": severity,
            "components": components,
        }, sort_keys=True)
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:16]
        fingerprint = f"{category}:{severity}:{hash_val[:8]}"

        return FailureDNA(
            hash=hash_val,
            category=category,
            severity=severity,
            components=components,
            fingerprint=fingerprint,
        )

    def record_incident(self, record: IncidentRecord):
        """Record an incident and update indexes."""
        if not record.recorded_at:
            record.recorded_at = datetime.now(timezone.utc).isoformat()

        self.records.append(record)

        dna_hash = record.failure_dna.hash
        if dna_hash not in self.dna_index:
            self.dna_index[dna_hash] = []
        self.dna_index[dna_hash].append(record.incident_id)

        if record.category not in self.category_index:
            self.category_index[record.category] = []
        self.category_index[record.category].append(record.incident_id)

        for service in record.affected_services:
            if service not in self.service_index:
                self.service_index[service] = []
            self.service_index[service].append(record.incident_id)

        logger.info(
            "Incident recorded: %s (DNA: %s)",
            record.incident_id, record.failure_dna.fingerprint,
        )

    def find_similar(
        self,
        category: str | None = None,
        severity: str | None = None,
        error_signatures: list[str] | None = None,
        service: str | None = None,
        limit: int = 10,
    ) -> list[IncidentRecord]:
        """Find similar past incidents."""
        candidates = list(self.records)

        if category:
            candidates = [r for r in candidates if r.category == category]
        if severity:
            candidates = [r for r in candidates if r.severity == severity]
        if service:
            service_ids = set(self.service_index.get(service, []))
            candidates = [r for r in candidates if r.incident_id in service_ids]

        if error_signatures:
            def similarity(r: IncidentRecord) -> float:
                common = set(r.error_signatures) & set(error_signatures)
                total = set(r.error_signatures) | set(error_signatures)
                return len(common) / len(total) if total else 0
            candidates.sort(key=similarity, reverse=True)

        return candidates[:limit]

    def get_resolution_patterns(self, category: str) -> list[dict]:
        """Get common resolution patterns for a category."""
        records = self.category_index.get(category, [])
        resolutions = {}
        for inc_id in records:
            record = next((r for r in self.records if r.incident_id == inc_id), None)
            if record and record.resolution:
                if record.resolution not in resolutions:
                    resolutions[record.resolution] = {"count": 0, "examples": []}
                resolutions[record.resolution]["count"] += 1
                if len(resolutions[record.resolution]["examples"]) < 3:
                    resolutions[record.resolution]["examples"].append(record.incident_id)

        return sorted(
            [{"resolution": k, **v} for k, v in resolutions.items()],
            key=lambda x: x["count"],
            reverse=True,
        )

    def get_prevention_tips(self, category: str | None = None) -> list[str]:
        """Get prevention tips from past incidents."""
        tips = []
        for record in self.records:
            if record.prevention_tip:
                if category is None or record.category == category:
                    tips.append(record.prevention_tip)
        return list(set(tips))

    def get_stats(self) -> dict:
        """Get memory statistics."""
        return {
            "total_records": len(self.records),
            "unique_dna": len(self.dna_index),
            "categories": {k: len(v) for k, v in self.category_index.items()},
            "services_affected": len(self.service_index),
        }

    def predict_risk(self, category: str, service: str) -> dict:
        """Predict risk based on historical incidents."""
        similar = self.find_similar(category=category, service=service)
        if not similar:
            return {
                "risk_level": "unknown",
                "historical_count": 0,
                "recommendation": "No historical data available",
            }

        recent = [r for r in similar if r.severity in ("high", "critical")]
        return {
            "risk_level": "high" if len(recent) > 2 else "medium" if len(recent) > 0 else "low",
            "historical_count": len(similar),
            "recent_high_severity": len(recent),
            "recommendation": f"{len(similar)} similar incidents found. Review resolution patterns.",
        }

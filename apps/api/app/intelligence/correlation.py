"""Incident Correlation for grouping related incidents."""
from typing import Any, Dict, List, Optional
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, Field
from enum import Enum
import hashlib


class CorrelationStrategy(str, Enum):
    """Strategies for correlating incidents."""
    SERVICE = "service"
    ERROR_TYPE = "error_type"
    TIME_WINDOW = "time_window"
    FAILURE_DNA = "failure_dna"
    TAG = "tag"
    CUSTOM = "custom"


class CorrelationRule(BaseModel):
    """A rule for correlating incidents."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    strategy: CorrelationStrategy
    parameters: Dict[str, Any] = {}
    enabled: bool = True
    priority: int = 0


class CorrelationResult(BaseModel):
    """Result of incident correlation."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    group_id: str
    incident_ids: List[str]
    correlation_strategy: str
    confidence: float
    metadata: Dict[str, Any] = {}
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class IncidentCorrelation:
    """Correlates related incidents into groups."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.rules: Dict[str, CorrelationRule] = {}
        self.correlations: Dict[str, CorrelationResult] = {}
        self.incident_groups: Dict[str, List[str]] = {}  # group_id -> incident_ids

    def add_rule(self, rule: CorrelationRule) -> CorrelationRule:
        """Add a correlation rule."""
        self.rules[rule.id] = rule
        return rule

    def correlate(
        self,
        incidents: List[Dict[str, Any]],
        strategy: CorrelationStrategy = CorrelationStrategy.SERVICE
    ) -> List[CorrelationResult]:
        """Correlate incidents using specified strategy."""
        if strategy == CorrelationStrategy.SERVICE:
            return self._correlate_by_service(incidents)
        elif strategy == CorrelationStrategy.ERROR_TYPE:
            return self._correlate_by_error_type(incidents)
        elif strategy == CorrelationStrategy.TIME_WINDOW:
            return self._correlate_by_time_window(incidents)
        elif strategy == CorrelationStrategy.FAILURE_DNA:
            return self._correlate_by_failure_dna(incidents)
        elif strategy == CorrelationStrategy.TAG:
            return self._correlate_by_tag(incidents)
        else:
            return []

    def _correlate_by_service(self, incidents: List[Dict[str, Any]]) -> List[CorrelationResult]:
        """Correlate incidents by affected service."""
        service_groups: Dict[str, List[str]] = {}

        for incident in incidents:
            services = incident.get("affected_services", [])
            incident_id = incident.get("id", "")

            for service in services:
                if service not in service_groups:
                    service_groups[service] = []
                service_groups[service].append(incident_id)

        results = []
        for service, incident_ids in service_groups.items():
            if len(incident_ids) > 1:
                result = CorrelationResult(
                    group_id=f"service-{service}",
                    incident_ids=incident_ids,
                    correlation_strategy="service",
                    confidence=0.8,
                    metadata={"service": service}
                )
                results.append(result)
                self.correlations[result.id] = result

        return results

    def _correlate_by_error_type(self, incidents: List[Dict[str, Any]]) -> List[CorrelationResult]:
        """Correlate incidents by error type/signature."""
        error_groups: Dict[str, List[str]] = {}

        for incident in incidents:
            error_sigs = incident.get("error_signatures", [])
            incident_id = incident.get("id", "")

            for sig in error_sigs:
                sig_hash = hashlib.md5(sig.encode()).hexdigest()[:8]
                if sig_hash not in error_groups:
                    error_groups[sig_hash] = []
                error_groups[sig_hash].append(incident_id)

        results = []
        for sig_hash, incident_ids in error_groups.items():
            if len(incident_ids) > 1:
                result = CorrelationResult(
                    group_id=f"error-{sig_hash}",
                    incident_ids=incident_ids,
                    correlation_strategy="error_type",
                    confidence=0.9,
                    metadata={"error_hash": sig_hash}
                )
                results.append(result)
                self.correlations[result.id] = result

        return results

    def _correlate_by_time_window(
        self,
        incidents: List[Dict[str, Any]],
        window_minutes: int = 30
    ) -> List[CorrelationResult]:
        """Correlate incidents within a time window."""
        if not incidents:
            return []

        # Sort by created_at
        sorted_incidents = sorted(incidents, key=lambda x: x.get("created_at", ""))

        groups: List[List[str]] = []
        current_group: List[str] = []
        window_start = None

        for incident in sorted_incidents:
            created_str = incident.get("created_at", "")
            if not created_str:
                continue

            try:
                created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            except ValueError:
                continue

            if window_start is None:
                window_start = created

            if (created - window_start) <= timedelta(minutes=window_minutes):
                current_group.append(incident.get("id", ""))
            else:
                if len(current_group) > 1:
                    groups.append(current_group)
                current_group = [incident.get("id", "")]
                window_start = created

        if len(current_group) > 1:
            groups.append(current_group)

        results = []
        for i, group in enumerate(groups):
            result = CorrelationResult(
                group_id=f"time-{i}",
                incident_ids=group,
                correlation_strategy="time_window",
                confidence=0.6,
                metadata={"window_minutes": window_minutes}
            )
            results.append(result)
            self.correlations[result.id] = result

        return results

    def _correlate_by_failure_dna(self, incidents: List[Dict[str, Any]]) -> List[CorrelationResult]:
        """Correlate incidents by failure DNA fingerprint."""
        dna_groups: Dict[str, List[str]] = {}

        for incident in incidents:
            failure_dna = incident.get("failure_dna")
            if failure_dna:
                dna_hash = failure_dna.get("hash", "")
                if dna_hash:
                    if dna_hash not in dna_groups:
                        dna_groups[dna_hash] = []
                    dna_groups[dna_hash].append(incident.get("id", ""))

        results = []
        for dna_hash, incident_ids in dna_groups.items():
            if len(incident_ids) > 1:
                result = CorrelationResult(
                    group_id=f"dna-{dna_hash[:8]}",
                    incident_ids=incident_ids,
                    correlation_strategy="failure_dna",
                    confidence=0.95,
                    metadata={"dna_hash": dna_hash}
                )
                results.append(result)
                self.correlations[result.id] = result

        return results

    def _correlate_by_tag(self, incidents: List[Dict[str, Any]]) -> List[CorrelationResult]:
        """Correlate incidents by tags."""
        tag_groups: Dict[str, List[str]] = {}

        for incident in incidents:
            tags = incident.get("tags", [])
            incident_id = incident.get("id", "")

            for tag in tags:
                if tag not in tag_groups:
                    tag_groups[tag] = []
                tag_groups[tag].append(incident_id)

        results = []
        for tag, incident_ids in tag_groups.items():
            if len(incident_ids) > 1:
                result = CorrelationResult(
                    group_id=f"tag-{tag}",
                    incident_ids=incident_ids,
                    correlation_strategy="tag",
                    confidence=0.7,
                    metadata={"tag": tag}
                )
                results.append(result)
                self.correlations[result.id] = result

        return results

    def get_correlation(self, correlation_id: str) -> Optional[CorrelationResult]:
        """Get correlation by ID."""
        return self.correlations.get(correlation_id)

    def get_correlations_for_incident(self, incident_id: str) -> List[CorrelationResult]:
        """Get all correlations for an incident."""
        return [
            corr for corr in self.correlations.values()
            if incident_id in corr.incident_ids
        ]

    def list_correlations(self) -> List[CorrelationResult]:
        """List all correlations."""
        return list(self.correlations.values())

    def merge_correlations(self, correlation_ids: List[str]) -> Optional[CorrelationResult]:
        """Merge multiple correlations into one."""
        if len(correlation_ids) < 2:
            return None

        all_incident_ids = []
        for cid in correlation_ids:
            corr = self.correlations.get(cid)
            if corr:
                all_incident_ids.extend(corr.incident_ids)

        # Deduplicate
        unique_incident_ids = list(set(all_incident_ids))

        merged = CorrelationResult(
            group_id=f"merged-{uuid4().hex[:8]}",
            incident_ids=unique_incident_ids,
            correlation_strategy="merged",
            confidence=0.7,
            metadata={"merged_from": correlation_ids}
        )

        self.correlations[merged.id] = merged
        return merged

    def add_correlation_result(self, group_id: str, incident_ids: List[str]) -> CorrelationResult:
        """Helper to add a correlation result directly (for testing)."""
        result = CorrelationResult(
            group_id=group_id,
            incident_ids=incident_ids,
            correlation_strategy="manual",
            confidence=0.8
        )
        self.correlations[result.id] = result
        return result

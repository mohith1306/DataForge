"""Incident Deduplication for identifying duplicate incidents."""
from typing import Any, Dict, List, Optional
from uuid import uuid4
from datetime import datetime, timezone
from pydantic import BaseModel, Field
import hashlib
from enum import Enum


class DeduplicationStrategy(str, Enum):
    """Strategies for deduplicating incidents."""
    EXACT_MATCH = "exact_match"
    FUZZY_MATCH = "fuzzy_match"
    SIGNATURE_MATCH = "signature_match"
    DNA_MATCH = "dna_match"


class DeduplicationResult(BaseModel):
    """Result of deduplication check."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    original_incident_id: str
    duplicate_incident_id: str
    strategy: str
    similarity_score: float
    metadata: Dict[str, Any] = {}
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class IncidentDeduplication:
    """Identifies and handles duplicate incidents."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.incidents: Dict[str, Dict[str, Any]] = {}
        self.signature_index: Dict[str, List[str]] = {}  # signature -> incident_ids
        self.dna_index: Dict[str, List[str]] = {}  # dna_hash -> incident_ids
        self.deduplication_results: List[DeduplicationResult] = []

    def add_incident(self, incident: Dict[str, Any]) -> None:
        """Add an incident to the deduplication index."""
        incident_id = incident.get("id", "")
        self.incidents[incident_id] = incident

        # Index by error signatures
        for sig in incident.get("error_signatures", []):
            sig_hash = self._hash_signature(sig)
            if sig_hash not in self.signature_index:
                self.signature_index[sig_hash] = []
            self.signature_index[sig_hash].append(incident_id)

        # Index by failure DNA
        failure_dna = incident.get("failure_dna")
        if failure_dna:
            dna_hash = failure_dna.get("hash", "")
            if dna_hash:
                if dna_hash not in self.dna_index:
                    self.dna_index[dna_hash] = []
                self.dna_index[dna_hash].append(incident_id)

    def check_duplicate(
        self,
        incident: Dict[str, Any],
        strategy: DeduplicationStrategy = DeduplicationStrategy.SIGNATURE_MATCH
    ) -> Optional[DeduplicationResult]:
        """Check if an incident is a duplicate."""
        if strategy == DeduplicationStrategy.EXACT_MATCH:
            return self._check_exact_match(incident)
        elif strategy == DeduplicationStrategy.SIGNATURE_MATCH:
            return self._check_signature_match(incident)
        elif strategy == DeduplicationStrategy.DNA_MATCH:
            return self._check_dna_match(incident)
        elif strategy == DeduplicationStrategy.FUZZY_MATCH:
            return self._check_fuzzy_match(incident)
        return None

    def _check_exact_match(self, incident: Dict[str, Any]) -> Optional[DeduplicationResult]:
        """Check for exact match (same title, description, and services)."""
        title = incident.get("title", "")
        description = incident.get("description", "")
        services = sorted(incident.get("affected_services", []))

        for existing_id, existing in self.incidents.items():
            if existing_id == incident.get("id"):
                continue

            if (existing.get("title") == title and
                existing.get("description") == description and
                sorted(existing.get("affected_services", [])) == services):

                return DeduplicationResult(
                    original_incident_id=existing_id,
                    duplicate_incident_id=incident.get("id", ""),
                    strategy="exact_match",
                    similarity_score=1.0,
                    metadata={"title": title}
                )

        return None

    def _check_signature_match(self, incident: Dict[str, Any]) -> Optional[DeduplicationResult]:
        """Check for matching error signatures."""
        incident_id = incident.get("id", "")
        sigs = incident.get("error_signatures", [])

        best_match = None
        best_score = 0.0

        for sig in sigs:
            sig_hash = self._hash_signature(sig)
            matching_ids = self.signature_index.get(sig_hash, [])

            for matching_id in matching_ids:
                if matching_id == incident_id:
                    continue

                existing = self.incidents.get(matching_id, {})
                score = self._calculate_similarity(incident, existing)

                if score > best_score:
                    best_score = score
                    best_match = matching_id

        if best_match and best_score > 0.5:
            result = DeduplicationResult(
                original_incident_id=best_match,
                duplicate_incident_id=incident_id,
                strategy="signature_match",
                similarity_score=best_score
            )
            self.deduplication_results.append(result)
            return result

        return None

    def _check_dna_match(self, incident: Dict[str, Any]) -> Optional[DeduplicationResult]:
        """Check for matching failure DNA."""
        incident_id = incident.get("id", "")
        failure_dna = incident.get("failure_dna")

        if not failure_dna:
            return None

        dna_hash = failure_dna.get("hash", "")
        matching_ids = self.dna_index.get(dna_hash, [])

        for matching_id in matching_ids:
            if matching_id == incident_id:
                continue

            result = DeduplicationResult(
                original_incident_id=matching_id,
                duplicate_incident_id=incident_id,
                strategy="dna_match",
                similarity_score=0.95,
                metadata={"dna_hash": dna_hash}
            )
            self.deduplication_results.append(result)
            return result

        return None

    def _check_fuzzy_match(self, incident: Dict[str, Any]) -> Optional[DeduplicationResult]:
        """Check for fuzzy match using multiple signals."""
        incident_id = incident.get("id", "")
        best_match = None
        best_score = 0.0

        for existing_id, existing in self.incidents.items():
            if existing_id == incident_id:
                continue

            score = self._calculate_similarity(incident, existing)

            if score > best_score:
                best_score = score
                best_match = existing_id

        if best_match and best_score > 0.7:
            result = DeduplicationResult(
                original_incident_id=best_match,
                duplicate_incident_id=incident_id,
                strategy="fuzzy_match",
                similarity_score=best_score
            )
            self.deduplication_results.append(result)
            return result

        return None

    def _calculate_similarity(self, incident1: Dict, incident2: Dict) -> float:
        """Calculate similarity between two incidents."""
        score = 0.0
        factors = 0

        # Title similarity
        title1 = incident1.get("title", "").lower()
        title2 = incident2.get("title", "").lower()
        if title1 and title2:
            title_sim = self._string_similarity(title1, title2)
            score += title_sim * 0.3
            factors += 0.3

        # Service overlap
        services1 = set(incident1.get("affected_services", []))
        services2 = set(incident2.get("affected_services", []))
        if services1 and services2:
            overlap = len(services1 & services2) / max(len(services1 | services2), 1)
            score += overlap * 0.4
            factors += 0.4

        # Error signature overlap
        sigs1 = set(incident1.get("error_signatures", []))
        sigs2 = set(incident2.get("error_signatures", []))
        if sigs1 and sigs2:
            sig_overlap = len(sigs1 & sigs2) / max(len(sigs1 | sigs2), 1)
            score += sig_overlap * 0.3
            factors += 0.3

        return score / max(factors, 0.001)

    def _string_similarity(self, s1: str, s2: str) -> float:
        """Calculate string similarity using Jaccard index."""
        words1 = set(s1.split())
        words2 = set(s2.split())

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / max(union, 1)

    def _hash_signature(self, signature: str) -> str:
        """Hash an error signature."""
        return hashlib.md5(signature.encode()).hexdigest()[:16]

    def deduplicate_all(
        self,
        strategy: DeduplicationStrategy = DeduplicationStrategy.SIGNATURE_MATCH
    ) -> List[DeduplicationResult]:
        """Deduplicate all incidents."""
        results = []
        for incident in self.incidents.values():
            result = self.check_duplicate(incident, strategy)
            if result:
                results.append(result)
        return results

    def get_duplicates(self, incident_id: str) -> List[DeduplicationResult]:
        """Get all duplicates for an incident."""
        return [
            r for r in self.deduplication_results
            if r.original_incident_id == incident_id or r.duplicate_incident_id == incident_id
        ]

    def list_deduplication_results(self) -> List[DeduplicationResult]:
        """List all deduplication results."""
        return self.deduplication_results

    def get_stats(self) -> Dict[str, Any]:
        """Get deduplication statistics."""
        return {
            "total_incidents": len(self.incidents),
            "total_deduplication_results": len(self.deduplication_results),
            "unique_signatures": len(self.signature_index),
            "unique_dna_patterns": len(self.dna_index),
            "strategies_used": list(set(r.strategy for r in self.deduplication_results))
        }

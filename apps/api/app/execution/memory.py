"""Incident Memory with failure DNA storage and retrieval."""
from typing import Any, Dict, List, Optional
from uuid import uuid4
from datetime import datetime, timezone
from pydantic import BaseModel, Field
import hashlib
import json


class FailureDNA(BaseModel):
    """Unique fingerprint for a failure pattern."""
    hash: str
    components: List[str]
    severity: str
    category: str
    fingerprint: str


class IncidentRecord(BaseModel):
    """Record of an incident for memory storage."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    incident_id: str
    title: str
    description: str
    severity: str
    category: str
    root_cause: Optional[str] = None
    resolution: Optional[str] = None
    affected_services: List[str] = []
    error_signatures: List[str] = []
    failure_dna: Optional[FailureDNA] = None
    resolution_steps: List[Dict[str, Any]] = []
    execution_results: List[Dict[str, Any]] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None
    tags: List[str] = []


class IncidentMemory:
    """Memory system for storing and retrieving incident patterns."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.incidents: Dict[str, IncidentRecord] = {}
        self.failure_dna_index: Dict[str, List[str]] = {}  # hash -> incident_ids
        self.category_index: Dict[str, List[str]] = {}  # category -> incident_ids
        self.service_index: Dict[str, List[str]] = {}  # service -> incident_ids

    def generate_failure_dna(
        self,
        error_signatures: List[str],
        category: str,
        severity: str,
    ) -> FailureDNA:
        """Generate a failure DNA fingerprint."""
        # Sort signatures for consistent hashing
        sorted_signatures = sorted(error_signatures)
        
        # Create hash from components
        components = {
            "signatures": sorted_signatures,
            "category": category,
            "severity": severity,
        }
        
        hash_input = json.dumps(components, sort_keys=True)
        hash_value = hashlib.sha256(hash_input.encode()).hexdigest()[:16]
        
        # Create fingerprint
        fingerprint = f"{category}:{severity}:{hash_value[:8]}"
        
        return FailureDNA(
            hash=hash_value,
            components=sorted_signatures,
            severity=severity,
            category=category,
            fingerprint=fingerprint,
        )

    def store_incident(
        self,
        incident_id: str,
        title: str,
        description: str,
        severity: str,
        category: str,
        error_signatures: Optional[List[str]] = None,
        root_cause: Optional[str] = None,
        resolution: Optional[str] = None,
        affected_services: Optional[List[str]] = None,
        resolution_steps: Optional[List[Dict[str, Any]]] = None,
        execution_results: Optional[List[Dict[str, Any]]] = None,
        tags: Optional[List[str]] = None,
    ) -> IncidentRecord:
        """Store an incident in memory."""
        # Generate failure DNA
        failure_dna = None
        if error_signatures:
            failure_dna = self.generate_failure_dna(
                error_signatures=error_signatures,
                category=category,
                severity=severity,
            )
        
        record = IncidentRecord(
            incident_id=incident_id,
            title=title,
            description=description,
            severity=severity,
            category=category,
            root_cause=root_cause,
            resolution=resolution,
            affected_services=affected_services or [],
            error_signatures=error_signatures or [],
            failure_dna=failure_dna,
            resolution_steps=resolution_steps or [],
            execution_results=execution_results or [],
            tags=tags or [],
        )
        
        self.incidents[record.id] = record
        
        # Update indexes
        if failure_dna:
            if failure_dna.hash not in self.failure_dna_index:
                self.failure_dna_index[failure_dna.hash] = []
            self.failure_dna_index[failure_dna.hash].append(record.id)
        
        if category not in self.category_index:
            self.category_index[category] = []
        self.category_index[category].append(record.id)
        
        for service in affected_services or []:
            if service not in self.service_index:
                self.service_index[service] = []
            self.service_index[service].append(record.id)
        
        return record

    def get_incident(self, record_id: str) -> Optional[IncidentRecord]:
        """Get an incident by record ID."""
        return self.incidents.get(record_id)

    def find_similar_incidents(
        self,
        error_signatures: List[str],
        category: Optional[str] = None,
        limit: int = 10,
    ) -> List[IncidentRecord]:
        """Find similar incidents based on error signatures."""
        # Generate DNA for search
        search_dna = self.generate_failure_dna(
            error_signatures=error_signatures,
            category=category or "unknown",
            severity="unknown",
        )
        
        # Find matching incidents
        matching_ids = self.failure_dna_index.get(search_dna.hash, [])
        
        # If no exact match, find partial matches
        if not matching_ids:
            for dna_hash, incident_ids in self.failure_dna_index.items():
                # Check if any components match
                for incident_id in incident_ids:
                    incident = self.incidents.get(incident_id)
                    if incident and incident.error_signatures:
                        common = set(error_signatures) & set(incident.error_signatures)
                        if common:
                            matching_ids.extend(incident_ids)
                            break
        
        # Get unique results
        unique_ids = list(set(matching_ids))[:limit]
        return [self.incidents[rid] for rid in unique_ids if rid in self.incidents]

    def get_by_category(self, category: str, limit: int = 100) -> List[IncidentRecord]:
        """Get incidents by category."""
        incident_ids = self.category_index.get(category, [])
        return [self.incidents[rid] for rid in incident_ids[:limit] if rid in self.incidents]

    def get_by_service(self, service: str, limit: int = 100) -> List[IncidentRecord]:
        """Get incidents affecting a specific service."""
        incident_ids = self.service_index.get(service, [])
        return [self.incidents[rid] for rid in incident_ids[:limit] if rid in self.incidents]

    def resolve_incident(
        self,
        record_id: str,
        resolution: str,
        resolution_steps: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """Mark an incident as resolved."""
        incident = self.incidents.get(record_id)
        if not incident:
            return False
        
        incident.resolution = resolution
        incident.resolution_steps = resolution_steps or []
        incident.resolved_at = datetime.now(timezone.utc)
        
        return True

    def get_resolution_patterns(self, category: str) -> List[Dict[str, Any]]:
        """Get common resolution patterns for a category."""
        incidents = self.get_by_category(category)
        
        # Count resolution patterns
        resolution_counts: Dict[str, int] = {}
        for incident in incidents:
            if incident.resolution:
                resolution_counts[incident.resolution] = resolution_counts.get(incident.resolution, 0) + 1
        
        # Sort by frequency
        patterns = [
            {"resolution": res, "count": count}
            for res, count in sorted(resolution_counts.items(), key=lambda x: x[1], reverse=True)
        ]
        
        return patterns

    def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        return {
            "total_incidents": len(self.incidents),
            "categories": list(self.category_index.keys()),
            "services": list(self.service_index.keys()),
            "failure_patterns": len(self.failure_dna_index),
            "resolved_incidents": sum(
                1 for i in self.incidents.values() if i.resolved_at
            ),
        }

    def export_memory(self) -> Dict[str, Any]:
        """Export memory for persistence."""
        return {
            "incidents": {
                rid: record.model_dump()
                for rid, record in self.incidents.items()
            },
            "indexes": {
                "failure_dna": self.failure_dna_index,
                "category": self.category_index,
                "service": self.service_index,
            },
        }

    def import_memory(self, data: Dict[str, Any]) -> None:
        """Import memory from persistence."""
        # Import incidents
        for rid, record_data in data.get("incidents", {}).items():
            self.incidents[rid] = IncidentRecord(**record_data)
        
        # Import indexes
        indexes = data.get("indexes", {})
        self.failure_dna_index = indexes.get("failure_dna", {})
        self.category_index = indexes.get("category", {})
        self.service_index = indexes.get("service", {})

"""Blast Radius Calculator for impact analysis."""
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from enum import Enum


class ImpactDimension(str, Enum):
    """Dimensions for calculating blast radius."""
    SERVICE = "service"
    TEAM = "team"
    USER = "user"
    DATA = "data"
    REVENUE = "revenue"


class BlastRadiusResult(BaseModel):
    """Result of blast radius calculation."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    source_incident_id: str
    impact_dimensions: Dict[str, Any] = {}
    affected_entities: Dict[str, List[str]] = {}
    risk_score: float = 0.0
    severity: str = "unknown"
    recommendations: List[str] = []
    metadata: Dict[str, Any] = {}
    calculated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BlastRadiusCalculator:
    """Calculates blast radius of incidents."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.dependency_graph: Dict[str, Set[str]] = {}  # entity -> dependencies
        self.reverse_graph: Dict[str, Set[str]] = {}  # entity -> dependents
        self.entity_metadata: Dict[str, Dict[str, Any]] = {}
        self.calculation_results: List[BlastRadiusResult] = []

    def register_entity(
        self,
        entity_id: str,
        entity_type: str,
        dependencies: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Register an entity and its dependencies."""
        self.dependency_graph[entity_id] = set(dependencies or [])
        self.entity_metadata[entity_id] = {
            "type": entity_type,
            **(metadata or {})
        }

        # Update reverse graph
        for dep in dependencies or []:
            if dep not in self.reverse_graph:
                self.reverse_graph[dep] = set()
            self.reverse_graph[dep].add(entity_id)

    def calculate(
        self,
        incident: Dict[str, Any],
        affected_services: Optional[List[str]] = None
    ) -> BlastRadiusResult:
        """Calculate blast radius for an incident."""
        incident_id = incident.get("id", "")
        services = affected_services or incident.get("affected_services", [])

        # Calculate impact across dimensions
        impact_dimensions = {}
        affected_entities = {
            "services": [],
            "teams": [],
            "users": [],
            "data_assets": []
        }

        # Service impact
        service_impact = self._calculate_service_impact(services)
        impact_dimensions["service"] = service_impact
        affected_entities["services"] = service_impact.get("affected", [])

        # Team impact
        team_impact = self._calculate_team_impact(services)
        impact_dimensions["team"] = team_impact
        affected_entities["teams"] = team_impact.get("affected", [])

        # User impact
        user_impact = self._calculate_user_impact(services)
        impact_dimensions["user"] = user_impact

        # Data impact
        data_impact = self._calculate_data_impact(services)
        impact_dimensions["data"] = data_impact
        affected_entities["data_assets"] = data_impact.get("affected", [])

        # Calculate overall risk score
        risk_score = self._calculate_risk_score(impact_dimensions)

        # Determine severity
        severity = self._determine_severity(risk_score)

        # Generate recommendations
        recommendations = self._generate_recommendations(impact_dimensions, severity)

        result = BlastRadiusResult(
            source_incident_id=incident_id,
            impact_dimensions=impact_dimensions,
            affected_entities=affected_entities,
            risk_score=risk_score,
            severity=severity,
            recommendations=recommendations,
            metadata={"affected_services": services}
        )

        self.calculation_results.append(result)
        return result

    def _calculate_service_impact(self, services: List[str]) -> Dict[str, Any]:
        """Calculate impact on services."""
        directly_affected = set(services)
        indirectly_affected = set()

        for service in services:
            # Get services that depend on this service
            dependents = self.reverse_graph.get(service, set())
            indirectly_affected.update(dependents)

        all_affected = directly_affected | indirectly_affected

        return {
            "directly_affected": list(directly_affected),
            "indirectly_affected": list(indirectly_affected),
            "affected": list(all_affected),
            "total_count": len(all_affected),
            "impact_score": min(1.0, len(all_affected) * 0.2)
        }

    def _calculate_team_impact(self, services: List[str]) -> Dict[str, Any]:
        """Calculate impact on teams (based on service ownership)."""
        teams = set()

        for service in services:
            metadata = self.entity_metadata.get(service, {})
            team = metadata.get("team")
            if team:
                teams.add(team)

        return {
            "affected": list(teams),
            "total_count": len(teams),
            "impact_score": min(1.0, len(teams) * 0.3)
        }

    def _calculate_user_impact(self, services: List[str]) -> Dict[str, Any]:
        """Calculate impact on users (estimated)."""
        # Estimate users affected based on service criticality
        estimated_users = len(services) * 1000  # Placeholder logic

        return {
            "estimated_users_affected": estimated_users,
            "impact_score": min(1.0, estimated_users / 10000)
        }

    def _calculate_data_impact(self, services: List[str]) -> Dict[str, Any]:
        """Calculate impact on data assets."""
        data_assets = []

        for service in services:
            metadata = self.entity_metadata.get(service, {})
            assets = metadata.get("data_assets", [])
            data_assets.extend(assets)

        unique_assets = list(set(data_assets))

        return {
            "affected": unique_assets,
            "total_count": len(unique_assets),
            "impact_score": min(1.0, len(unique_assets) * 0.25)
        }

    def _calculate_risk_score(self, impact_dimensions: Dict[str, Any]) -> float:
        """Calculate overall risk score."""
        scores = []

        for dim_name, dim_data in impact_dimensions.items():
            if isinstance(dim_data, dict):
                score = dim_data.get("impact_score", 0.0)
                scores.append(score)

        if not scores:
            return 0.0

        # Weighted average
        weights = {"service": 0.4, "team": 0.2, "user": 0.3, "data": 0.1}
        weighted_sum = 0.0
        total_weight = 0.0

        for dim_name, dim_data in impact_dimensions.items():
            if isinstance(dim_data, dict):
                score = dim_data.get("impact_score", 0.0)
                weight = weights.get(dim_name, 0.25)
                weighted_sum += score * weight
                total_weight += weight

        return weighted_sum / max(total_weight, 0.001)

    def _determine_severity(self, risk_score: float) -> str:
        """Determine severity based on risk score."""
        if risk_score >= 0.8:
            return "critical"
        elif risk_score >= 0.6:
            return "high"
        elif risk_score >= 0.4:
            return "medium"
        elif risk_score >= 0.2:
            return "low"
        return "minimal"

    def _generate_recommendations(
        self,
        impact_dimensions: Dict[str, Any],
        severity: str
    ) -> List[str]:
        """Generate recommendations based on impact."""
        recommendations = []

        if severity in ("critical", "high"):
            recommendations.append("Initiate incident response procedure")
            recommendations.append("Notify affected team leads")

        service_data = impact_dimensions.get("service", {})
        if service_data.get("total_count", 0) > 5:
            recommendations.append("Consider cascade failure prevention")

        user_data = impact_dimensions.get("user", {})
        if user_data.get("estimated_users_affected", 0) > 5000:
            recommendations.append("Prepare customer communication")

        data_data = impact_dimensions.get("data", {})
        if data_data.get("total_count", 0) > 3:
            recommendations.append("Verify data integrity across affected assets")

        if not recommendations:
            recommendations.append("Monitor situation closely")

        return recommendations

    def get_dependency_chain(self, entity_id: str) -> List[str]:
        """Get the full dependency chain for an entity."""
        chain = []
        visited = set()
        self._traverse_dependencies(entity_id, chain, visited)
        return chain

    def _traverse_dependencies(self, entity_id: str, chain: List[str], visited: Set[str]):
        """Recursively traverse dependencies."""
        if entity_id in visited:
            return
        visited.add(entity_id)

        deps = self.dependency_graph.get(entity_id, set())
        for dep in deps:
            if dep not in visited:
                chain.append(dep)
                self._traverse_dependencies(dep, chain, visited)

    def get_dependents(self, entity_id: str) -> List[str]:
        """Get all entities that depend on this entity."""
        return list(self.reverse_graph.get(entity_id, set()))

    def get_calculation_results(self) -> List[BlastRadiusResult]:
        """Get all calculation results."""
        return self.calculation_results

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the blast radius calculator."""
        return {
            "total_entities": len(self.dependency_graph),
            "total_calculations": len(self.calculation_results),
            "avg_dependencies": sum(len(v) for v in self.dependency_graph.values()) / max(len(self.dependency_graph), 1),
            "avg_dependents": sum(len(v) for v in self.reverse_graph.values()) / max(len(self.reverse_graph), 1)
        }

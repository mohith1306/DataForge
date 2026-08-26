"""DataForge Agent — LangGraph state definition."""
from typing import Any, TypedDict


class IncidentState(TypedDict):
    incident_id: str
    user_request: str
    description: str
    status: str
    events: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    database_findings: list[dict[str, Any]]
    pipeline_findings: list[dict[str, Any]]
    github_findings: list[dict[str, Any]]
    analysis_results: dict[str, Any]
    root_cause: dict[str, Any]
    confidence: float
    remediation_plan: dict[str, Any]
    risk_level: str
    approval_required: bool
    approval_status: str
    execution_result: dict[str, Any]
    verification_result: dict[str, Any]
    incident_type: str
    severity: str
    business_impact: str
    data_quality_results: dict[str, Any]

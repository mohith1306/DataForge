"""Specialized AI agents for incident investigation and remediation."""
from typing import Any, Dict, List
from datetime import datetime, timezone

from .base import BaseAgent, AgentResult


class DiagnosisAgent(BaseAgent):
    """Diagnoses the root cause of incidents."""

    def __init__(self, config=None):
        super().__init__("diagnosis", config)

    async def process(self, context: Dict[str, Any]) -> AgentResult:
        """Diagnose the root cause of an incident."""
        start_time = datetime.now(timezone.utc)
        
        incident = context.get("incident", {})
        error_message = incident.get("error_message", "")
        stack_trace = incident.get("stack_trace", "")
        affected_services = incident.get("affected_services", [])
        
        # Pattern matching for common issues
        root_causes = []
        confidence = 0.0
        
        if "connection" in error_message.lower() or "timeout" in error_message.lower():
            root_causes.append("Database connection pool exhaustion")
            confidence = 0.85
        elif "null" in error_message.lower() or "none" in error_message.lower():
            root_causes.append("Null pointer exception - missing data validation")
            confidence = 0.80
        elif "memory" in error_message.lower() or "heap" in error_message.lower():
            root_causes.append("Memory leak or insufficient heap space")
            confidence = 0.90
        elif "disk" in error_message.lower() or "space" in error_message.lower():
            root_causes.append("Disk space exhaustion")
            confidence = 0.95
        elif "permission" in error_message.lower() or "access" in error_message.lower():
            root_causes.append("Permission denied - IAM policy misconfiguration")
            confidence = 0.88
        else:
            root_causes.append("Requires deeper investigation - multiple potential causes")
            confidence = 0.50
        
        # Analyze stack trace for additional clues
        if stack_trace:
            if "OutOfMemoryError" in stack_trace:
                root_causes.append("JVM heap space exhaustion")
                confidence = 0.92
            elif "StackOverflowError" in stack_trace:
                root_causes.append("Infinite recursion detected")
                confidence = 0.95
        
        elapsed_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        
        return AgentResult(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            success=True,
            data={
                "root_causes": root_causes,
                "primary_cause": root_causes[0] if root_causes else "Unknown",
                "analysis_depth": "initial" if confidence < 0.7 else "thorough",
                "stack_trace_analyzed": bool(stack_trace),
            },
            recommendations=[
                f"Investigate {root_causes[0]}",
                "Check related service health",
                "Review recent deployments",
            ],
            confidence=confidence,
            execution_time_ms=elapsed_ms,
        )

    def get_capabilities(self) -> List[str]:
        return ["root_cause_analysis", "error_pattern_matching", "stack_trace_analysis"]


class InvestigationAgent(BaseAgent):
    """Investigates incidents by gathering context from multiple sources."""

    def __init__(self, config=None):
        super().__init__("investigation", config)

    async def process(self, context: Dict[str, Any]) -> AgentResult:
        """Investigate an incident by gathering context."""
        start_time = datetime.now(timezone.utc)
        
        incident = context.get("incident", {})
        blast_radius = context.get("blast_radius", {})
        diagnosis = context.get("diagnosis", {})
        
        # Gather investigation data
        investigation_data = {
            "incident_summary": {
                "id": incident.get("id"),
                "severity": incident.get("severity", "unknown"),
                "affected_services": incident.get("affected_services", []),
                "first_seen": incident.get("created_at"),
            },
            "blast_radius_analysis": {
                "total_affected": blast_radius.get("total_affected", 0),
                "affected_nodes": blast_radius.get("affected_nodes", []),
                "business_impact": blast_radius.get("business_impact", "unknown"),
            },
            "root_cause_hypothesis": diagnosis.get("primary_cause", "Unknown"),
            "related_incidents": [],  # Would query incident history
            "recent_changes": [],  # Would query deployment history
            "metrics_anomalies": [],  # Would query monitoring data
        }
        
        # Determine investigation priority
        severity = incident.get("severity", "low")
        if severity in ("critical", "high"):
            investigation_data["priority"] = "immediate"
        else:
            investigation_data["priority"] = "standard"
        
        elapsed_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        
        return AgentResult(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            success=True,
            data=investigation_data,
            recommendations=[
                "Review blast radius impact",
                "Check for correlated incidents",
                "Analyze recent changes",
            ],
            confidence=0.75,
            execution_time_ms=elapsed_ms,
        )

    def get_capabilities(self) -> List[str]:
        return ["context_gathering", "correlation_analysis", "priority_assessment"]


class ImpactAgent(BaseAgent):
    """Assesses the business impact of incidents."""

    def __init__(self, config=None):
        super().__init__("impact", config)

    async def process(self, context: Dict[str, Any]) -> AgentResult:
        """Assess the business impact of an incident."""
        start_time = datetime.now(timezone.utc)
        
        incident = context.get("incident", {})
        blast_radius = context.get("blast_radius", {})
        
        # Calculate impact score
        severity_scores = {"critical": 100, "high": 75, "medium": 50, "low": 25}
        severity = incident.get("severity", "low")
        base_score = severity_scores.get(severity, 25)
        
        # Factor in blast radius
        affected_count = blast_radius.get("total_affected", 0)
        radius_factor = min(affected_count * 10, 50)  # Cap at 50
        
        # Factor in business criticality
        business_impact = blast_radius.get("business_impact", "low")
        criticality_scores = {"critical": 30, "high": 20, "medium": 10, "low": 5}
        criticality_factor = criticality_scores.get(business_impact, 5)
        
        total_impact_score = min(base_score + radius_factor + criticality_factor, 100)
        
        # Determine impact level
        if total_impact_score >= 80:
            impact_level = "severe"
        elif total_impact_score >= 60:
            impact_level = "significant"
        elif total_impact_score >= 40:
            impact_level = "moderate"
        else:
            impact_level = "minimal"
        
        impact_data = {
            "impact_score": total_impact_score,
            "impact_level": impact_level,
            "affected_users_estimate": affected_count * 100,  # Rough estimate
            "revenue_impact_estimate": f"${total_impact_score * 1000}",
            "sla_risk": "high" if total_impact_score >= 70 else "medium" if total_impact_score >= 40 else "low",
            "requires_immediate_action": total_impact_score >= 60,
        }
        
        elapsed_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        
        return AgentResult(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            success=True,
            data=impact_data,
            recommendations=[
                f"Impact level: {impact_level}",
                "Notify stakeholders" if total_impact_score >= 60 else "Monitor situation",
                "Escalate if needed" if total_impact_score >= 80 else "Standard response",
            ],
            confidence=0.80,
            execution_time_ms=elapsed_ms,
        )

    def get_capabilities(self) -> List[str]:
        return ["impact_assessment", "revenue_estimation", "sla_risk_analysis"]


class RepairAgent(BaseAgent):
    """Generates and executes remediation plans."""

    def __init__(self, config=None):
        super().__init__("repair", config)

    async def process(self, context: Dict[str, Any]) -> AgentResult:
        """Generate remediation actions for an incident."""
        start_time = datetime.now(timezone.utc)
        
        diagnosis = context.get("diagnosis", {})
        impact = context.get("impact", {})
        investigation = context.get("investigation", {})
        
        root_cause = diagnosis.get("primary_cause", "Unknown")
        impact_level = impact.get("impact_level", "minimal")
        
        # Generate remediation actions based on root cause
        remediation_actions = []
        
        if "connection" in root_cause.lower():
            remediation_actions.extend([
                {"action": "scale_connection_pool", "parameters": {"increase_by": 50}},
                {"action": "restart_database_connections", "parameters": {}},
                {"action": "enable_connection_monitoring", "parameters": {}},
            ])
        elif "memory" in root_cause.lower():
            remediation_actions.extend([
                {"action": "increase_heap_size", "parameters": {"new_size": "4g"}},
                {"action": "trigger_gc", "parameters": {}},
                {"action": "capture_heap_dump", "parameters": {}},
            ])
        elif "disk" in root_cause.lower():
            remediation_actions.extend([
                {"action": "cleanup_temp_files", "parameters": {"older_than_days": 7}},
                {"action": "expand_disk_volume", "parameters": {"additional_gb": 50}},
                {"action": "enable_disk_alerts", "parameters": {"threshold_percent": 80}},
            ])
        else:
            remediation_actions.extend([
                {"action": "restart_service", "parameters": {}},
                {"action": "scale_horizontal", "parameters": {"replicas": 3}},
                {"action": "enable_enhanced_logging", "parameters": {}},
            ])
        
        # Determine autonomy level based on impact and risk
        risk_score = impact.get("impact_score", 0)
        if risk_score >= 80:
            autonomy_level = "manual_approval_required"
        elif risk_score >= 50:
            autonomy_level = "supervised_autonomy"
        else:
            autonomy_level = "full_autonomy"
        
        remediation_data = {
            "actions": remediation_actions,
            "estimated_resolution_time": "15 minutes" if impact_level == "severe" else "30 minutes",
            "rollback_available": True,
            "autonomy_level": autonomy_level,
            "requires_approval": risk_score >= 50,
            "verification_steps": [
                "Verify service health after remediation",
                "Check error rates return to baseline",
                "Confirm affected users can access system",
            ],
        }
        
        elapsed_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        
        return AgentResult(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            success=True,
            data=remediation_data,
            recommendations=[
                f"Execute {len(remediation_actions)} remediation actions",
                f"Autonomy level: {autonomy_level}",
                "Monitor after remediation",
            ],
            confidence=0.75,
            execution_time_ms=elapsed_ms,
        )

    def get_capabilities(self) -> List[str]:
        return ["remediation_generation", "action_planning", "autonomy_assessment"]


class PreventionAgent(BaseAgent):
    """Prevents future incidents through pattern analysis and recommendations."""

    def __init__(self, config=None):
        super().__init__("prevention", config)

    async def process(self, context: Dict[str, Any]) -> AgentResult:
        """Generate prevention recommendations."""
        start_time = datetime.now(timezone.utc)
        
        diagnosis = context.get("diagnosis", {})
        investigation = context.get("investigation", {})
        incident_history = context.get("incident_history", [])
        
        root_cause = diagnosis.get("primary_cause", "Unknown")
        
        # Analyze patterns from incident history
        recurring_patterns = []
        if len(incident_history) > 3:
            recurring_patterns.append("Multiple incidents detected - systemic issue")
        
        # Generate prevention recommendations
        prevention_recommendations = []
        
        if "connection" in root_cause.lower():
            prevention_recommendations.extend([
                {"type": "monitoring", "recommendation": "Implement connection pool metrics alerting"},
                {"type": "architecture", "recommendation": "Add connection pooling with PgBouncer"},
                {"type": "process", "recommendation": "Implement database health checks in CI/CD"},
            ])
        elif "memory" in root_cause.lower():
            prevention_recommendations.extend([
                {"type": "monitoring", "recommendation": "Set up memory usage alerts at 70% threshold"},
                {"type": "architecture", "recommendation": "Implement circuit breakers for memory-intensive operations"},
                {"type": "process", "recommendation": "Add load testing to deployment pipeline"},
            ])
        else:
            prevention_recommendations.extend([
                {"type": "monitoring", "recommendation": "Enhance observability with distributed tracing"},
                {"type": "architecture", "recommendation": "Implement redundancy for critical components"},
                {"type": "process", "recommendation": "Conduct post-incident review for all high-severity incidents"},
            ])
        
        # Calculate prevention score
        prevention_score = max(0, 100 - len(incident_history) * 10)
        
        prevention_data = {
            "prevention_recommendations": prevention_recommendations,
            "recurring_patterns": recurring_patterns,
            "prevention_score": prevention_score,
            "risk_level": "high" if prevention_score < 50 else "medium" if prevention_score < 75 else "low",
            "recommended_actions_count": len(prevention_recommendations),
            "estimated_prevention_impact": f"{prevention_score}% risk reduction",
        }
        
        elapsed_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        
        return AgentResult(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            success=True,
            data=prevention_data,
            recommendations=[
                f"Implement {len(prevention_recommendations)} prevention measures",
                "Schedule prevention review",
                "Update runbooks based on findings",
            ],
            confidence=0.70,
            execution_time_ms=elapsed_ms,
        )

    def get_capabilities(self) -> List[str]:
        return ["pattern_analysis", "prevention_planning", "risk_assessment"]

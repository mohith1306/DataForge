from agent.graph.state import IncidentState


def investigation_to_analysis(state: IncidentState) -> str:
    """Edge: after investigation, go to analysis."""
    return "analyze"


def analysis_to_diagnosis(state: IncidentState) -> str:
    """Edge: after analysis, go to diagnosis."""
    return "diagnose"


def diagnosis_to_plan(state: IncidentState) -> str:
    """Edge: after diagnosis, go to planning."""
    return "plan"


def plan_to_approval(state: IncidentState) -> str:
    """Edge: after planning, go to approval gate."""
    return "approval"

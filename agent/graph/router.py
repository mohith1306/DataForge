from agent.graph.state import IncidentState


def route_after_investigation(state: IncidentState) -> str:
    """Route based on investigation completeness."""
    evidence = state.get("evidence", [])
    if len(evidence) < 3:
        return "investigate"
    return "diagnose"


def route_after_diagnosis(state: IncidentState) -> str:
    """Route based on confidence level."""
    confidence = state.get("confidence", 0.0)
    if confidence < 0.7:
        return "investigate"
    return "plan"


def route_after_approval(state: IncidentState) -> str:
    """Route based on approval status."""
    approval_status = state.get("approval_status", "")
    if approval_status == "rejected":
        return "verify"
    return "execute"

"""DataForge Agent — LangGraph workflow with sandbox and data quality checks."""
from langgraph.graph import END, StateGraph

from agent.graph.nodes.approval import approval_gate
from agent.graph.nodes.classify import classify
from agent.graph.nodes.diagnose import diagnose
from agent.graph.nodes.execute import execute_remediation
from agent.graph.nodes.investigate import investigate
from agent.graph.nodes.plan import plan_remediation
from agent.graph.nodes.sandbox import sandbox_analysis
from agent.graph.nodes.verify import verify_remediation
from agent.graph.state import IncidentState


def route_after_investigation(state: IncidentState) -> str:
    """Route based on investigation completeness."""
    evidence = state.get("evidence", [])
    if len(evidence) < 3:
        return "investigate"
    return "sandbox"


def route_after_sandbox(state: IncidentState) -> str:
    """Route after sandbox analysis."""
    analysis = state.get("analysis_results", {})
    if analysis.get("error"):
        return "diagnose"  # Continue even if sandbox fails
    return "diagnose"


def route_after_diagnosis(state: IncidentState) -> str:
    """Route based on confidence level."""
    confidence = state.get("confidence", 0.0)
    if confidence < 0.5:
        return "investigate"
    return "plan"


def route_after_approval(state: IncidentState) -> str:
    """Route based on approval status."""
    approval_status = state.get("approval_status", "")
    if approval_status == "rejected":
        return "investigate"
    if approval_status == "pending":
        return "end_pause"
    return "execute"


def route_after_verify(state: IncidentState) -> str:
    """Route based on verification result."""
    verification = state.get("verification_result", {})
    overall = verification.get("overall_status", "")
    if overall in ("unresolved", "partially_resolved"):
        return "investigate"
    return END


def build_graph() -> StateGraph:
    graph = StateGraph(IncidentState)

    # Add nodes
    graph.add_node("classify", classify)
    graph.add_node("investigate", investigate)
    graph.add_node("sandbox", sandbox_analysis)
    graph.add_node("diagnose", diagnose)
    graph.add_node("plan", plan_remediation)
    graph.add_node("approval", approval_gate)
    graph.add_node("execute", execute_remediation)
    graph.add_node("verify", verify_remediation)

    # Set entry point
    graph.set_entry_point("classify")

    # classify → investigate
    graph.add_edge("classify", "investigate")

    # investigate → sandbox (or loop back if not enough evidence)
    graph.add_conditional_edges(
        "investigate",
        route_after_investigation,
        {
            "investigate": "investigate",
            "sandbox": "sandbox",
        },
    )

    # sandbox → diagnose (always, even on error)
    graph.add_conditional_edges(
        "sandbox",
        route_after_sandbox,
        {
            "diagnose": "diagnose",
        },
    )

    # diagnose → plan (or loop back if low confidence)
    graph.add_conditional_edges(
        "diagnose",
        route_after_diagnosis,
        {
            "investigate": "investigate",
            "plan": "plan",
        },
    )

    # plan → approval
    graph.add_edge("plan", "approval")

    # approval → execute / investigate / pause
    graph.add_conditional_edges(
        "approval",
        route_after_approval,
        {
            "execute": "execute",
            "investigate": "investigate",
            "end_pause": END,
        },
    )

    # execute → verify
    graph.add_edge("execute", "verify")

    # verify → END (or loop back if unresolved)
    graph.add_conditional_edges(
        "verify",
        route_after_verify,
        {
            "investigate": "investigate",
            END: END,
        },
    )

    return graph.compile()

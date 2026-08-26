"""DataForge Agent — LangGraph workflow skeleton."""
from langgraph.graph import END, StateGraph

from agent.graph.state import IncidentState


def build_graph() -> StateGraph:
    graph = StateGraph(IncidentState)

    # Phase 1: Skeleton nodes — will be wired in later phases
    graph.add_node("classify", lambda s: s)
    graph.add_node("investigate", lambda s: s)
    graph.add_node("diagnose", lambda s: s)
    graph.add_node("plan", lambda s: s)
    graph.add_node("execute", lambda s: s)
    graph.add_node("verify", lambda s: s)

    graph.set_entry_point("classify")
    graph.add_edge("classify", "investigate")
    graph.add_edge("investigate", "diagnose")
    graph.add_edge("diagnose", "plan")
    graph.add_edge("plan", "execute")
    graph.add_edge("execute", "verify")
    graph.add_edge("verify", END)

    return graph.compile()

"""TrueForge-powered DataForge graph.

Alternative graph that uses TrueForge for:
- Agent execution (instead of direct LangChain calls)
- MCP tool connectivity (instead of direct Python imports)
- Sandbox (instead of custom exec)
- Human approval (instead of custom approval gate)

Falls back to the standard LangGraph path when TrueForge is unavailable.
"""

import logging
import os

from trueforge.runtime import TrueForgeRuntime

logger = logging.getLogger(__name__)

TRUEFORGE_ENABLED = os.getenv("TRUEFORGE_ENABLED", "false").lower() == "true"
TRUEFORGE_URL = os.getenv("TRUEFORGE_URL", "http://localhost:8790")
MODEL_NAME = os.getenv("MODEL_NAME", "groq/qwen3.8-27b")

_runtime: TrueForgeRuntime | None = None


def get_runtime() -> TrueForgeRuntime | None:
    """Get or create TrueForge runtime."""
    global _runtime
    if not TRUEFORGE_ENABLED:
        return None
    if _runtime is None:
        _runtime = TrueForgeRuntime(base_url=TRUEFORGE_URL, model_name=MODEL_NAME)
    return _runtime


async def trueforge_investigate(state: dict) -> dict:
    """Investigate using TrueForge subagents for parallel evidence collection."""
    runtime = get_runtime()
    if runtime is None:
        # Fallback to standard investigation
        from agent.graph.nodes.investigate import investigate
        return await investigate(state)

    incident_type = state.get("incident_type", "unknown")
    description = state.get("description", state.get("user_request", ""))
    incident_id = state.get("incident_id", "unknown")

    try:
        result = await runtime.start_investigation(
            incident_id=incident_id,
            incident_type=incident_type,
            description=description,
        )

        if result.get("status") == "error":
            logger.warning(
                f"TrueForge investigation failed, falling back: {result.get('error')}"
            )
            from agent.graph.nodes.investigate import investigate
            return await investigate(state)

        session_id = result.get("session_id")
        turn_id = result.get("turn_id")

        # Bug 6 fix: wait for investigation result and translate into evidence
        evidence = list(state.get("evidence", []))
        events = list(state.get("events", []))

        events.append({
            "type": "trueforge.started",
            "agent": "trueforge",
            "message": f"TrueForge investigation started: session {session_id}",
        })

        # Collect events from the investigation
        tool_count = 0
        findings: list[dict] = []
        try:
            async for event in runtime.stream_turn_events(session_id, turn_id):
                event_type = event.get("type", "")
                if event_type == "tool.response":
                    tool_count += 1
                    tool_name = event.get("tool_name", "unknown")
                    # Convert tool results into evidence
                    tool_result = event.get("result", {})
                    if isinstance(tool_result, dict) and not tool_result.get("error"):
                        findings.append({
                            "source": "trueforge",
                            "type": "finding",
                            "summary": f"Tool {tool_name} returned data",
                            "data": tool_result,
                            "confidence": 0.7,
                        })
                elif event_type == "model.message":
                    content = event.get("content", "")
                    if content:
                        findings.append({
                            "source": "trueforge",
                            "type": "analysis",
                            "summary": content[:500],
                            "data": {"raw": content},
                            "confidence": 0.6,
                        })
        except Exception as e:
            logger.warning(f"Error streaming TrueForge events: {e}")

        # Convert findings into evidence format
        for finding in findings:
            evidence.append({
                "source": finding.get("source", "trueforge"),
                "type": finding.get("type", "finding"),
                "summary": finding.get("summary", ""),
                "data": finding.get("data", {}),
                "confidence": finding.get("confidence", 0.5),
                "is_hypothesis": finding.get("type") == "analysis",
            })

        events.append({
            "type": "trueforge.completed",
            "agent": "trueforge",
            "message": (
                f"TrueForge investigation completed: "
                f"{len(evidence)} evidence items, {tool_count} tools called"
            ),
        })

        return {
            "status": "investigating",
            "evidence": evidence,
            "events": events,
            "trueforge_session_id": session_id,
            "trueforge_turn_id": turn_id,
        }

    except Exception as e:
        logger.error(f"TrueForge investigation failed: {e}")
        from agent.graph.nodes.investigate import investigate
        return await investigate(state)


async def trueforge_sandbox(state: dict) -> dict:
    """Run sandbox analysis using TrueForge sandbox."""
    runtime = get_runtime()
    if runtime is None:
        from agent.graph.nodes.sandbox import sandbox_analysis
        return await sandbox_analysis(state)

    # TrueForge handles sandbox through its own execution
    # The agent will use sandbox-as-tool automatically
    return {
        "status": "analyzing",
        "analysis_results": {
            "code_output": "Sandbox delegated to TrueForge",
            "result": None,
            "error": None,
            "execution_time": 0,
            "analysis_type": state.get("incident_type", "unknown"),
            "delegated_to_trueforge": True,
        },
        "events": state.get("events", []) + [
            {
                "type": "sandbox.delegated",
                "agent": "trueforge",
                "message": "Sandbox analysis delegated to TrueForge runtime",
            }
        ],
    }


async def trueforge_approval(state: dict) -> dict:
    """Approval gate using TrueForge human checkpoint."""
    runtime = get_runtime()
    if runtime is None:
        from agent.graph.nodes.approval import approval_gate
        return await approval_gate(state)

    plan = state.get("remediation_plan", {})
    actions = plan.get("actions", [])

    # Check if approval is required
    from agent.tools.risk import requires_approval
    if not requires_approval(actions):
        return {
            "approval_status": "auto_approved",
            "approval_note": "Low-risk actions auto-approved",
        }

    # TrueForge handles approval through its checkpoint mechanism
    # The agent will pause and wait for human approval
    return {
        "approval_status": "pending_trueforge",
        "trueforge_session_id": state.get("trueforge_session_id"),
        "events": state.get("events", []) + [
            {
                "type": "approval.required",
                "agent": "trueforge",
                "message": "Waiting for human approval via TrueForge checkpoint",
            }
        ],
    }


def build_trueforge_graph():
    """Build graph with TrueForge integration, falling back to standard nodes."""
    from langgraph.graph import END, StateGraph

    from agent.graph.nodes.classify import classify
    from agent.graph.nodes.diagnose import diagnose
    from agent.graph.nodes.execute import execute_remediation
    from agent.graph.nodes.plan import plan_remediation
    from agent.graph.nodes.verify import verify_remediation
    from agent.graph.state import IncidentState

    def route_after_investigation(state: IncidentState) -> str:
        evidence = state.get("evidence", [])
        if len(evidence) < 3:
            return "investigate"
        return "sandbox"

    def route_after_diagnosis(state: IncidentState) -> str:
        confidence = state.get("confidence", 0.0)
        if confidence < 0.5:
            return "investigate"
        return "plan"

    def route_after_approval(state: IncidentState) -> str:
        approval_status = state.get("approval_status", "")
        if approval_status == "rejected":
            return "investigate"
        if approval_status in ("pending", "pending_trueforge"):
            return "end_pause"
        return "execute"

    def route_after_verify(state: IncidentState) -> str:
        verification = state.get("verification_result", {})
        overall = verification.get("overall_status", "")
        if overall in ("unresolved", "partially_resolved"):
            return "investigate"
        return END

    graph = StateGraph(IncidentState)

    # Use TrueForge-powered nodes where available
    graph.add_node("classify", classify)
    graph.add_node("investigate", trueforge_investigate)
    graph.add_node("sandbox", trueforge_sandbox)
    graph.add_node("diagnose", diagnose)
    graph.add_node("plan", plan_remediation)
    graph.add_node("approval", trueforge_approval)
    graph.add_node("execute", execute_remediation)
    graph.add_node("verify", verify_remediation)

    graph.set_entry_point("classify")
    graph.add_edge("classify", "investigate")

    graph.add_conditional_edges(
        "investigate",
        route_after_investigation,
        {"investigate": "investigate", "sandbox": "sandbox"},
    )

    graph.add_edge("sandbox", "diagnose")

    graph.add_conditional_edges(
        "diagnose",
        route_after_diagnosis,
        {"investigate": "investigate", "plan": "plan"},
    )

    graph.add_edge("plan", "approval")

    graph.add_conditional_edges(
        "approval",
        route_after_approval,
        {"execute": "execute", "investigate": "investigate", "end_pause": END},
    )

    graph.add_edge("execute", "verify")

    graph.add_conditional_edges(
        "verify",
        route_after_verify,
        {"investigate": "investigate", END: END},
    )

    return graph.compile()

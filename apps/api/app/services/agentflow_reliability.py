"""AgentFlow Reliability — monitors agent workflows for failures and anomalies.

Tracks:
- Failed agents and workflows
- Tool failures
- Data dependency failures
- Execution anomalies
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class ToolStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


@dataclass
class ToolCall:
    """A single tool call within an agent workflow."""
    tool_name: str
    status: ToolStatus
    duration_ms: float = 0.0
    input_summary: str = ""
    output_summary: str = ""
    error_message: str = ""

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "status": self.status.value,
            "duration_ms": self.duration_ms,
            "input_summary": self.input_summary[:200],
            "output_summary": self.output_summary[:200],
            "error_message": self.error_message,
        }


@dataclass
class AgentRun:
    """An agent execution run."""
    run_id: str
    agent_name: str
    status: AgentStatus
    workflow_name: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_data: dict = field(default_factory=dict)
    output_data: dict = field(default_factory=dict)
    error_message: str = ""
    started_at: str = ""
    completed_at: str = ""
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "agent_name": self.agent_name,
            "status": self.status.value,
            "workflow_name": self.workflow_name,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "error_message": self.error_message,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
        }


@dataclass
class ReliabilityEvent:
    """A reliability event detected from agent monitoring."""
    event_id: str
    event_type: str
    severity: str
    agent_name: str
    run_id: str
    message: str
    details: dict = field(default_factory=dict)
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "severity": self.severity,
            "agent_name": self.agent_name,
            "run_id": self.run_id,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp,
        }


class AgentFlowReliability:
    """Monitors agent workflows for reliability issues."""

    def __init__(self):
        self.agent_runs: list[AgentRun] = []
        self.reliability_events: list[ReliabilityEvent] = []

    async def record_run(self, run: AgentRun) -> list[ReliabilityEvent]:
        """Record an agent run and detect reliability issues."""
        self.agent_runs.append(run)
        events = []

        if run.status == AgentStatus.FAILED:
            event = ReliabilityEvent(
                event_id=f"agent-fail-{run.run_id}",
                event_type="agent_failure",
                severity="high",
                agent_name=run.agent_name,
                run_id=run.run_id,
                message=f"Agent '{run.agent_name}' failed: {run.error_message}",
                details={"error": run.error_message, "workflow": run.workflow_name},
                timestamp=run.completed_at or datetime.now(timezone.utc).isoformat(),
            )
            events.append(event)
            self.reliability_events.append(event)

        if run.status == AgentStatus.TIMEOUT:
            event = ReliabilityEvent(
                event_id=f"agent-timeout-{run.run_id}",
                event_type="agent_timeout",
                severity="high",
                agent_name=run.agent_name,
                run_id=run.run_id,
                message=f"Agent '{run.agent_name}' timed out after {run.duration_ms}ms",
                details={"duration_ms": run.duration_ms},
                timestamp=run.completed_at or datetime.now(timezone.utc).isoformat(),
            )
            events.append(event)
            self.reliability_events.append(event)

        failed_tools = [tc for tc in run.tool_calls if tc.status == ToolStatus.FAILED]
        for tc in failed_tools:
            event = ReliabilityEvent(
                event_id=f"tool-fail-{run.run_id}-{tc.tool_name}",
                event_type="tool_failure",
                severity="medium",
                agent_name=run.agent_name,
                run_id=run.run_id,
                message=f"Tool '{tc.tool_name}' failed: {tc.error_message}",
                details={"tool": tc.tool_name, "error": tc.error_message},
                timestamp=run.completed_at or datetime.now(timezone.utc).isoformat(),
            )
            events.append(event)
            self.reliability_events.append(event)

        if run.tool_calls:
            slow_tools = [tc for tc in run.tool_calls if tc.duration_ms > 30000]
            for tc in slow_tools:
                event = ReliabilityEvent(
                    event_id=f"tool-slow-{run.run_id}-{tc.tool_name}",
                    event_type="execution_anomaly",
                    severity="medium",
                    agent_name=run.agent_name,
                    run_id=run.run_id,
                    message=f"Tool '{tc.tool_name}' slow: {tc.duration_ms}ms",
                    details={"tool": tc.tool_name, "duration_ms": tc.duration_ms},
                    timestamp=run.completed_at or datetime.now(timezone.utc).isoformat(),
                )
                events.append(event)
                self.reliability_events.append(event)

        return events

    def get_agent_health(self, agent_name: str) -> dict:
        """Get health summary for a specific agent."""
        runs = [r for r in self.agent_runs if r.agent_name == agent_name]
        if not runs:
            return {"agent": agent_name, "status": "unknown", "total_runs": 0}

        failed = [r for r in runs if r.status in (AgentStatus.FAILED, AgentStatus.TIMEOUT)]
        success_rate = (len(runs) - len(failed)) / len(runs) * 100

        return {
            "agent": agent_name,
            "status": "healthy" if success_rate > 90 else "degraded" if success_rate > 50 else "unhealthy",
            "total_runs": len(runs),
            "successful": len(runs) - len(failed),
            "failed": len(failed),
            "success_rate": round(success_rate, 1),
        }

    def get_workflow_health(self, workflow_name: str) -> dict:
        """Get health summary for a specific workflow."""
        runs = [r for r in self.agent_runs if r.workflow_name == workflow_name]
        if not runs:
            return {"workflow": workflow_name, "status": "unknown", "total_runs": 0}

        failed = [r for r in runs if r.status in (AgentStatus.FAILED, AgentStatus.TIMEOUT)]
        success_rate = (len(runs) - len(failed)) / len(runs) * 100

        return {
            "workflow": workflow_name,
            "status": "healthy" if success_rate > 90 else "degraded" if success_rate > 50 else "unhealthy",
            "total_runs": len(runs),
            "successful": len(runs) - len(failed),
            "failed": len(failed),
            "success_rate": round(success_rate, 1),
        }

    def get_tool_reliability(self) -> list[dict]:
        """Get reliability stats for all tools."""
        tool_stats: dict[str, dict] = {}
        for run in self.agent_runs:
            for tc in run.tool_calls:
                if tc.tool_name not in tool_stats:
                    tool_stats[tc.tool_name] = {"total": 0, "failed": 0, "slow": 0}
                tool_stats[tc.tool_name]["total"] += 1
                if tc.status == ToolStatus.FAILED:
                    tool_stats[tc.tool_name]["failed"] += 1
                if tc.duration_ms > 30000:
                    tool_stats[tc.tool_name]["slow"] += 1

        result = []
        for tool_name, stats in tool_stats.items():
            success_rate = (stats["total"] - stats["failed"]) / stats["total"] * 100
            result.append({
                "tool": tool_name,
                "total_calls": stats["total"],
                "failed": stats["failed"],
                "slow": stats["slow"],
                "success_rate": round(success_rate, 1),
            })
        return sorted(result, key=lambda x: x["success_rate"])

    def get_recent_events(self, limit: int = 20) -> list[dict]:
        """Get recent reliability events."""
        return [e.to_dict() for e in self.reliability_events[-limit:]]

"""Phase 11 Tests — e6data Integration & Agentic Data Plane."""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from apps.api.app.services.e6data_connector import (
    E6DataConnector,
    QueryTelemetry,
    IngestTelemetry,
    TelemetryType,
    Severity,
)
from apps.api.app.services.agentflow_reliability import (
    AgentFlowReliability,
    AgentRun,
    AgentStatus,
    ToolCall,
    ToolStatus,
)


# ─── e6data Connector Tests ───────────────────────────────────────────


class TestE6DataConnector:
    @pytest.mark.asyncio
    async def test_ingest_query_event_success(self):
        connector = E6DataConnector()
        qt = QueryTelemetry(
            query_id="q1",
            query_text="SELECT * FROM users",
            status="SUCCESS",
            duration_ms=150.0,
            rows_returned=100,
        )
        event = await connector.ingest_query_event(qt)
        assert event.event_type == TelemetryType.QUERY_LATENCY
        assert event.severity == Severity.LOW

    @pytest.mark.asyncio
    async def test_ingest_query_event_failure(self):
        connector = E6DataConnector()
        qt = QueryTelemetry(
            query_id="q2",
            query_text="SELECT * FROM missing_table",
            status="FAILED",
            error_message="Table not found",
        )
        event = await connector.ingest_query_event(qt)
        assert event.event_type == TelemetryType.QUERY_FAILURE
        assert event.severity == Severity.HIGH

    @pytest.mark.asyncio
    async def test_ingest_query_event_slow(self):
        connector = E6DataConnector()
        qt = QueryTelemetry(
            query_id="q3",
            query_text="SELECT * FROM large_table",
            status="SUCCESS",
            duration_ms=45000.0,
        )
        event = await connector.ingest_query_event(qt)
        assert event.severity in (Severity.MEDIUM, Severity.HIGH)

    @pytest.mark.asyncio
    async def test_ingest_pipeline_event_success(self):
        connector = E6DataConnector()
        it = IngestTelemetry(
            pipeline_id="p1",
            pipeline_name="users-ingest",
            status="SUCCESS",
            records_processed=1000,
        )
        event = await connector.ingest_pipeline_event(it)
        assert event.event_type == TelemetryType.FRESHNESS_ANOMALY
        assert event.severity == Severity.LOW

    @pytest.mark.asyncio
    async def test_ingest_pipeline_event_failure(self):
        connector = E6DataConnector()
        it = IngestTelemetry(
            pipeline_id="p2",
            pipeline_name="orders-ingest",
            status="FAILED",
            error_message="CDC lag exceeded",
        )
        event = await connector.ingest_pipeline_event(it)
        assert event.event_type == TelemetryType.INGEST_FAILURE
        assert event.severity == Severity.HIGH

    @pytest.mark.asyncio
    async def test_ingest_pipeline_event_high_lag(self):
        connector = E6DataConnector()
        it = IngestTelemetry(
            pipeline_id="p3",
            pipeline_name="events-ingest",
            status="RUNNING",
            lag_seconds=600,
        )
        event = await connector.ingest_pipeline_event(it)
        assert event.severity == Severity.HIGH

    @pytest.mark.asyncio
    async def test_get_anomalies(self):
        connector = E6DataConnector()
        await connector.ingest_query_event(
            QueryTelemetry(query_id="q1", query_text="SELECT 1", status="FAILED", error_message="err")
        )
        await connector.ingest_query_event(
            QueryTelemetry(query_id="q2", query_text="SELECT 1", status="SUCCESS", duration_ms=10)
        )
        anomalies = connector.get_anomalies(min_severity=Severity.HIGH)
        assert len(anomalies) == 1

    def test_get_resource_health_no_events(self):
        connector = E6DataConnector()
        health = connector.get_resource_health("unknown-resource")
        assert health["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_get_resource_health_with_events(self):
        connector = E6DataConnector()
        await connector.ingest_query_event(
            QueryTelemetry(query_id="q1", query_text="SELECT 1", status="FAILED", error_message="err")
        )
        health = connector.get_resource_health("q1")
        assert health["status"] == "degraded"

    def test_telemetry_to_dict(self):
        qt = QueryTelemetry(query_id="q1", query_text="SELECT 1", status="SUCCESS")
        d = qt.to_dict()
        assert d["query_id"] == "q1"

    def test_ingest_telemetry_to_dict(self):
        it = IngestTelemetry(pipeline_id="p1", pipeline_name="test", status="SUCCESS")
        d = it.to_dict()
        assert d["pipeline_id"] == "p1"


# ─── AgentFlow Reliability Tests ──────────────────────────────────────


class TestAgentFlowReliability:
    @pytest.mark.asyncio
    async def test_record_successful_run(self):
        af = AgentFlowReliability()
        run = AgentRun(
            run_id="r1",
            agent_name="investigator",
            status=AgentStatus.COMPLETED,
            tool_calls=[
                ToolCall(tool_name="get_pipeline_status", status=ToolStatus.SUCCESS, duration_ms=100),
            ],
        )
        events = await af.record_run(run)
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_record_failed_run(self):
        af = AgentFlowReliability()
        run = AgentRun(
            run_id="r2",
            agent_name="investigator",
            status=AgentStatus.FAILED,
            error_message="Connection timeout",
        )
        events = await af.record_run(run)
        assert len(events) == 1
        assert events[0].event_type == "agent_failure"

    @pytest.mark.asyncio
    async def test_record_timeout_run(self):
        af = AgentFlowReliability()
        run = AgentRun(
            run_id="r3",
            agent_name="diagnoser",
            status=AgentStatus.TIMEOUT,
            duration_ms=30000,
        )
        events = await af.record_run(run)
        assert len(events) == 1
        assert events[0].event_type == "agent_timeout"

    @pytest.mark.asyncio
    async def test_record_tool_failure(self):
        af = AgentFlowReliability()
        run = AgentRun(
            run_id="r4",
            agent_name="investigator",
            status=AgentStatus.COMPLETED,
            tool_calls=[
                ToolCall(tool_name="query_db", status=ToolStatus.FAILED, error_message="Connection refused"),
            ],
        )
        events = await af.record_run(run)
        assert len(events) == 1
        assert events[0].event_type == "tool_failure"

    @pytest.mark.asyncio
    async def test_record_slow_tool(self):
        af = AgentFlowReliability()
        run = AgentRun(
            run_id="r5",
            agent_name="investigator",
            status=AgentStatus.COMPLETED,
            tool_calls=[
                ToolCall(tool_name="heavy_query", status=ToolStatus.SUCCESS, duration_ms=45000),
            ],
        )
        events = await af.record_run(run)
        assert len(events) == 1
        assert events[0].event_type == "execution_anomaly"

    def test_get_agent_health_no_runs(self):
        af = AgentFlowReliability()
        health = af.get_agent_health("unknown")
        assert health["status"] == "unknown"

    @pytest.mark.asyncio
    async def test_get_agent_health_healthy(self):
        af = AgentFlowReliability()
        for i in range(5):
            await af.record_run(AgentRun(
                run_id=f"r{i}", agent_name="investigator", status=AgentStatus.COMPLETED,
            ))
        health = af.get_agent_health("investigator")
        assert health["status"] == "healthy"
        assert health["success_rate"] == 100.0

    @pytest.mark.asyncio
    async def test_get_agent_health_degraded(self):
        af = AgentFlowReliability()
        for i in range(3):
            await af.record_run(AgentRun(
                run_id=f"r{i}", agent_name="investigator", status=AgentStatus.COMPLETED,
            ))
        await af.record_run(AgentRun(
            run_id="r3", agent_name="investigator", status=AgentStatus.FAILED, error_message="err",
        ))
        health = af.get_agent_health("investigator")
        assert health["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_get_tool_reliability(self):
        af = AgentFlowReliability()
        await af.record_run(AgentRun(
            run_id="r1", agent_name="a", status=AgentStatus.COMPLETED,
            tool_calls=[ToolCall(tool_name="good_tool", status=ToolStatus.SUCCESS, duration_ms=10)],
        ))
        await af.record_run(AgentRun(
            run_id="r2", agent_name="a", status=AgentStatus.COMPLETED,
            tool_calls=[ToolCall(tool_name="bad_tool", status=ToolStatus.FAILED, error_message="err")],
        ))
        stats = af.get_tool_reliability()
        assert len(stats) == 2
        bad = next(s for s in stats if s["tool"] == "bad_tool")
        assert bad["success_rate"] == 0.0

    def test_get_recent_events(self):
        af = AgentFlowReliability()
        assert af.get_recent_events() == []


# ─── API Import Tests ─────────────────────────────────────────────────


class TestPhase11APIImports:
    def test_e6data_router_imports(self):
        from apps.api.app.api.e6data import router
        assert router.prefix == "/api/e6data"

    def test_main_app_includes_e6data(self):
        from apps.api.app.api.e6data import router
        assert any("telemetry" in r.path for r in router.routes if hasattr(r, "path"))

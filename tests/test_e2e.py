"""End-to-end tests for the DataForge agent lifecycle."""

import pytest
from unittest.mock import AsyncMock, patch

from sandbox.executor import execute_analysis
from agent.tools.risk import classify_remediation_risk, get_risk_level
from agent.graph.nodes.execute import execute_remediation, TOOL_REGISTRY
from agent.graph.nodes.approval import approval_gate, process_approval


def _make_state(**overrides) -> dict:
    defaults = {
        "incident_id": "e2e-1",
        "status": "created",
        "events": [],
        "evidence": [],
        "remediation_plan": {"actions": []},
        "risk_level": "LOW",
        "approval_required": False,
        "approval_status": "",
        "execution_result": {},
        "verification_result": {},
        "incident_type": "stale_data",
        "pipeline_findings": [],
        "github_findings": [],
        "database_findings": [],
    }
    defaults.update(overrides)
    return defaults


# ── Scenario A: Safe investigation (read-only, no approval needed) ─────────────

@pytest.mark.asyncio
async def test_investigation_collects_evidence():
    pipeline_result = {"status": "healthy", "pipelines": []}
    commits_result = [{"sha": "abc123", "message": "fix: patch"}]

    with patch("mcp.monitoring.tools.pipelines.get_pipeline_status", new_callable=AsyncMock, return_value=pipeline_result), \
         patch("mcp.github.tools.commits.get_recent_commits", new_callable=AsyncMock, return_value=commits_result):
        from agent.agents.pipeline_agent import investigate_pipeline
        from agent.agents.github_agent import investigate_github

        p_result = await investigate_pipeline("stale_data", "pipeline looks stale")
        g_result = await investigate_github("stale_data", "pipeline looks stale")

        assert "findings" in p_result
        assert "findings" in g_result


@pytest.mark.asyncio
async def test_approval_gate_auto_approves_low_risk():
    state = _make_state(approval_required=False, risk_level="LOW")
    result = await approval_gate(state)
    assert result["approval_status"] == "auto_approved"
    assert result["status"] == "approved"


@pytest.mark.asyncio
async def test_execute_node_blocks_without_approval():
    state = _make_state(approval_status="", remediation_plan={"actions": [{"tool": "rerun_pipeline", "parameters": {}}]})
    result = await execute_remediation(state)
    assert result["status"] == "blocked"
    assert "blocked" in result["execution_result"]["error"]


@pytest.mark.asyncio
async def test_execute_node_blocks_rejected():
    state = _make_state(approval_status="rejected", remediation_plan={"actions": [{"tool": "rerun_pipeline", "parameters": {}}]})
    result = await execute_remediation(state)
    assert result["status"] == "blocked"
    assert "rejected" in result["execution_result"]["error"]


# ── Scenario B: Destructive remediation denied ─────────────────────────────────

def test_high_risk_requires_approval():
    actions = [{"tool": "rollback_deployment", "parameters": {}}]
    assert classify_remediation_risk(actions) == "HIGH"


@pytest.mark.asyncio
async def test_approval_gate_pauses_on_high_risk():
    state = _make_state(approval_required=True, risk_level="HIGH")
    result = await approval_gate(state)
    assert result["status"] == "awaiting_approval"
    assert result["approval_status"] == "pending"


@pytest.mark.asyncio
async def test_rejection_stops_execution():
    state = _make_state(approval_status="rejected")
    result = await process_approval(state)
    assert result["status"] == "rejected"
    event_types = [e["type"] for e in result["events"]]
    assert "approval.rejected" in event_types


# ── Scenario C: Approved remediation ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_approval_sets_status():
    state = _make_state(approval_status="approved")
    result = await process_approval(state)
    assert result["status"] == "approved"
    event_types = [e["type"] for e in result["events"]]
    assert "approval.approved" in event_types


@pytest.mark.asyncio
async def test_execute_runs_after_approval():
    mock_rerun = AsyncMock(return_value={"status": "success", "tool": "rerun_pipeline"})
    with patch.dict(TOOL_REGISTRY, {"rerun_pipeline": mock_rerun}):
        state = _make_state(
            approval_status="approved",
            remediation_plan={"actions": [{"tool": "rerun_pipeline", "parameters": {"pipeline_id": "PL-1"}}]},
        )
        result = await execute_remediation(state)
        assert result["status"] == "executing"
        assert result["execution_result"]["all_success"] is True
        assert result["execution_result"]["success_count"] == 1
        mock_rerun.assert_called_once()


@pytest.mark.asyncio
async def test_full_approved_workflow():
    mock_rerun = AsyncMock(return_value={"status": "success", "tool": "rerun_pipeline"})
    with patch.dict(TOOL_REGISTRY, {"rerun_pipeline": mock_rerun}):
        state = _make_state(
            approval_status="auto_approved",
            remediation_plan={"actions": [{"tool": "rerun_pipeline", "parameters": {"pipeline_id": "PL-1"}}]},
        )
        exec_result = await execute_remediation(state)
        assert exec_result["status"] == "executing"
        assert exec_result["execution_result"]["success_count"] == 1

        pipeline_status = {"pipelines": [{"status": "HEALTHY"}]}
        with patch("agent.graph.nodes.verify.get_pipeline_status", new_callable=AsyncMock, return_value=pipeline_status), \
             patch("agent.graph.nodes.verify.check_data_quality", new_callable=AsyncMock, return_value={"findings": [], "errors": []}):
            from agent.graph.nodes.verify import verify_remediation
            verify_result = await verify_remediation(state)
            pipeline_checks = [r for r in verify_result["verification_result"]["results"] if r["metric"] == "pipeline_health"]
            assert len(pipeline_checks) == 1
            assert pipeline_checks[0]["status"] == "resolved"


# ── Scenario D: Sandbox failure containment ────────────────────────────────────

@pytest.mark.asyncio
async def test_sandbox_timeout():
    result = await execute_analysis("while True: pass")
    assert result["error"] is not None
    assert "timed out" in result["error"].lower() or result["error"] != ""


@pytest.mark.asyncio
async def test_sandbox_import_restriction():
    result = await execute_analysis("import os\nresult = os.listdir('/')")
    assert result["error"] is not None
    assert "not allowed" in result["error"].lower() or "blocked" in result["error"].lower() or "Import not allowed" in result["error"]


@pytest.mark.asyncio
async def test_sandbox_file_access_blocked():
    result = await execute_analysis("open('/etc/passwd')")
    assert result["error"] is not None


@pytest.mark.asyncio
async def test_sandbox_valid_code_works():
    code = 'result = {"status": "ok", "findings": [1, 2, 3]}'
    result = await execute_analysis(code)
    assert result["error"] is None
    assert result["result"]["status"] == "ok"
    assert result["result"]["findings"] == [1, 2, 3]


@pytest.mark.asyncio
async def test_sandbox_empty_code_handled():
    result = await execute_analysis("")
    assert result["error"] == "No code provided"
    assert result["result"] is None


# ── Scenario E: Verification failure ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_verification_detects_unresolved():
    dq_result = {
        "findings": [
            {"type": "freshness", "data": {}, "summary": "stale 3d", "passed": False},
            {"type": "uniqueness", "data": {}, "summary": "5% dupes", "passed": False},
        ],
        "errors": [],
    }
    pipeline_status = {"pipelines": [{"status": "FAILED"}]}

    with patch("agent.graph.nodes.verify.check_data_quality", new_callable=AsyncMock, return_value=dq_result), \
         patch("agent.graph.nodes.verify.get_pipeline_status", new_callable=AsyncMock, return_value=pipeline_status):
        from agent.graph.nodes.verify import verify_remediation
        result = await verify_remediation(_make_state())
        vr = result["verification_result"]
        assert vr["overall_status"] == "partially_resolved"
        assert vr["resolved_count"] < vr["total_count"]
        statuses = [r["status"] for r in vr["results"]]
        assert "unresolved" in statuses


@pytest.mark.asyncio
async def test_verification_partial_resolution():
    dq_result = {
        "findings": [
            {"type": "freshness", "data": {}, "summary": "ok now", "passed": True},
            {"type": "uniqueness", "data": {}, "summary": "still dupes", "passed": False},
        ],
        "errors": [],
    }
    pipeline_status = {"pipelines": [{"status": "HEALTHY"}]}

    with patch("agent.graph.nodes.verify.check_data_quality", new_callable=AsyncMock, return_value=dq_result), \
         patch("agent.graph.nodes.verify.get_pipeline_status", new_callable=AsyncMock, return_value=pipeline_status):
        from agent.graph.nodes.verify import verify_remediation
        result = await verify_remediation(_make_state())
        vr = result["verification_result"]
        assert vr["overall_status"] == "partially_resolved"
        assert 1 <= vr["resolved_count"] < vr["total_count"]


# ── Risk classification ────────────────────────────────────────────────────────

def test_read_only_low_risk():
    assert get_risk_level("get_pipeline_status") == "LOW"
    assert get_risk_level("list_tables") == "LOW"


def test_destructive_high_risk():
    assert get_risk_level("rollback_deployment") == "HIGH"
    assert get_risk_level("reprocess_partition") == "HIGH"


def test_unknown_tools_high_risk():
    assert get_risk_level("totally_unknown_tool") == "HIGH"

"""End-to-end Golden Path test — full 12-step flow against the real API.

Covers: detect-drift → investigate → create-repair-plan → approve →
        execute → verify → status.

Requires a running PostgreSQL database (marked integration).
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.app.main import app

API_KEY = "df_D7HhB2A1pynRLOo-6sRcRp565-8scSk2Rq67uDgKexI"
RUN_ID = uuid.uuid4().hex[:8]

BASE_SCHEMA = [
    {"name": "id", "type": "integer", "nullable": False},
    {"name": "customer_id", "type": "integer", "nullable": True},
    {"name": "amount", "type": "numeric", "nullable": True},
]

DRIFTED_SCHEMA = [
    {"name": "id", "type": "integer", "nullable": False},
    {"name": "customer_id", "type": "integer", "nullable": True},
    {"name": "amount", "type": "numeric", "nullable": True},
    {"name": "region", "type": "varchar", "nullable": True},
]

REPAIRED_SCHEMA = [
    {"name": "id", "type": "integer", "nullable": False},
    {"name": "customer_id", "type": "integer", "nullable": True},
    {"name": "amount", "type": "numeric", "nullable": True},
    {"name": "region", "type": "varchar", "nullable": True},
    {"name": "created_at", "type": "timestamp", "nullable": True},
]


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-API-Key": API_KEY},
    ) as ac:
        yield ac


@pytest.mark.integration
class TestGoldenPathEndToEnd:
    """Full 12-step golden path flow."""

    @pytest.mark.asyncio
    async def test_full_golden_path_flow(self, client):
        # ── Establish baseline (first call stores snapshot) ────────────
        table = f"e2e_orders_{RUN_ID}"
        resp = await client.post("/api/golden-path/detect-drift", json={
            "connector_id": "e2e-test",
            "table_name": table,
            "current_schema": BASE_SCHEMA,
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "no_drift"

        # ── Step 1-4: Detect drift, create incident ────────────────────
        resp = await client.post("/api/golden-path/detect-drift", json={
            "connector_id": "e2e-test",
            "table_name": table,
            "current_schema": DRIFTED_SCHEMA,
            "connector_name": "E2E Test DB",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "drift_detected"
        incident_id = data["incident_id"]
        assert incident_id
        assert "drift" in data
        drift = data["drift"]
        assert drift["added_columns"] or drift["removed_columns"] or drift["type_changes"]

        # ── Step 5-6: Investigate with GitHub correlation ──────────────
        resp = await client.post("/api/golden-path/investigate", json={
            "incident_id": incident_id,
        })
        assert resp.status_code == 200
        inv = resp.json()
        assert inv["status"] == "investigation_complete"
        assert inv["incident_id"] == incident_id
        assert isinstance(inv["suspect_commits"], list)

        # ── Step 7-8: Create repair plan ───────────────────────────────
        resp = await client.post("/api/golden-path/create-repair-plan", json={
            "incident_id": incident_id,
            "actions": [
                {"action": "ALTER TABLE", "sql": "ALTER TABLE e2e_orders ADD COLUMN created_at TIMESTAMP"},
                {"action": "UPDATE", "sql": "UPDATE e2e_orders SET created_at = NOW()"},
            ],
            "rollback_plan": [
                {"action": "ALTER TABLE", "sql": "ALTER TABLE e2e_orders DROP COLUMN created_at"},
            ],
            "risk_level": "high",
        })
        assert resp.status_code == 200
        plan = resp.json()
        plan_id = plan["plan_id"]
        assert plan_id
        assert plan["requires_approval"] is True
        assert plan["risk_level"] == "high"
        assert len(plan["actions"]) == 2

        # ── Step 9-10: Approve the plan ────────────────────────────────
        resp = await client.post("/api/golden-path/approve", json={
            "plan_id": plan_id,
            "approved": True,
            "reason": "E2E test approval",
        })
        assert resp.status_code == 200
        approval = resp.json()
        assert approval["status"] == "approved"
        assert approval["approved"] is True

        # ── Step 11: Execute the plan ──────────────────────────────────
        resp = await client.post("/api/golden-path/execute", json={
            "plan_id": plan_id,
            "current_schema": REPAIRED_SCHEMA,
        })
        assert resp.status_code == 200
        execution = resp.json()
        assert execution["status"] == "executed"
        assert execution["incident_id"] == incident_id

        # ── Step 12: Verify the remediation ────────────────────────────
        resp = await client.post("/api/golden-path/verify", json={
            "incident_id": incident_id,
            "current_schema": REPAIRED_SCHEMA,
        })
        assert resp.status_code == 200
        verification = resp.json()
        assert verification["incident_id"] == incident_id
        assert "verification" in verification

        # ── Step 13: Check final status ────────────────────────────────
        resp = await client.get(f"/api/golden-path/status/{incident_id}")
        assert resp.status_code == 200
        status = resp.json()
        assert status["incident_id"] == incident_id
        assert len(status["events"]) >= 5
        event_types = [e["type"] for e in status["events"]]
        assert "drift_detected" in event_types
        assert "investigation" in event_types
        assert "repair_plan_created" in event_types
        assert "plan_approved" in event_types
        assert "plan_executed" in event_types
        assert "verification" in event_types
        assert len(status["plans"]) >= 1
        assert status["plans"][0]["status"] == "executed"

    @pytest.mark.asyncio
    async def test_reject_flow(self, client):
        """Detect drift → create plan → reject → cannot execute."""
        table = f"e2e_reject_{RUN_ID}"
        # Establish baseline
        await client.post("/api/golden-path/detect-drift", json={
            "connector_id": "e2e-test",
            "table_name": table,
            "current_schema": BASE_SCHEMA,
        })
        # Detect drift
        resp = await client.post("/api/golden-path/detect-drift", json={
            "connector_id": "e2e-test",
            "table_name": table,
            "current_schema": DRIFTED_SCHEMA,
        })
        assert resp.status_code == 200
        incident_id = resp.json()["incident_id"]

        resp = await client.post("/api/golden-path/create-repair-plan", json={
            "incident_id": incident_id,
            "actions": [{"action": "ALTER TABLE", "sql": "ALTER TABLE e2e_reject ADD COLUMN x INT"}],
            "risk_level": "critical",
        })
        plan_id = resp.json()["plan_id"]

        # Reject
        resp = await client.post("/api/golden-path/approve", json={
            "plan_id": plan_id,
            "approved": False,
            "reason": "Too risky",
        })
        assert resp.json()["status"] == "rejected"

        # Cannot execute rejected plan
        resp = await client.post("/api/golden-path/execute", json={
            "plan_id": plan_id,
            "current_schema": DRIFTED_SCHEMA,
        })
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_no_drift_detected(self, client):
        """Second detection with same schema → no drift."""
        table = f"e2e_nodrift_{RUN_ID}"
        # First detection stores a snapshot
        await client.post("/api/golden-path/detect-drift", json={
            "connector_id": "e2e-test",
            "table_name": table,
            "current_schema": BASE_SCHEMA,
        })
        # Second detection with same schema → no drift
        resp = await client.post("/api/golden-path/detect-drift", json={
            "connector_id": "e2e-test",
            "table_name": table,
            "current_schema": BASE_SCHEMA,
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "no_drift"

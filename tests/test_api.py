"""Tests for API endpoints.

These tests require a running PostgreSQL database.
Skip with: uv run pytest tests/test_api.py -k "not api"
"""

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.integration
class TestHealthEndpoint:
    """Test health check endpoint."""

    @pytest.mark.asyncio
    async def test_health(self, client):
        response = await client.get("/api/health")
        assert response.status_code == 200


@pytest.mark.integration
class TestIncidentsEndpoint:
    """Test incidents CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_list_incidents(self, client):
        response = await client.get("/api/incidents/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_create_incident(self, client):
        payload = {
            "title": "Test incident",
            "severity": "medium",
            "incident_type": "test",
        }
        response = await client.post("/api/incidents/", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Test incident"
        assert data["status"] == "created"

    @pytest.mark.asyncio
    async def test_get_incident(self, client):
        payload = {"title": "Get test", "severity": "low"}
        create_resp = await client.post("/api/incidents/", json=payload)
        incident_id = create_resp.json()["id"]

        response = await client.get(f"/api/incidents/{incident_id}")
        assert response.status_code == 200
        assert response.json()["title"] == "Get test"

    @pytest.mark.asyncio
    async def test_get_incident_not_found(self, client):
        response = await client.get("/api/incidents/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_stats_endpoint(self, client):
        response = await client.get("/api/incidents/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "open" in data
        assert "resolved" in data
        assert "critical" in data


@pytest.mark.integration
class TestChaosEndpoint:
    """Test chaos fault injection endpoints."""

    @pytest.mark.asyncio
    async def test_list_faults(self, client):
        response = await client.get("/api/chaos/faults")
        assert response.status_code == 200
        data = response.json()
        assert "faults" in data
        assert len(data["faults"]) == 7

    @pytest.mark.asyncio
    async def test_inject_schema_drift(self, client):
        response = await client.post("/api/chaos/schema_drift")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "injected"
        assert data["fault_type"] == "schema_drift"
        assert data["incident_id"] is not None

    @pytest.mark.asyncio
    async def test_inject_unknown_fault(self, client):
        response = await client.post("/api/chaos/unknown_fault")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"

"""TrueForge — Python client for the TrueForge agent harness HTTP API.

Provides:
- Agent management (create, list, get)
- Session management (create, get, list)
- Turn management (create, stream events)
- Approval handling
- Event streaming

Usage:
    from trueforge.client import TrueForgeClient

    client = TrueForgeClient(base_url="http://localhost:8790")
    session = await client.create_session(agent_name="dataforge-investigator")
    turn = await client.create_turn(session_id=session["id"], message="Investigate...")
    async for event in client.stream_turn(session_id=session["id"], turn_id=turn["id"]):
        print(event)
"""

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://localhost:8790"
DEFAULT_TIMEOUT = 600.0


class TrueForgeError(Exception):
    """Error from TrueForge API."""
    pass


class TrueForgeClient:
    """Async client for TrueForge agent harness HTTP API."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        token: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    # ─── Agents ──────────────────────────────────────────────────────────────

    async def list_agents(self) -> list[dict]:
        """List all configured agents."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/agents",
                headers=self._headers(),
            )
            if resp.status_code != 200:
                raise TrueForgeError(f"List agents failed: {resp.status_code} {resp.text}")
            return resp.json().get("data", [])

    async def create_agent(self, spec: dict) -> dict:
        """Create a new agent from spec."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}/api/v1/agents",
                headers=self._headers(),
                json=spec,
            )
            if resp.status_code not in (200, 201):
                raise TrueForgeError(f"Create agent failed: {resp.status_code} {resp.text}")
            return resp.json()

    async def get_agent(self, agent_id: str) -> dict:
        """Get agent by ID."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/agents/{agent_id}",
                headers=self._headers(),
            )
            if resp.status_code != 200:
                raise TrueForgeError(f"Get agent failed: {resp.status_code} {resp.text}")
            return resp.json()

    # ─── Sessions ────────────────────────────────────────────────────────────

    async def create_session(
        self,
        agent_name: str | None = None,
        agent_spec: dict | None = None,
    ) -> dict:
        """Create a new session with an agent.

        Use either agent_name (saved agent) or agent_spec (inline).
        """
        payload: dict[str, Any] = {}
        if agent_name:
            payload["agent"] = {"name": agent_name}
        elif agent_spec:
            payload["agent"] = {"spec": agent_spec}
        else:
            raise TrueForgeError("Either agent_name or agent_spec required")

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}/api/v1/sessions",
                headers=self._headers(),
                json=payload,
            )
            if resp.status_code not in (200, 201):
                raise TrueForgeError(f"Create session failed: {resp.status_code} {resp.text}")
            data = resp.json()
            return data.get("data", data)

    async def get_session(self, session_id: str) -> dict:
        """Get session by ID."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/sessions/{session_id}",
                headers=self._headers(),
            )
            if resp.status_code != 200:
                raise TrueForgeError(f"Get session failed: {resp.status_code} {resp.text}")
            return resp.json()

    async def list_sessions(self, limit: int = 50) -> list[dict]:
        """List recent sessions."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/sessions",
                headers=self._headers(),
                params={"limit": limit},
            )
            if resp.status_code != 200:
                raise TrueForgeError(f"List sessions failed: {resp.status_code} {resp.text}")
            return resp.json().get("data", [])

    # ─── Turns ───────────────────────────────────────────────────────────────

    async def create_turn(
        self,
        session_id: str,
        message: str,
    ) -> dict:
        """Create a new turn in a session (non-blocking).

        Sends the turn creation request and returns immediately with the turn_id
        without waiting for the LLM to complete processing.
        """
        payload = {
            "input": [{"type": "user.message", "content": message}],
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/v1/sessions/{session_id}/turns",
                headers=self._headers(),
                json=payload,
            ) as resp:
                if resp.status_code not in (200, 201):
                    text = ""
                    async for chunk in resp.aiter_text():
                        text += chunk
                    raise TrueForgeError(f"Create turn failed: {resp.status_code} {text}")

                # Read SSE events to find turn.created
                turn_id = None
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            if data.get("type") == "turn.created":
                                turn_id = data.get("turn_id") or data.get("id")
                                return {"id": turn_id, "status": "started"}
                        except json.JSONDecodeError:
                            continue

                return {"id": turn_id, "status": "started"}

    async def create_turn_stream(
        self,
        session_id: str,
        message: str,
    ) -> AsyncIterator[dict]:
        """Create a turn and stream events via SSE."""
        payload = {
            "input": [{"type": "user.message", "content": message}],
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/v1/sessions/{session_id}/turns",
                headers=self._headers(),
                json=payload,
            ) as resp:
                if resp.status_code != 200:
                    text = await resp.aread()
                    raise TrueForgeError(f"Stream turn failed: {resp.status_code} {text.decode()}")

                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data.strip():
                            try:
                                event = json.loads(data)
                                yield event
                            except json.JSONDecodeError:
                                logger.warning(f"Failed to parse SSE event: {data}")

    async def list_turns(self, session_id: str) -> list[dict]:
        """List all turns for a session."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/sessions/{session_id}/turns",
                headers=self._headers(),
            )
            if resp.status_code != 200:
                raise TrueForgeError(f"List turns failed: {resp.status_code} {resp.text}")
            return resp.json().get("data", [])

    async def get_turn(self, session_id: str, turn_id: str) -> dict:
        """Get turn by ID."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/sessions/{session_id}/turns/{turn_id}",
                headers=self._headers(),
            )
            if resp.status_code != 200:
                raise TrueForgeError(f"Get turn failed: {resp.status_code} {resp.text}")
            return resp.json()

    async def get_turn_events(self, session_id: str, turn_id: str) -> list[dict]:
        """Get all events for a turn."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/sessions/{session_id}/turns/{turn_id}/events",
                headers=self._headers(),
            )
            if resp.status_code != 200:
                raise TrueForgeError(f"Get turn events failed: {resp.status_code} {resp.text}")
            return resp.json().get("data", [])

    # ─── Approvals ───────────────────────────────────────────────────────────

    async def approve_tool(
        self,
        session_id: str,
        turn_id: str,
        tool_name: str,
        approved: bool = True,
    ) -> dict:
        """Approve or reject a tool call."""
        payload = {
            "tool_name": tool_name,
            "approved": approved,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}/api/v1/sessions/{session_id}/turns/{turn_id}/approval",
                headers=self._headers(),
                json=payload,
            )
            if resp.status_code not in (200, 201):
                raise TrueForgeError(f"Approve tool failed: {resp.status_code} {resp.text}")
            return resp.json()

    # ─── Health ──────────────────────────────────────────────────────────────

    async def health(self) -> dict:
        """Check TrueForge server health."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/capabilities",
                headers=self._headers(),
            )
            if resp.status_code != 200:
                raise TrueForgeError(f"Health check failed: {resp.status_code} {resp.text}")
            return resp.json()

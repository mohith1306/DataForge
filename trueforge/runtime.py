"""TrueForge integration for DataForge API.

Provides:
- TrueForge runtime connection
- Session management for incidents
- Event streaming to SSE
- Approval handling
"""

import logging

from trueforge.agents import DATAFORGE_INVESTIGATOR_SPEC
from trueforge.client import TrueForgeClient, TrueForgeError

logger = logging.getLogger(__name__)


class TrueForgeRuntime:
    """Manages TrueForge integration for DataForge incidents."""

    def __init__(self, base_url: str = "http://localhost:8790", token: str | None = None):
        self.client = TrueForgeClient(base_url=base_url, token=token)
        self._agent_id: str | None = None

    async def ensure_agent(self) -> str:
        """Ensure the DataForge investigator agent exists, return its ID."""
        if self._agent_id:
            return self._agent_id

        try:
            agents = await self.client.list_agents()
            for agent in agents:
                if agent.get("name") == "dataforge-investigator":
                    self._agent_id = agent["id"]
                    logger.info(f"Found existing agent: {self._agent_id}")
                    return self._agent_id
        except TrueForgeError as e:
            logger.warning(f"Could not list agents: {e}")

        # Create agent
        try:
            result = await self.client.create_agent(DATAFORGE_INVESTIGATOR_SPEC)
            self._agent_id = result.get("id")
            logger.info(f"Created agent: {self._agent_id}")
            return self._agent_id
        except TrueForgeError as e:
            logger.error(f"Failed to create agent: {e}")
            raise

    async def start_investigation(
        self,
        incident_id: str,
        incident_type: str,
        description: str,
    ) -> dict:
        """Start a TrueForge investigation session for an incident."""
        await self.ensure_agent()

        message = (
            f"Investigate this data quality incident.\n\n"
            f"Incident ID: {incident_id}\n"
            f"Type: {incident_type}\n"
            f"Description: {description}\n\n"
            f"Use the database, monitoring, and GitHub tools to collect evidence. "
            f"Then run sandbox analysis to verify your findings. "
            f"Finally, identify the root cause and generate a remediation plan."
        )

        try:
            session = await self.client.create_session(
                agent_name="dataforge-investigator",
                title=f"Investigation: {incident_id}",
            )
            session_id = session["id"]

            turn = await self.client.create_turn(
                session_id=session_id,
                message=message,
            )

            return {
                "session_id": session_id,
                "turn_id": turn.get("id"),
                "status": "started",
            }
        except TrueForgeError as e:
            logger.error(f"Failed to start investigation: {e}")
            return {
                "session_id": None,
                "turn_id": None,
                "status": "error",
                "error": str(e),
            }

    async def stream_investigation(
        self,
        session_id: str,
    ):
        """Stream investigation events from TrueForge."""
        try:
            async for event in self.client.create_turn_stream(
                session_id=session_id,
                message="Continue the investigation.",
            ):
                yield event
        except TrueForgeError as e:
            logger.error(f"Stream error: {e}")
            yield {"type": "error", "message": str(e)}

    async def get_investigation_result(self, session_id: str) -> dict:
        """Get the final result of an investigation."""
        try:
            session = await self.client.get_session(session_id)
            return session
        except TrueForgeError as e:
            logger.error(f"Failed to get result: {e}")
            return {"error": str(e)}

    async def approve_action(
        self,
        session_id: str,
        turn_id: str,
        tool_name: str,
        approved: bool = True,
    ) -> dict:
        """Approve or reject a remediation action."""
        try:
            return await self.client.approve_tool(
                session_id=session_id,
                turn_id=turn_id,
                tool_name=tool_name,
                approved=approved,
            )
        except TrueForgeError as e:
            logger.error(f"Failed to approve action: {e}")
            return {"error": str(e)}

    async def health_check(self) -> dict:
        """Check if TrueForge is running."""
        try:
            return await self.client.health()
        except TrueForgeError as e:
            return {"status": "unavailable", "error": str(e)}

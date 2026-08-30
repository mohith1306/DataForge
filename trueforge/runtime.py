"""TrueForge integration for DataForge API.

Provides:
- TrueForge runtime connection
- Session management for incidents
- Event streaming to SSE
- Approval handling
"""

import asyncio
import json
import logging

from trueforge.agents import get_investigator_spec
from trueforge.client import TrueForgeClient, TrueForgeError

logger = logging.getLogger(__name__)


class TrueForgeRuntime:
    """Manages TrueForge integration for DataForge incidents."""

    def __init__(
        self,
        base_url: str = "http://localhost:8790",
        token: str | None = None,
        model_name: str = "google/gemini-2.0-flash",
    ):
        self.client = TrueForgeClient(base_url=base_url, token=token)
        self._agent_id: str | None = None
        self._model_name = model_name

    async def ensure_agent(self) -> str:
        """Ensure the DataForge investigator agent exists, return its ID.

        If an existing agent is found, updates its manifest to match the
        current spec (model, instructions, MCP servers, iteration limit).
        """
        desired_spec = get_investigator_spec(self._model_name)

        try:
            agents = await self.client.list_agents()
            for agent in agents:
                if agent.get("name") == "dataforge-investigator":
                    self._agent_id = agent["id"]
                    logger.info(f"Found existing agent: {self._agent_id}")
                    # Update manifest to ensure it matches current spec
                    try:
                        await self.client.update_agent(
                            self._agent_id,
                            {"manifest": desired_spec},
                        )
                        logger.info("Updated existing agent manifest")
                    except TrueForgeError as e:
                        logger.warning(f"Could not update agent manifest: {e}")
                    return self._agent_id
        except TrueForgeError as e:
            logger.warning(f"Could not list agents: {e}")

        # Create agent — TrueForge expects {name, manifest: {model, instructions, ...}}
        try:
            payload = {
                "name": "dataforge-investigator",
                "manifest": desired_spec,
            }
            result = await self.client.create_agent(payload)
            self._agent_id = result.get("id")
            logger.info(f"Created agent: {self._agent_id}")
            return self._agent_id
        except TrueForgeError as e:
            logger.error(f"Failed to create agent: {e}")
            raise

    async def _prefetch_data(self, description: str) -> str:
        """Pre-fetch pipeline data from the configured database for the investigation.

        Uses the same adapter as the monitor, so it works with ClickHouse,
        PostgreSQL, or custom backends.
        """
        from apps.api.app.services.db_adapter import create_monitor_adapter

        adapter = create_monitor_adapter()
        sections = []

        # 1. Pipeline status (recent failures)
        try:
            failures = await adapter.check_pipeline_failures(lookback_seconds=3600)
            sections.append("### Pipeline Status (recent runs)")
            if failures:
                for r in failures:
                    sections.append(
                        f"- {r.get('pipeline_name','?')} ({r.get('pipeline_id','?')}): "
                        f"{r.get('status','?')} | started: {r.get('started_at','?')} | "
                        f"error: {str(r.get('error_message',''))[:200]}"
                    )
            else:
                sections.append("- No recent failures found")
        except Exception as e:
            sections.append(f"### Pipeline Status\nError fetching: {e}")

        # 2. Pipeline freshness
        try:
            stale = await adapter.check_pipeline_freshness(stale_minutes=120)
            sections.append("\n### Data Freshness (stale pipelines)")
            if stale:
                for r in stale:
                    sections.append(
                        f"- {r.get('pipeline_name','?')} ({r.get('pipeline_id','?')}): "
                        f"last run: {r.get('last_run','?')}"
                    )
            else:
                sections.append("- No stale pipelines")
        except Exception as e:
            sections.append(f"\n### Data Freshness\nError fetching: {e}")

        # 3. Data quality checks
        try:
            dq = await adapter.check_data_quality()
            if dq:
                sections.append("\n### Failed Data Quality Checks")
                for r in dq:
                    sections.append(
                        f"- {r.get('table','?')}.{r.get('column','?')}: "
                        f"null_rate={r.get('null_rate',0):.1%} (threshold: {r.get('threshold',0):.0%})"
                    )
            else:
                sections.append("\n### Data Quality\nAll checks passing.")
        except Exception as e:
            sections.append(f"\n### Data Quality\nError fetching: {e}")

        # 4. Recent commits
        try:
            import subprocess
            result = subprocess.run(
                ["git", "log", "--oneline", "-5", "--format=%h %s (%ai)"],
                capture_output=True, text=True, timeout=5,
                cwd=os.getenv("GITHUB_REPO_PATH", "."),
            )
            commits = result.stdout.strip()
            sections.append(f"\n### Recent Git Commits\n{commits}" if commits else "\n### Recent Git Commits\nNo commits found.")
        except Exception as e:
            sections.append(f"\n### Recent Git Commits\nError: {e}")

        return "\n".join(sections)

    async def start_investigation(
        self,
        incident_id: str,
        incident_type: str,
        description: str,
    ) -> dict:
        """Start a TrueForge investigation session for an incident.

        Pre-fetches data from ClickHouse so the LLM just needs to analyze,
        not call tools (avoids Gemini tool-calling loop issues).
        """
        await self.ensure_agent()

        # Pre-fetch data from ClickHouse
        prefetched = await self._prefetch_data(description)

        message = (
            f"## Data Quality Incident\n\n"
            f"Incident ID: {incident_id}\n"
            f"Type: {incident_type}\n"
            f"Description: {description}\n\n"
            f"## Pre-fetched Data\n\n"
            f"{prefetched}\n\n"
            f"## Task\n\n"
            f"Analyze the above data and write your investigation report.\n"
            f"Do NOT call any tools — all data is provided above.\n\n"
            f"## Response Format\n\n"
            f"ROOT CAUSE: [describe the root cause]\n"
            f"CONFIDENCE: [high/medium/low]\n"
            f"EVIDENCE: [list the evidence]\n"
            f"REMEDIATION PLAN: [describe how to fix]"
        )

        try:
            session = await self.client.create_session(
                agent_name="dataforge-investigator",
            )
            session_id = session["id"]

            turn = await self.client.create_turn(
                session_id=session_id,
                message=message,
            )

            turn_id = turn.get("id")
            if not turn_id:
                turns = await self.client.list_turns(session_id)
                if turns:
                    turn_id = turns[-1].get("id")

            return {
                "session_id": session_id,
                "turn_id": turn_id,
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

    async def stream_turn_events(
        self,
        session_id: str,
        turn_id: str | None,
    ):
        """Stream events for an existing turn (Bug 3 fix).

        If turn_id is provided, reads events for that specific turn.
        Otherwise falls back to creating a new streaming turn.
        """
        if not turn_id:
            # Fallback: create a new streaming turn
            async for event in self.client.create_turn_stream(
                session_id=session_id,
                message="Continue the investigation.",
            ):
                yield event
            return

        try:
            events = await self.client.get_turn_events(session_id, turn_id)
            for event in events:
                yield event
        except TrueForgeError as e:
            logger.error(f"Failed to get turn events: {e}")
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

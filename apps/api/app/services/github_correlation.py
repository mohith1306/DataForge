"""GitHub Correlation — links incidents to the commit that caused them.

Searches recent commits for schema changes (migrations, ALTER TABLE, etc.)
and correlates them with detected schema drift.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


class GitHubCorrelator:
    """Searches GitHub for commits that may have caused an incident."""

    def __init__(self, repo: str | None = None, token: str | None = None):
        self.repo = repo or os.getenv("GITHUB_REPO", "mohith1306/DataForge")
        self.token = token or os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")

    def _headers(self) -> dict:
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def get_recent_commits(
        self, branch: str = "main", limit: int = 30
    ) -> list[dict]:
        """Fetch recent commits from the repo."""
        url = f"{GITHUB_API}/repos/{self.repo}/commits"
        params = {"sha": branch, "per_page": min(limit, 100)}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, params=params, headers=self._headers())
            if resp.status_code != 200:
                logger.warning("GitHub API error: %s", resp.status_code)
                return []
            return [
                {
                    "sha": c["sha"],
                    "short_sha": c["sha"][:7],
                    "message": c["commit"]["message"].split("\n")[0],
                    "author": c["commit"]["author"]["name"],
                    "date": c["commit"]["author"]["date"],
                }
                for c in resp.json()
            ]

    async def get_commit_files(self, sha: str) -> list[dict]:
        """Get files changed in a specific commit."""
        url = f"{GITHUB_API}/repos/{self.repo}/commits/{sha}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=self._headers())
            if resp.status_code != 200:
                return []
            return [
                {
                    "filename": f["filename"],
                    "status": f["status"],
                    "additions": f["additions"],
                    "deletions": f["deletions"],
                    "patch": f.get("patch", "")[:1000],
                }
                for f in resp.json().get("files", [])
            ]

    SCHEMA_KEYWORDS = [
        "schema", "migration", "alter", "column", "rename",
        "add_column", "drop_column", "nullable", "type",
        "region", "enum", "customer_id", "order_id",
    ]

    def _is_schema_related(self, commit_msg: str, files: list[dict]) -> bool:
        """Check if a commit looks schema-related."""
        msg_lower = commit_msg.lower()
        if any(kw in msg_lower for kw in self.SCHEMA_KEYWORDS):
            return True

        migration_extensions = (".sql", ".py")
        migration_patterns = ["migrations/", "alembic/", "schema/", "dbt/"]
        for f in files:
            fn = f.get("filename", "").lower()
            if any(fn.endswith(ext) for ext in migration_extensions):
                if any(pat in fn for pat in migration_patterns):
                    return True
            patch = f.get("patch", "").lower()
            if "alter table" in patch or "add column" in patch or "drop column" in patch:
                return True

        return False

    async def find_suspect_commits(
        self,
        table_name: str = "",
        drift_info: dict | None = None,
        branch: str = "main",
        limit: int = 20,
    ) -> list[dict]:
        """Find commits that may have caused schema drift."""
        commits = await self.get_recent_commits(branch=branch, limit=limit)
        suspects = []

        for commit in commits:
            files = await self.get_commit_files(commit["sha"])

            if self._is_schema_related(commit["message"], files):
                relevance = self._score_relevance(commit, files, table_name, drift_info)
                if relevance > 0:
                    suspects.append({
                        **commit,
                        "files_changed": [f["filename"] for f in files],
                        "relevance_score": relevance,
                        "reason": self._explain_relevance(commit, files, table_name),
                    })

        suspects.sort(key=lambda x: x["relevance_score"], reverse=True)
        return suspects[:5]

    def _score_relevance(
        self,
        commit: dict,
        files: list[dict],
        table_name: str,
        drift_info: dict | None,
    ) -> float:
        """Score how relevant a commit is to the detected drift."""
        score = 0.0
        msg = commit["message"].lower()

        if table_name and table_name.lower() in msg:
            score += 5.0

        for f in files:
            fn = f["filename"].lower()
            if table_name and table_name.lower() in fn:
                score += 3.0
            if any(kw in fn for kw in ["migration", "schema", "alembic", "dbt"]):
                score += 2.0

        if drift_info:
            for col in drift_info.get("added_columns", []):
                if col.get("name", "").lower() in msg:
                    score += 4.0
            for col in drift_info.get("removed_columns", []):
                if col.get("name", "").lower() in msg:
                    score += 4.0

        if any(kw in msg for kw in self.SCHEMA_KEYWORDS):
            score += 1.0

        return score

    def _explain_relevance(
        self, commit: dict, files: list[dict], table_name: str
    ) -> str:
        """Generate a human-readable explanation of why this commit is relevant."""
        reasons = []
        msg = commit["message"].lower()

        if table_name and table_name.lower() in msg:
            reasons.append(f"commit message references table '{table_name}'")

        migration_files = [
            f["filename"] for f in files
            if any(kw in f["filename"].lower() for kw in ["migration", "schema", "alembic"])
        ]
        if migration_files:
            reasons.append(f"touches migration files: {', '.join(migration_files[:3])}")

        if any(kw in msg for kw in ["alter", "rename", "drop", "add column"]):
            reasons.append("commit message mentions schema alteration")

        return "; ".join(reasons) if reasons else "schema-related commit"

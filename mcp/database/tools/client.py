"""ClickHouse client for database MCP tools."""

import json
import re

import httpx

from apps.api.app.core.config import settings

IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _validate_identifier(name: str) -> None:
    if not name or not IDENTIFIER_PATTERN.match(name):
        raise ValueError(f"Invalid identifier: {name!r}")


class ClickHouseClient:
    """Async client for ClickHouse HTTP interface."""

    def __init__(self) -> None:
        self.url = f"http://{settings.clickhouse_host}:{settings.clickhouse_port}"
        self.database = settings.clickhouse_database

    async def execute(self, query: str) -> list[dict]:
        """Execute a query and return results as list of dicts."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.url}/",
                params={"database": self.database, "default_format": "JSONEachRow"},
                content=query,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"ClickHouse error: {resp.text}")

            text = resp.text.strip()
            if not text:
                return []

            return [json.loads(line) for line in text.split("\n") if line.strip()]

    async def list_tables(self, database: str | None = None) -> list[str]:
        """List all tables in the database."""
        db = database or self.database
        _validate_identifier(db)
        rows = await self.execute(f"SHOW TABLES FROM {db}")
        return [row.get("name", "") for row in rows]

    async def describe_table(self, table: str, database: str | None = None) -> list[dict]:
        """Get column definitions for a table."""
        db = database or self.database
        _validate_identifier(db)
        _validate_identifier(table)
        return await self.execute(f"DESCRIBE TABLE {db}.{table}")

    async def get_table_count(self, table: str) -> int:
        """Get row count for a table."""
        _validate_identifier(table)
        rows = await self.execute(
            f"SELECT count() as cnt FROM {self.database}.{table}"
        )
        return rows[0].get("cnt", 0) if rows else 0


clickhouse_client = ClickHouseClient()

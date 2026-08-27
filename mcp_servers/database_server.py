"""Database MCP Server — exposes ClickHouse tools via MCP protocol.

Run with: python -m mcp_servers.database_server

This server provides read-only ClickHouse tools that TrueForge can connect to.
"""

import json
import logging
import os
import re

import httpx
from fastmcp import FastMCP

logger = logging.getLogger(__name__)

CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_DB = os.getenv("CLICKHOUSE_DATABASE", "dataforge")
CLICKHOUSE_URL = f"http://{CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}"

IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

mcp = FastMCP(
    "dataforge-database",
    description="Read-only ClickHouse database tools for DataForge investigation",
)


def _validate_identifier(name: str) -> str:
    if not name or not IDENTIFIER_PATTERN.match(name):
        raise ValueError(f"Invalid identifier: {name!r}")
    return name


async def _query(sql: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{CLICKHOUSE_URL}/",
            params={"database": CLICKHOUSE_DB, "default_format": "JSONEachRow"},
            content=sql,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"ClickHouse query failed ({resp.status_code}): {resp.text}")
        text = resp.text.strip()
        if not text:
            return []
        return [json.loads(line) for line in text.split("\n") if line.strip()]


@mcp.tool()
async def list_tables() -> list[dict]:
    """List all tables in the dataforge database."""
    rows = await _query(f"SHOW TABLES FROM {CLICKHOUSE_DB}")
    return [{"name": row.get("name", "")} for row in rows]


@mcp.tool()
async def describe_table(table: str) -> dict:
    """Get the schema of a table."""
    tbl = _validate_identifier(table)
    rows = await _query(f"DESCRIBE TABLE {CLICKHOUSE_DB}.{tbl}")
    return {"table": tbl, "columns": rows}


@mcp.tool()
async def execute_select(query: str) -> list[dict]:
    """Execute a read-only SELECT query.

    Only SELECT queries are allowed. All others are rejected.
    """
    q = query.strip()
    if not q.upper().startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed")
    if ";" in q[:-1]:
        raise ValueError("Multiple statements not allowed")

    # Enforce row limit
    if "LIMIT" not in q.upper():
        q += " LIMIT 1000"

    return await _query(q)


@mcp.tool()
async def profile_column(table: str, column: str) -> dict:
    """Get column statistics: null rate, distinct count, min, max."""
    tbl = _validate_identifier(table)
    col = _validate_identifier(column)

    sql = (
        f"SELECT "
        f"  count() as total_rows, "
        f"  countIf({col} IS NULL) as null_count, "
        f"  round(countIf({col} IS NULL) / count(), 4) as null_rate, "
        f"  uniq({col}) as distinct_count, "
        f"  min(CAST({col} AS String)) as min_val, "
        f"  max(CAST({col} AS String)) as max_val "
        f"FROM {CLICKHOUSE_DB}.{tbl}"
    )
    rows = await _query(sql)
    return {"table": tbl, "column": col, "stats": rows[0] if rows else {}}


@mcp.tool()
async def get_recent_records(table: str, limit: int = 100) -> list[dict]:
    """Get recent records from a table."""
    tbl = _validate_identifier(table)
    limit = min(limit, 1000)
    rows = await _query(f"SELECT * FROM {CLICKHOUSE_DB}.{tbl} ORDER BY 1 DESC LIMIT {limit}")
    return {"table": tbl, "records": rows, "count": len(rows)}


if __name__ == "__main__":
    mcp.run(transport="stdio")

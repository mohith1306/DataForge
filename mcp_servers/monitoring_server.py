"""Monitoring MCP Server — exposes pipeline monitoring tools via MCP protocol.

Run with: python -m mcp_servers.monitoring_server

This server provides pipeline status, logs, and metrics tools.
"""

import json
import logging
import os

import httpx
from fastmcp import FastMCP

logger = logging.getLogger(__name__)

CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_DB = os.getenv("CLICKHOUSE_DATABASE", "dataforge")
CLICKHOUSE_URL = f"http://{CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}"

mcp = FastMCP(
    "dataforge-monitoring",
    description="Pipeline monitoring tools for DataForge investigation",
)


async def _query(sql: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=30) as client:
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
async def get_pipeline_status(pipeline_id: str | None = None) -> dict:
    """Get current status of pipelines — latest run per pipeline."""
    if pipeline_id:
        sql = (
            f"SELECT pipeline_id, pipeline_name, status, started_at, completed_at, "
            f"error_message, rows_processed "
            f"FROM {CLICKHOUSE_DB}.pipeline_events "
            f"WHERE pipeline_id = '{pipeline_id}' "
            f"ORDER BY started_at DESC LIMIT 1"
        )
    else:
        sql = (
            f"SELECT pipeline_id, "
            f"argMax(pipeline_name, started_at) as pipeline_name, "
            f"argMax(status, started_at) as status, "
            f"argMax(started_at, started_at) as started_at, "
            f"argMax(completed_at, started_at) as completed_at, "
            f"argMax(error_message, started_at) as error_message, "
            f"argMax(rows_processed, started_at) as rows_processed "
            f"FROM {CLICKHOUSE_DB}.pipeline_events "
            f"GROUP BY pipeline_id "
            f"ORDER BY started_at DESC"
        )
    rows = await _query(sql)
    return {"pipelines": rows, "count": len(rows)}


@mcp.tool()
async def get_pipeline_logs(pipeline_id: str, limit: int = 50) -> dict:
    """Get error logs for a pipeline."""
    sql = (
        f"SELECT pipeline_id, pipeline_name, status, started_at, error_message "
        f"FROM {CLICKHOUSE_DB}.pipeline_events "
        f"WHERE pipeline_id = '{pipeline_id}' "
        f"AND status = 'FAILED' "
        f"ORDER BY started_at DESC LIMIT {limit}"
    )
    rows = await _query(sql)
    return {"pipeline_id": pipeline_id, "error_logs": rows, "count": len(rows)}


@mcp.tool()
async def get_failed_jobs(days: int = 7) -> dict:
    """Get all failed pipeline jobs in the last N days."""
    sql = (
        f"SELECT pipeline_id, pipeline_name, status, started_at, error_message "
        f"FROM {CLICKHOUSE_DB}.pipeline_events "
        f"WHERE status = 'FAILED' "
        f"AND started_at >= now() - INTERVAL {days} DAY "
        f"ORDER BY started_at DESC"
    )
    rows = await _query(sql)
    return {"failed_jobs": rows, "count": len(rows)}


@mcp.tool()
async def get_pipeline_metrics(pipeline_id: str) -> dict:
    """Get performance metrics for a pipeline."""
    sql = (
        f"SELECT pipeline_id, "
        f"count() as total_runs, "
        f"countIf(status = 'SUCCESS') as success_count, "
        f"countIf(status = 'FAILED') as failed_count, "
        f"avg(dateDiff('second', started_at, completed_at)) as avg_duration_sec, "
        f"max(dateDiff('second', started_at, completed_at)) as max_duration_sec, "
        f"sum(rows_processed) as total_rows_processed "
        f"FROM {CLICKHOUSE_DB}.pipeline_events "
        f"WHERE pipeline_id = '{pipeline_id}' "
        f"AND started_at >= now() - INTERVAL 30 DAY "
        f"GROUP BY pipeline_id"
    )
    rows = await _query(sql)
    return {"metrics": rows[0] if rows else {}, "pipeline_id": pipeline_id}


if __name__ == "__main__":
    mcp.run(transport="stdio")

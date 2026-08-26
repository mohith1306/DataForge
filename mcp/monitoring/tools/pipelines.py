"""Pipeline MCP tools — query pipeline_events in ClickHouse for status, logs, and metrics."""

import httpx

CLICKHOUSE_URL = "http://localhost:8123"
CLICKHOUSE_DB = "dataforge"


async def _query(sql: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{CLICKHOUSE_URL}/",
            params={"database": CLICKHOUSE_DB, "default_format": "JSONEachRow"},
            content=sql,
        )
        if resp.status_code != 200:
            return [{"error": resp.text}]
        text = resp.text.strip()
        if not text:
            return []
        import json
        return [json.loads(line) for line in text.split("\n") if line.strip()]


async def get_pipeline_status(pipeline_id: str | None = None) -> dict:
    """Get current status of pipelines."""
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
            f"SELECT pipeline_id, pipeline_name, status, started_at, completed_at, "
            f"error_message, rows_processed "
            f"FROM {CLICKHOUSE_DB}.pipeline_events "
            f"ORDER BY started_at DESC LIMIT 20"
        )
    rows = await _query(sql)
    return {"pipelines": rows, "count": len(rows)}


async def get_pipeline_runs(pipeline_id: str, days: int = 7) -> dict:
    """Get recent runs for a specific pipeline."""
    sql = (
        f"SELECT pipeline_id, pipeline_name, status, started_at, completed_at, "
        f"error_message, rows_processed "
        f"FROM {CLICKHOUSE_DB}.pipeline_events "
        f"WHERE pipeline_id = '{pipeline_id}' "
        f"AND started_at >= now() - INTERVAL {days} DAY "
        f"ORDER BY started_at DESC"
    )
    rows = await _query(sql)
    success = sum(1 for r in rows if r.get("status") == "SUCCESS")
    failed = sum(1 for r in rows if r.get("status") == "FAILED")
    return {
        "pipeline_id": pipeline_id,
        "total_runs": len(rows),
        "success_count": success,
        "failed_count": failed,
        "runs": rows,
    }


async def get_pipeline_logs(pipeline_id: str, limit: int = 50) -> dict:
    """Get error logs for a pipeline (from pipeline_events error_message field)."""
    sql = (
        f"SELECT pipeline_id, pipeline_name, status, started_at, error_message "
        f"FROM {CLICKHOUSE_DB}.pipeline_events "
        f"WHERE pipeline_id = '{pipeline_id}' "
        f"AND status = 'FAILED' "
        f"ORDER BY started_at DESC LIMIT {limit}"
    )
    rows = await _query(sql)
    return {"pipeline_id": pipeline_id, "error_logs": rows, "count": len(rows)}


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
        f"AND started_at >= now() - INTERVAL 30 DAY"
    )
    rows = await _query(sql)
    return {"metrics": rows[0] if rows else {}, "pipeline_id": pipeline_id}

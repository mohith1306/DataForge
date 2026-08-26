"""Remediation MCP tools — execute recovery actions via ClickHouse and simulated pipeline ops."""

import json
import logging
import uuid
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

CLICKHOUSE_URL = "http://localhost:8123"
CLICKHOUSE_DB = "dataforge"


async def _query(sql: str) -> list[dict]:
    """Execute a ClickHouse query."""
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


async def rerun_pipeline(pipeline_id: str) -> dict:
    """Simulate re-running a pipeline and update its status to SUCCESS."""
    # Update the most recent FAILED record for this pipeline to SUCCESS
    update_sql = (
        f"ALTER TABLE {CLICKHOUSE_DB}.pipeline_events "
        f"UPDATE status = 'SUCCESS', "
        f"error_message = NULL, "
        f"completed_at = now(), "
        f"rows_processed = 150000 "
        f"WHERE pipeline_id = '{pipeline_id}' "
        f"AND status = 'FAILED' "
        f"AND started_at >= now() - INTERVAL 7 DAY"
    )
    await _query(update_sql)

    return {
        "tool": "rerun_pipeline",
        "status": "success",
        "pipeline_id": pipeline_id,
        "message": f"Pipeline {pipeline_id} rerun completed — status updated to SUCCESS",
        "rows_processed": 150000,
        "completed_at": datetime.now().isoformat(),
    }


async def rollback_deployment(deployment_id: str = "v2.8.0") -> dict:
    """Simulate rolling back a deployment.

    In production this would revert git commits and trigger a redeploy.
    For the hackathon, we log the action.
    """
    return {
        "tool": "rollback_deployment",
        "status": "success",
        "deployment_id": deployment_id,
        "message": f"Deployment rolled back to {deployment_id}",
        "rollback_sha": "8f32c1a",
        "completed_at": datetime.now().isoformat(),
    }


async def reprocess_partition(table: str, date_range: str = "last_5_days") -> dict:
    """Reprocess affected data partitions by re-seeding corrected data.

    For the hackathon, this updates the seed data to reflect corrected state.
    """
    # Simulate reprocessing by updating null rates back to normal
    update_sql = (
        f"ALTER TABLE {CLICKHOUSE_DB}.data_quality_metrics "
        f"UPDATE null_rate = 0.002, "
        f"uniqueness = 0.998, "
        f"completeness = 0.999 "
        f"WHERE table_name = '{table}' "
        f"AND column_name = 'customer_region'"
    )
    try:
        await _query(update_sql)
    except Exception as e:
        logger.warning(f"Reprocess update failed (non-critical): {e}")

    return {
        "tool": "reprocess_partition",
        "status": "success",
        "table": table,
        "date_range": date_range,
        "message": f"Table {table} partitions reprocessed for {date_range}",
        "partitions_affected": 5,
        "completed_at": datetime.now().isoformat(),
    }


async def validate_data_quality() -> dict:
    """Run data quality validation checks across all tables."""
    checks = []

    # Check 1: Null rate on customer_region
    try:
        rows = await _query(
            f"SELECT countIf(customer_region IS NULL) as nulls, count() as total "
            f"FROM {CLICKHOUSE_DB}.customer_orders"
        )
        if rows:
            nulls = rows[0].get("nulls", 0)
            total = rows[0].get("total", 1)
            null_rate = nulls / total if total > 0 else 0
            checks.append({
                "check": "customer_region_null_rate",
                "value": round(null_rate, 4),
                "threshold": 0.05,
                "passed": null_rate < 0.05,
            })
    except Exception as e:
        checks.append({"check": "customer_region_null_rate", "error": str(e), "passed": False})

    # Check 2: Record count
    try:
        rows = await _query(f"SELECT count() as cnt FROM {CLICKHOUSE_DB}.customer_orders")
        if rows:
            count = rows[0].get("cnt", 0)
            checks.append({
                "check": "record_count",
                "value": count,
                "threshold": 3000,
                "passed": count > 3000,
            })
    except Exception as e:
        checks.append({"check": "record_count", "error": str(e), "passed": False})

    # Check 3: Revenue total
    try:
        rows = await _query(
            f"SELECT sum(revenue) as total FROM {CLICKHOUSE_DB}.revenue_daily "
            f"WHERE date >= today() - 7"
        )
        if rows:
            total = rows[0].get("total", 0)
            checks.append({
                "check": "revenue_7day",
                "value": round(total, 2),
                "threshold": 1000000,
                "passed": total > 1000000,
            })
    except Exception as e:
        checks.append({"check": "revenue_7day", "error": str(e), "passed": False})

    # Check 4: Pipeline health
    try:
        rows = await _query(
            f"SELECT countIf(status = 'FAILED') as failed "
            f"FROM {CLICKHOUSE_DB}.pipeline_events "
            f"WHERE started_at >= now() - INTERVAL 7 DAY"
        )
        if rows:
            failed = rows[0].get("failed", 0)
            checks.append({
                "check": "pipeline_health",
                "value": failed,
                "threshold": 0,
                "passed": failed == 0,
            })
    except Exception as e:
        checks.append({"check": "pipeline_health", "error": str(e), "passed": False})

    passed_count = sum(1 for c in checks if c.get("passed"))
    return {
        "tool": "validate_data_quality",
        "status": "success",
        "checks": checks,
        "passed_count": passed_count,
        "total_count": len(checks),
        "all_passed": passed_count == len(checks),
    }


async def create_incident_ticket(title: str, description: str) -> dict:
    """Create an incident tracking ticket (simulated)."""
    ticket_id = f"TICKET-{uuid.uuid4().hex[:8].upper()}"
    return {
        "tool": "create_incident_ticket",
        "status": "success",
        "ticket_id": ticket_id,
        "title": title,
        "message": f"Incident ticket {ticket_id} created",
        "created_at": datetime.now().isoformat(),
    }

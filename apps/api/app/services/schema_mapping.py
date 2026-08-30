"""Schema mapping — lets users map their own table/column names to DataForge's model.

Users configure this via:
1. /api/database/setup endpoint (interactive wizard)
2. dataforge.schema.json file (manual)
3. MONITOR_SCHEMA_JSON env var (advanced)

DataForge needs to know:
- Which table has pipeline run history
- Which columns map to: pipeline_id, pipeline_name, status, started_at, error_message
- Which table has data quality metrics (optional)
- Which column to check for null rates (optional)
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CONFIG_FILE = Path("dataforge.schema.json")


# ── Default schema (matches ClickHouse init.sql) ──────────────────────────────

DEFAULT_SCHEMA: dict[str, Any] = {
    "pipeline_table": "pipeline_events",
    "pipeline_columns": {
        "pipeline_id": "pipeline_id",
        "pipeline_name": "pipeline_name",
        "status": "status",
        "started_at": "started_at",
        "error_message": "error_message",
    },
    "quality_table": "customer_orders",
    "quality_columns": {
        "null_check_column": "customer_region",
    },
    "status_values": {
        "failed": "FAILED",
        "success": "SUCCESS",
    },
}


def load_schema() -> dict[str, Any]:
    """Load schema mapping from file, env, or defaults."""
    # 1. Try env var
    env_json = os.getenv("MONITOR_SCHEMA_JSON", "")
    if env_json:
        try:
            return json.loads(env_json)
        except json.JSONDecodeError:
            logger.warning("Invalid MONITOR_SCHEMA_JSON, falling back")

    # 2. Try config file
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except json.JSONDecodeError:
            logger.warning("Invalid %s, falling back", CONFIG_FILE)

    return DEFAULT_SCHEMA


def save_schema(schema: dict[str, Any]) -> None:
    """Save schema mapping to config file."""
    CONFIG_FILE.write_text(json.dumps(schema, indent=2))
    logger.info("Saved schema to %s", CONFIG_FILE)


def generate_create_table_sql(db_type: str = "clickhouse") -> dict[str, str]:
    """Generate CREATE TABLE SQL for the user's target database."""
    schema = load_schema()
    pt = schema["pipeline_table"]
    qt = schema["quality_table"]
    pc = schema["pipeline_columns"]

    if db_type == "clickhouse":
        return {
            pt: f"""
CREATE TABLE IF NOT EXISTS {pt} (
    {pc['pipeline_id']} String,
    {pc['pipeline_name']} String,
    {pc['status']} String,
    {pc['started_at']} DateTime,
    {pc.get('error_message', 'error_message')} Nullable(String)
) ENGINE = MergeTree()
ORDER BY ({pc['started_at']}, {pc['pipeline_id']})""",
            qt: f"""
CREATE TABLE IF NOT EXISTS {qt} (
    order_id String,
    customer_id String,
    {schema['quality_columns']['null_check_column']} String,
    product_line String,
    order_date DateTime,
    amount Float64,
    status String
) ENGINE = MergeTree()
ORDER BY (order_date)""",
        }
    elif db_type == "postgres":
        return {
            pt: f"""
CREATE TABLE IF NOT EXISTS {pt} (
    {pc['pipeline_id']} VARCHAR(100),
    {pc['pipeline_name']} VARCHAR(200),
    {pc['status']} VARCHAR(20),
    {pc['started_at']} TIMESTAMP,
    {pc.get('error_message', 'error_message')} TEXT
);""",
            qt: f"""
CREATE TABLE IF NOT EXISTS {qt} (
    order_id VARCHAR(100),
    customer_id VARCHAR(100),
    {schema['quality_columns']['null_check_column']} VARCHAR(100),
    product_line VARCHAR(100),
    order_date TIMESTAMP,
    amount DECIMAL(10,2),
    status VARCHAR(20)
);""",
        }
    else:
        return {}


def generate_monitor_sql(db_type: str = "clickhouse") -> dict[str, str]:
    """Generate the actual monitoring queries using the user's schema."""
    schema = load_schema()
    pt = schema["pipeline_table"]
    pc = schema["pipeline_columns"]
    failed = schema["status_values"]["failed"]

    if db_type == "clickhouse":
        return {
            "pipeline_failures": f"""
SELECT {pc['pipeline_id']}, {pc['pipeline_name']}, {pc['status']}, {pc['started_at']}, {pc.get('error_message','error_message')}
FROM {pt}
WHERE {pc['status']} = '{failed}'
AND {pc['started_at']} >= now() - INTERVAL {{{{lookback_seconds}}}} SECOND
ORDER BY {pc['started_at']} DESC LIMIT 20""",
            "pipeline_freshness": f"""
SELECT {pc['pipeline_id']}, {pc['pipeline_name']}, max({pc['started_at']}) as last_run
FROM {pt}
GROUP BY {pc['pipeline_id']}, {pc['pipeline_name']}
HAVING last_run < now() - INTERVAL {{{{stale_minutes}}}} MINUTE
ORDER BY last_run ASC""",
            "data_quality": f"""
SELECT countIf({schema['quality_columns']['null_check_column']} IS NULL) as nulls, count() as total
FROM {schema['quality_table']}""",
        }
    elif db_type == "postgres":
        return {
            "pipeline_failures": f"""
SELECT {pc['pipeline_id']}, {pc['pipeline_name']}, {pc['status']}, {pc['started_at']}, {pc.get('error_message','error_message')}
FROM {pt}
WHERE {pc['status']} = '{failed}'
AND {pc['started_at']} >= now() - interval '{{{{lookback_seconds}}}} seconds'
ORDER BY {pc['started_at']} DESC LIMIT 20""",
            "pipeline_freshness": f"""
SELECT {pc['pipeline_id']}, {pc['pipeline_name']}, max({pc['started_at']}) as last_run
FROM {pt}
GROUP BY {pc['pipeline_id']}, {pc['pipeline_name']}
HAVING max({pc['started_at']}) < now() - interval '{{{{stale_minutes}}}} minutes'
ORDER BY last_run ASC""",
            "data_quality": f"""
SELECT count(*) FILTER (WHERE {schema['quality_columns']['null_check_column']} IS NULL) as nulls, count(*) as total
FROM {schema['quality_table']}""",
        }
    else:
        return {}

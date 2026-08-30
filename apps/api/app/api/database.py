"""Database configuration API — lets users view/set the monitor DB backend."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/database", tags=["database"])


class DBConfigResponse(BaseModel):
    db_type: str
    configured: bool
    adapter_class: str
    tables_required: list[str]
    docs: str


@router.get("/config", response_model=DBConfigResponse)
async def get_db_config() -> DBConfigResponse:
    """Return current monitor database configuration."""
    import os
    db_type = os.getenv("MONITOR_DB_TYPE", "clickhouse")

    adapter_docs = {
        "clickhouse": (
            "Uses ClickHouse HTTP interface. "
            "Required env: CLICKHOUSE_HOST, CLICKHOUSE_PORT, CLICKHOUSE_DATABASE. "
            "Required tables: pipeline_events, customer_orders."
        ),
        "postgres": (
            "Uses asyncpg with PostgreSQL. "
            "Required env: MONITOR_DB_URL (or DATABASE_URL). "
            "Required tables: pipeline_events, customer_orders."
        ),
        "custom": (
            "Uses user-provided SQL queries via HTTP endpoint. "
            "Required env: MONITOR_CUSTOM_QUERY_URL, MONITOR_QUERIES_JSON. "
            "Your endpoint receives {\"query\": \"SQL\"} and returns rows."
        ),
    }

    from apps.api.app.services.db_adapter import create_monitor_adapter
    try:
        adapter = create_monitor_adapter()
        adapter_class = type(adapter).__name__
        configured = True
    except Exception as e:
        adapter_class = "None"
        configured = False

    return DBConfigResponse(
        db_type=db_type,
        configured=configured,
        adapter_class=adapter_class,
        tables_required=["pipeline_events", "customer_orders"],
        docs=adapter_docs.get(db_type, "Unknown adapter"),
    )


@router.get("/schema-example")
async def get_schema_example() -> dict:
    """Return example table schemas for the monitor."""
    return {
        "clickhouse": {
            "pipeline_events": """
CREATE TABLE pipeline_events (
    pipeline_id String,
    pipeline_name String,
    status String,           -- 'SUCCESS' or 'FAILED'
    started_at DateTime,
    completed_at Nullable(DateTime),
    error_message Nullable(String),
    rows_processed UInt32
) ENGINE = MergeTree()
ORDER BY (started_at, pipeline_id)""",
            "customer_orders": """
CREATE TABLE customer_orders (
    order_id String,
    customer_id String,
    customer_region String,
    product_line String,
    order_date DateTime,
    amount Float64,
    status String
) ENGINE = MergeTree()
ORDER BY (order_date, order_id)""",
        },
        "postgres": {
            "pipeline_events": """
CREATE TABLE pipeline_events (
    pipeline_id VARCHAR(100),
    pipeline_name VARCHAR(200),
    status VARCHAR(20),      -- 'SUCCESS' or 'FAILED'
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    rows_processed INTEGER
);""",
            "customer_orders": """
CREATE TABLE customer_orders (
    order_id VARCHAR(100),
    customer_id VARCHAR(100),
    customer_region VARCHAR(100),
    product_line VARCHAR(100),
    order_date TIMESTAMP,
    amount DECIMAL(10,2),
    status VARCHAR(20)
);""",
        },
        "custom_queries_example": {
            "pipeline_failures": "SELECT pipeline_id, pipeline_name, status, started_at, error_message FROM pipeline_events WHERE status = 'FAILED' AND started_at >= now() - interval '{lookback_seconds} seconds' ORDER BY started_at DESC LIMIT 20",
            "pipeline_freshness": "SELECT pipeline_id, pipeline_name, max(started_at) as last_run FROM pipeline_events GROUP BY pipeline_id, pipeline_name HAVING max(started_at) < now() - interval '{stale_minutes} minutes' ORDER BY last_run ASC",
            "data_quality": "SELECT count(*) FILTER (WHERE customer_region IS NULL) as nulls, count(*) as total FROM customer_orders",
        },
    }

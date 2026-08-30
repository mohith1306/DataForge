"""Database configuration API — setup wizard for custom databases."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/database", tags=["database"])


class SchemaMappingInput(BaseModel):
    """User's database schema mapping."""
    db_type: str  # clickhouse | postgres | custom
    database: str = "dataforge"  # database name
    schema_name: str = "public"  # for postgres
    pipeline_table: str
    pipeline_columns: dict[str, str]  # map logical name → actual column
    quality_table: str = ""
    quality_columns: dict[str, str] = {}
    status_values: dict[str, str] = {"failed": "FAILED", "success": "SUCCESS"}


class SetupResponse(BaseModel):
    status: str
    message: str
    schema: dict
    create_table_sql: dict[str, str]
    env_vars: dict[str, str]
    test_queries: dict[str, str]


@router.get("/config")
async def get_db_config() -> dict:
    """Return current monitor database configuration."""
    import os
    from apps.api.app.services.db_adapter import create_monitor_adapter
    from apps.api.app.services.schema_mapping import load_schema

    db_type = os.getenv("MONITOR_DB_TYPE", "clickhouse")
    schema = load_schema()

    try:
        adapter = create_monitor_adapter()
        adapter_class = type(adapter).__name__
        configured = True
    except Exception:
        adapter_class = "None"
        configured = False

    return {
        "db_type": db_type,
        "configured": configured,
        "adapter_class": adapter_class,
        "schema": schema,
        "docs": {
            "clickhouse": "ClickHouse HTTP interface",
            "postgres": "PostgreSQL via asyncpg",
            "custom": "User-provided SQL via HTTP endpoint",
        }.get(db_type, "Unknown"),
    }


@router.post("/setup", response_model=SetupResponse)
async def setup_database(input: SchemaMappingInput) -> SetupResponse:
    """Setup wizard — configure DataForge for your database.

    Takes your table/column names and generates:
    1. Schema mapping file (dataforge.schema.json)
    2. CREATE TABLE SQL for your database
    3. Environment variables to set
    4. Test queries to verify everything works
    """
    from apps.api.app.services.schema_mapping import (
        save_schema,
        generate_create_table_sql,
        generate_monitor_sql,
    )

    # Build schema mapping
    schema = {
        "pipeline_table": input.pipeline_table,
        "pipeline_columns": input.pipeline_columns,
        "quality_table": input.quality_table,
        "quality_columns": input.quality_columns,
        "status_values": input.status_values,
    }

    # Save to file
    save_schema(schema)

    # Generate SQL
    create_sql = generate_create_table_sql(input.db_type)
    monitor_sql = generate_monitor_sql(input.db_type)

    # Build env vars
    env_vars = {"MONITOR_DB_TYPE": input.db_type}
    if input.db_type == "postgres":
        env_vars["MONITOR_DB_URL"] = f"postgresql://user:password@localhost:5432/{input.database}"
        env_vars["MONITOR_DB_SCHEMA"] = input.schema_name
    elif input.db_type == "custom":
        env_vars["MONITOR_CUSTOM_QUERY_URL"] = "http://your-endpoint/query"
        env_vars["MONITOR_QUERIES_JSON"] = "See monitor_sql below"

    return SetupResponse(
        status="success",
        message=(
            f"Schema saved to {str(__import__('pathlib').Path('dataforge.schema.json'))}. "
            f"Set MONITOR_DB_TYPE={input.db_type} in .env and restart the API server."
        ),
        schema=schema,
        create_table_sql=create_sql,
        env_vars=env_vars,
        test_queries=monitor_sql,
    )


@router.get("/schema-example")
async def get_schema_example() -> dict:
    """Return example schemas for all supported databases."""
    from apps.api.app.services.schema_mapping import DEFAULT_SCHEMA

    return {
        "default_schema": DEFAULT_SCHEMA,
        "example_configs": {
            "postgresql_own_database": {
                "db_type": "postgres",
                "database": "my_analytics",
                "pipeline_table": "etl_runs",
                "pipeline_columns": {
                    "pipeline_id": "job_id",
                    "pipeline_name": "job_name",
                    "status": "run_status",
                    "started_at": "start_time",
                    "error_message": "error_detail",
                },
                "quality_table": "orders",
                "quality_columns": {"null_check_column": "region"},
                "status_values": {"failed": "FAILED", "success": "SUCCESS"},
            },
            "mysql_own_database": {
                "db_type": "custom",
                "note": "Use MONITOR_CUSTOM_QUERY_URL with a REST endpoint that runs MySQL queries",
                "pipeline_table": "pipeline_log",
                "pipeline_columns": {
                    "pipeline_id": "id",
                    "pipeline_name": "name",
                    "status": "result",
                    "started_at": "created_at",
                    "error_message": "error",
                },
            },
            "snowflake": {
                "db_type": "custom",
                "note": "Use MONITOR_CUSTOM_QUERY_URL pointing to a Snowflake REST API wrapper",
            },
        },
    }


@router.get("/test-connection")
async def test_connection() -> dict:
    """Test that the database adapter can connect and run queries."""
    from apps.api.app.services.db_adapter import create_monitor_adapter

    try:
        adapter = create_monitor_adapter()
        failures = await adapter.check_pipeline_failures(lookback_seconds=3600)
        freshness = await adapter.check_pipeline_freshness(stale_minutes=120)
        return {
            "status": "connected",
            "adapter": type(adapter).__name__,
            "recent_failures": len(failures),
            "stale_pipelines": len(freshness),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Connection failed: {e}")

"""Database adapters for the health monitor.

Provides a unified interface for querying pipeline health data
from different database backends (ClickHouse, PostgreSQL, custom).

Users can plug in their own database by:
1. Setting MONITOR_DB_TYPE in .env (clickhouse | postgres | custom)
2. Setting MONITOR_DB_URL to their connection string
3. Running POST /api/database/setup with their table/column names
   (generates dataforge.schema.json with the correct SQL)
"""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any

import httpx

from apps.api.app.services.schema_mapping import load_schema

logger = logging.getLogger(__name__)


class MonitorDBAdapter(ABC):
    """Abstract base class for monitor database adapters."""

    @abstractmethod
    async def check_pipeline_failures(self, lookback_seconds: int = 60) -> list[dict]:
        """Return recently failed pipeline runs."""
        ...

    @abstractmethod
    async def check_pipeline_freshness(self, stale_minutes: int = 60) -> list[dict]:
        """Return pipelines that haven't run recently."""
        ...

    @abstractmethod
    async def check_data_quality(self) -> list[dict]:
        """Check data quality metrics (null rates, etc)."""
        ...


# ── ClickHouse Adapter ────────────────────────────────────────────────────────

class ClickHouseAdapter(MonitorDBAdapter):
    """Adapter for ClickHouse via HTTP interface."""

    def __init__(self, base_url: str, database: str):
        self.base_url = base_url
        self.database = database
        self._schema = load_schema()

    async def _query(self, sql: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}/",
                params={"database": self.database, "default_format": "JSONEachRow"},
                content=sql,
            )
            if resp.status_code != 200:
                logger.warning("ClickHouse query failed (%s): %s", resp.status_code, resp.text[:200])
                return []
            text = resp.text.strip()
            if not text:
                return []
            return [json.loads(line) for line in text.split("\n") if line.strip()]

    async def check_pipeline_failures(self, lookback_seconds: int = 60) -> list[dict]:
        s = self._schema
        pt = s["pipeline_table"]
        pc = s["pipeline_columns"]
        failed = s["status_values"]["failed"]
        sql = (
            f"SELECT {pc['pipeline_id']}, {pc['pipeline_name']}, {pc['status']}, "
            f"{pc['started_at']}, {pc.get('error_message', 'error_message')} "
            f"FROM {self.database}.{pt} "
            f"WHERE {pc['status']} = '{failed}' "
            f"AND {pc['started_at']} >= now() - INTERVAL {lookback_seconds} SECOND "
            f"ORDER BY {pc['started_at']} DESC LIMIT 20"
        )
        return await self._query(sql)

    async def check_pipeline_freshness(self, stale_minutes: int = 60) -> list[dict]:
        s = self._schema
        pt = s["pipeline_table"]
        pc = s["pipeline_columns"]
        sql = (
            f"SELECT {pc['pipeline_id']}, {pc['pipeline_name']}, max({pc['started_at']}) as last_run "
            f"FROM {self.database}.{pt} "
            f"GROUP BY {pc['pipeline_id']}, {pc['pipeline_name']} "
            f"HAVING last_run < now() - INTERVAL {stale_minutes} MINUTE "
            f"ORDER BY last_run ASC"
        )
        return await self._query(sql)

    async def check_data_quality(self) -> list[dict]:
        s = self._schema
        qt = s["quality_table"]
        qc = s["quality_columns"]
        checks = []
        try:
            rows = await self._query(
                f"SELECT countIf({qc['null_check_column']} IS NULL) as nulls, count() as total "
                f"FROM {self.database}.{qt}"
            )
            if rows:
                nulls = rows[0].get("nulls", 0)
                total = rows[0].get("total", 1)
                rate = nulls / total if total > 0 else 0
                if rate > 0.05:
                    checks.append({
                        "table": qt,
                        "column": qc["null_check_column"],
                        "null_rate": round(rate, 4),
                        "threshold": 0.05,
                    })
        except Exception as exc:
            logger.debug("DQ check skipped: %s", exc)
        return checks


# ── PostgreSQL Adapter ─────────────────────────────────────────────────────────

class PostgresAdapter(MonitorDBAdapter):
    """Adapter for PostgreSQL via asyncpg."""

    def __init__(self, dsn: str, schema: str = "public"):
        self.dsn = dsn
        self.schema = schema
        self._pool = None
        self._schema_config = load_schema()

    async def _get_pool(self):
        if self._pool is None:
            import asyncpg
            self._pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=5)
        return self._pool

    async def _query(self, sql: str) -> list[dict]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql)
            return [dict(r) for r in rows]

    async def check_pipeline_failures(self, lookback_seconds: int = 60) -> list[dict]:
        s = self._schema_config
        pt = s["pipeline_table"]
        pc = s["pipeline_columns"]
        failed = s["status_values"]["failed"]
        sql = f"""
            SELECT {pc['pipeline_id']}, {pc['pipeline_name']}, {pc['status']}, {pc['started_at']}, {pc.get('error_message','error_message')}
            FROM {self.schema}.{pt}
            WHERE {pc['status']} = '{failed}'
            AND {pc['started_at']} >= now() - interval '{lookback_seconds} seconds'
            ORDER BY {pc['started_at']} DESC LIMIT 20
        """
        return await self._query(sql)

    async def check_pipeline_freshness(self, stale_minutes: int = 60) -> list[dict]:
        s = self._schema_config
        pt = s["pipeline_table"]
        pc = s["pipeline_columns"]
        sql = f"""
            SELECT {pc['pipeline_id']}, {pc['pipeline_name']}, max({pc['started_at']}) as last_run
            FROM {self.schema}.{pt}
            GROUP BY {pc['pipeline_id']}, {pc['pipeline_name']}
            HAVING max({pc['started_at']}) < now() - interval '{stale_minutes} minutes'
            ORDER BY last_run ASC
        """
        return await self._query(sql)

    async def check_data_quality(self) -> list[dict]:
        s = self._schema_config
        qt = s["quality_table"]
        qc = s["quality_columns"]
        checks = []
        try:
            rows = await self._query(f"""
                SELECT
                    count(*) FILTER (WHERE {qc['null_check_column']} IS NULL) as nulls,
                    count(*) as total
                FROM {self.schema}.{qt}
            """)
            if rows:
                nulls = rows[0].get("nulls", 0)
                total = rows[0].get("total", 1)
                rate = nulls / total if total > 0 else 0
                if rate > 0.05:
                    checks.append({
                        "table": qt,
                        "column": qc["null_check_column"],
                        "null_rate": round(rate, 4),
                        "threshold": 0.05,
                    })
        except Exception as exc:
            logger.debug("DQ check skipped: %s", exc)
        return checks


# ── Custom SQL Adapter ─────────────────────────────────────────────────────────

class CustomSQLAdapter(MonitorDBAdapter):
    """Adapter that uses user-provided SQL queries via a generic HTTP endpoint.

    Users point this at any database that exposes an HTTP query interface
    (e.g., PostgREST, custom API, Supabase, PlanetScale, Turso, etc.)

    MONITOR_CUSTOM_QUERY_URL must be set to the query endpoint.
    MONITOR_QUERIES_JSON maps check names to SQL strings.
    """

    def __init__(self, query_url: str, queries: dict[str, str], auth_header: str = ""):
        self.query_url = query_url
        self.queries = queries
        self.auth_header = auth_header

    async def _query(self, sql: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=30) as client:
            headers = {"Content-Type": "application/json"}
            if self.auth_header:
                headers["Authorization"] = self.auth_header
            resp = await client.post(
                self.query_url,
                headers=headers,
                json={"query": sql},
            )
            if resp.status_code != 200:
                logger.warning("Custom query failed (%s): %s", resp.status_code, resp.text[:200])
                return []
            data = resp.json()
            if isinstance(data, list):
                return data
            return data.get("rows", data.get("data", []))

    async def check_pipeline_failures(self, lookback_seconds: int = 60) -> list[dict]:
        sql = self.queries.get("pipeline_failures", "")
        if not sql:
            return []
        sql = sql.replace("{lookback_seconds}", str(lookback_seconds))
        return await self._query(sql)

    async def check_pipeline_freshness(self, stale_minutes: int = 60) -> list[dict]:
        sql = self.queries.get("pipeline_freshness", "")
        if not sql:
            return []
        sql = sql.replace("{stale_minutes}", str(stale_minutes))
        return await self._query(sql)

    async def check_data_quality(self) -> list[dict]:
        sql = self.queries.get("data_quality", "")
        if not sql:
            return []
        return await self._query(sql)


# ── Factory ───────────────────────────────────────────────────────────────────

def create_monitor_adapter() -> MonitorDBAdapter:
    """Create the appropriate adapter based on environment config."""
    db_type = os.getenv("MONITOR_DB_TYPE", "clickhouse").lower()

    if db_type == "clickhouse":
        host = os.getenv("CLICKHOUSE_HOST", "localhost")
        port = os.getenv("CLICKHOUSE_PORT", "8123")
        db = os.getenv("CLICKHOUSE_DATABASE", "dataforge")
        return ClickHouseAdapter(base_url=f"http://{host}:{port}", database=db)

    elif db_type == "postgres":
        dsn = os.getenv("MONITOR_DB_URL", os.getenv("DATABASE_URL", ""))
        schema = os.getenv("MONITOR_DB_SCHEMA", "public")
        if not dsn:
            raise ValueError("MONITOR_DB_URL or DATABASE_URL required for postgres adapter")
        return PostgresAdapter(dsn=dsn, schema=schema)

    elif db_type == "custom":
        url = os.getenv("MONITOR_CUSTOM_QUERY_URL", "")
        auth = os.getenv("MONITOR_CUSTOM_AUTH_HEADER", "")
        queries_raw = os.getenv("MONITOR_QUERIES_JSON", "{}")
        if not url:
            raise ValueError("MONITOR_CUSTOM_QUERY_URL required for custom adapter")
        try:
            queries = json.loads(queries_raw)
        except json.JSONDecodeError:
            logger.warning("Invalid MONITOR_QUERIES_JSON, using empty queries")
            queries = {}
        return CustomSQLAdapter(query_url=url, queries=queries, auth_header=auth)

    else:
        raise ValueError(f"Unknown MONITOR_DB_TYPE: {db_type}. Use clickhouse, postgres, or custom.")

"""ClickHouse database connector with auto-discovery."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from apps.api.app.services.connectors.base import DatabaseConnector, ConnectorConfig

logger = logging.getLogger(__name__)


class ClickHouseConnector(DatabaseConnector):
    """ClickHouse connector via HTTP interface."""

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self._base_url = f"http://{config.host}:{config.port or 8123}"

    async def connect(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self._base_url}/ping")
                if resp.status_code == 200:
                    logger.info("Connected to ClickHouse: %s", self._base_url)
                    return True
            return False
        except Exception as e:
            logger.error("ClickHouse connection failed: %s", e)
            return False

    async def disconnect(self) -> None:
        pass  # HTTP, no persistent connection

    async def _query(self, sql: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._base_url}/",
                params={
                    "database": self.config.database,
                    "default_format": "JSONEachRow",
                },
                content=sql,
            )
            if resp.status_code != 200:
                logger.warning("ClickHouse query failed: %s", resp.text[:200])
                return []
            text = resp.text.strip()
            if not text:
                return []
            return [json.loads(line) for line in text.split("\n") if line.strip()]

    async def _query_val(self, sql: str) -> Any:
        rows = await self._query(sql)
        if rows:
            return list(rows[0].values())[0]
        return None

    async def list_tables(self, schema: str | None = None) -> list[str]:
        schema = schema or self.config.database
        rows = await self._query(
            f"SELECT name FROM system.tables WHERE database = '{schema}' ORDER BY name"
        )
        return [r["name"] for r in rows]

    async def describe_table(self, table: str, schema: str | None = None) -> list[dict]:
        schema = schema or self.config.database
        rows = await self._query(
            f"SELECT name, type, default_kind "
            f"FROM system.columns "
            f"WHERE database = '{schema}' AND table = '{table}' "
            f"ORDER BY position"
        )
        return [{"name": r["name"], "type": r["type"], "nullable": False} for r in rows]

    async def execute_query(self, sql: str) -> list[dict]:
        return await self._query(sql)

    async def execute_non_query(self, sql: str) -> None:
        """Execute INSERT/CREATE without returning results."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._base_url}/",
                params={"database": self.config.database},
                content=sql,
            )
            if resp.status_code != 200:
                logger.warning("ClickHouse execute failed: %s", resp.text[:200])

    async def count_rows(self, table: str, schema: str | None = None) -> int:
        schema = schema or self.config.database
        result = await self._query_val(f"SELECT COUNT(*) FROM {schema}.{table}")
        return result or 0

    def get_inject_sql(self) -> list[str]:
        schema = self.config.schema or self.config.database
        qualified = f"{schema}.pipeline_events"

        return [
            f"""CREATE TABLE IF NOT EXISTS {qualified} (
                pipeline_id String,
                pipeline_name String,
                status String,
                started_at DateTime,
                completed_at Nullable(DateTime),
                error_message Nullable(String),
                rows_processed UInt32
            ) ENGINE = MergeTree() ORDER BY tuple()""",
            f"INSERT INTO {qualified} SELECT 'PL-FAIL-001', 'revenue-etl', 'FAILED', now() - INTERVAL 10 MINUTE, NULL, 'Connection timeout to upstream service', toUInt32(0)",
            f"INSERT INTO {qualified} SELECT 'PL-FAIL-002', 'user-sync', 'FAILED', now() - INTERVAL 5 MINUTE, NULL, 'NULL constraint violation on user_id', toUInt32(0)",
            f"INSERT INTO {qualified} SELECT 'PL-FAIL-003', 'order-processing', 'FAILED', now() - INTERVAL 2 MINUTE, NULL, 'Disk space exceeded on /data volume', toUInt32(0)",
            f"INSERT INTO {qualified} SELECT 'PL-STALE-001', 'inventory-sync', 'SUCCESS', now() - INTERVAL 90 MINUTE, now() - INTERVAL 89 MINUTE, NULL, toUInt32(15234)",
            f"INSERT INTO {qualified} SELECT 'PL-STALE-002', 'analytics-daily', 'SUCCESS', now() - INTERVAL 120 MINUTE, now() - INTERVAL 119 MINUTE, NULL, toUInt32(89012)",
            f"INSERT INTO {qualified} SELECT 'PL-OK-001', 'email-campaign', 'SUCCESS', now() - INTERVAL 3 MINUTE, now() - INTERVAL 2 MINUTE, NULL, toUInt32(3456)",
            f"INSERT INTO {qualified} SELECT 'PL-OK-002', 'report-gen', 'SUCCESS', now() - INTERVAL 8 MINUTE, now() - INTERVAL 7 MINUTE, NULL, toUInt32(7890)",
        ]

    def build_monitoring_queries(self, mapping: "TableMapping") -> dict[str, str]:
        """ClickHouse-specific SQL syntax."""
        if mapping.table_type != "pipeline":
            return super().build_monitoring_queries(mapping)

        c = mapping.columns
        table = mapping.table_name
        schema = self.config.schema or self.config.database
        qualified = f"{schema}.{table}"

        failed_vals = "','".join(self.STATUS_FAILED_VALUES)

        return {
            "pipeline_failures": f"""
SELECT {c.get('pipeline_id','id')}, {c.get('pipeline_name','name')}, {c.get('status','status')}, {c.get('started_at','started_at')}, {c.get('error_message','error_message')}
FROM {qualified}
WHERE {c.get('status','status')} IN ('{failed_vals}')
AND {c.get('started_at','started_at')} >= now() - INTERVAL 1 HOUR
ORDER BY {c.get('started_at','started_at')} DESC LIMIT 20""",
            "pipeline_freshness": f"""
SELECT {c.get('pipeline_id','id')}, {c.get('pipeline_name','name')}, max({c.get('started_at','started_at')}) as last_run
FROM {qualified}
GROUP BY {c.get('pipeline_id','id')}, {c.get('pipeline_name','name')}
HAVING max({c.get('started_at','started_at')}) < now() - INTERVAL 60 MINUTE
ORDER BY last_run ASC""",
        }

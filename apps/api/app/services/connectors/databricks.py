"""Databricks database connector with auto-discovery.

Connects via Databricks SQL Warehouse (HTTP endpoint) or ODBC.
Config:
  host = workspace URL (e.g. https://dbc-xxx.cloud.databricks.com)
  extra.token = personal access token
  extra.http_path = SQL warehouse HTTP path (e.g. /sql/1.0/warehouses/xxx)
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from apps.api.app.services.connectors.base import DatabaseConnector, ConnectorConfig

logger = logging.getLogger(__name__)


class DatabricksConnector(DatabaseConnector):
    """Databricks connector via SQL Warehouse HTTP API."""

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        host = config.host.rstrip("/")
        # Fix common typos: httpds:// → https://
        if host.startswith("httpds://"):
            host = "https://" + host[len("httpds://"):]
        elif not host.startswith("http"):
            host = "https://" + host
        self._host = host
        self._token = config.extra.get("token", config.password)
        self._http_path = config.extra.get("http_path", "")

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    async def connect(self) -> bool:
        try:
            url = f"{self._host}/api/2.0/sql/statements/"
            logger.info("Connecting to Databricks: %s", url)
            async with httpx.AsyncClient(timeout=30, verify=True) as client:
                resp = await client.post(
                    url,
                    headers=self._headers,
                    json={
                        "statement": "SELECT 1",
                        "warehouse_id": self._http_path.split("/")[-1] if self._http_path else "",
                    },
                )
                logger.info("Databricks response: %d %s", resp.status_code, resp.text[:200])
                if resp.status_code in (200, 400):
                    logger.info("Connected to Databricks: %s", self._host)
                    return True
                # Parse Databricks error message
                try:
                    err = resp.json()
                    msg = err.get("message", resp.text[:200])
                except Exception:
                    msg = resp.text[:200]
                logger.warning("Databricks connect failed: %d %s", resp.status_code, msg)
                # Store error message for caller
                self._last_error = f"HTTP {resp.status_code}: {msg}"
                return False
        except httpx.ConnectError as e:
            logger.error("Databricks connection error (check network/URL): %s", e)
            self._last_error = f"Connection refused: {e}"
            return False
        except httpx.TimeoutException:
            logger.error("Databricks connection timed out (30s)")
            self._last_error = "Connection timed out after 30s"
            return False
        except Exception as e:
            logger.error("Databricks connection failed: %s", type(e).__name__, e)
            self._last_error = str(e)
            return False
        except Exception as e:
            logger.error("Databricks connection failed: %s", e)
            return False

    async def disconnect(self) -> None:
        pass  # HTTP, no persistent connection

    async def _query(self, sql: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self._host}/api/2.0/sql/statements/",
                headers=self._headers,
                json={
                    "statement": sql,
                    "warehouse_id": self._http_path.split("/")[-1] if self._http_path else "",
                    "catalog": self.config.database,
                },
            )
            if resp.status_code != 200:
                logger.warning("Databricks query failed: %s", resp.text[:300])
                return []
            data = resp.json()
            manifest = data.get("result", {}).get("data_array", [])
            columns = [col["name"].lower() for col in data.get("result", {}).get("manifest", {}).get("columns", [])]
            if not columns and manifest:
                # Fallback: use first row indices
                return manifest
            return [dict(zip(columns, row)) for row in manifest]

    async def _query_val(self, sql: str) -> Any:
        rows = await self._query(sql)
        if rows:
            return list(rows[0].values())[0]
        return None

    async def list_tables(self, schema: str | None = None) -> list[str]:
        schema = schema or "default"
        rows = await self._query(f"SHOW TABLES IN SCHEMA {self.config.database}.{schema}")
        return [r.get("tableName", r.get("table_name", "")) for r in rows]

    async def describe_table(self, table: str, schema: str | None = None) -> list[dict]:
        schema = schema or "default"
        rows = await self._query(f"DESCRIBE TABLE {self.config.database}.{schema}.{table}")
        return [{"name": r.get("col_name", r.get("name", "")), "type": r.get("data_type", r.get("type", "")), "nullable": True} for r in rows]

    async def execute_query(self, sql: str) -> list[dict]:
        return await self._query(sql)

    async def count_rows(self, table: str, schema: str | None = None) -> int:
        schema = schema or "default"
        result = await self._query_val(f"SELECT COUNT(*) FROM {self.config.database}.{schema}.{table}")
        return result or 0

    def build_monitoring_queries(self, mapping: "TableMapping") -> dict[str, str]:
        """Databricks SQL syntax (Spark SQL)."""
        if mapping.table_type != "pipeline":
            return super().build_monitoring_queries(mapping)

        c = mapping.columns
        table = mapping.table_name
        schema = self.config.schema or "default"
        qualified = f"{self.config.database}.{schema}.{table}"
        failed_vals = "','".join(self.STATUS_FAILED_VALUES)

        return {
            "pipeline_failures": f"""
SELECT {c.get('pipeline_id','id')}, {c.get('pipeline_name','name')}, {c.get('status','status')}, {c.get('started_at','started_at')}, {c.get('error_message','error_message')}
FROM {qualified}
WHERE {c.get('status','status')} IN ('{failed_vals}')
AND {c.get('started_at','started_at')} >= CURRENT_TIMESTAMP() - INTERVAL 1 HOUR
ORDER BY {c.get('started_at','started_at')} DESC LIMIT 20""",
            "pipeline_freshness": f"""
SELECT {c.get('pipeline_id','id')}, {c.get('pipeline_name','name')}, MAX({c.get('started_at','started_at')}) as last_run
FROM {qualified}
GROUP BY {c.get('pipeline_id','id')}, {c.get('pipeline_name','name')}
HAVING MAX({c.get('started_at','started_at')}) < CURRENT_TIMESTAMP() - INTERVAL 1 HOUR
ORDER BY last_run ASC""",
        }

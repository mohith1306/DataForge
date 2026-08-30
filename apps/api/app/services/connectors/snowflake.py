"""Snowflake database connector with auto-discovery."""

from __future__ import annotations

import logging
from typing import Any

from apps.api.app.services.connectors.base import DatabaseConnector, ConnectorConfig

logger = logging.getLogger(__name__)


class SnowflakeConnector(DatabaseConnector):
    """Snowflake connector using snowflake-connector-python async wrapper."""

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self._connection = None

    async def connect(self) -> bool:
        try:
            import snowflake.connector

            # Strip .snowflakecomputing.com from account if user provided full URL
            account = self.config.host
            if ".snowflakecomputing.com" in account:
                account = account.split(".snowflakecomputing.com")[0]

            self._connection = snowflake.connector.connect(
                account=account,
                user=self.config.username,
                password=self.config.password,
                database=self.config.database,
                schema=self.config.schema or "PUBLIC",
                warehouse=self.config.extra.get("warehouse", "COMPUTE_WH"),
                role=self.config.extra.get("role", "SYSADMIN"),
                login_timeout=15,
            )
            # Test
            cursor = self._connection.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            logger.info("Connected to Snowflake: %s/%s", self.config.host, self.config.database)
            return True
        except ImportError as e:
            msg = "snowflake-connector-python not installed. Run: pip install snowflake-connector-python"
            logger.error(msg)
            self._last_error = msg
            return False
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            logger.error("Snowflake connection failed: %s", msg)
            self._last_error = msg
            return False

    async def disconnect(self) -> None:
        if self._connection:
            self._connection.close()
            self._connection = None

    def _execute_sync(self, sql: str) -> list[dict]:
        if not self._connection:
            raise RuntimeError("Not connected")
        cursor = self._connection.cursor()
        cursor.execute(sql)
        columns = [desc[0].lower() for desc in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        cursor.close()
        return [dict(zip(columns, row)) for row in rows]

    def _execute_val_sync(self, sql: str) -> Any:
        rows = self._execute_sync(sql)
        if rows:
            return list(rows[0].values())[0]
        return None

    async def list_tables(self, schema: str | None = None) -> list[str]:
        schema = schema or self.config.schema or "PUBLIC"
        rows = self._execute_sync(
            f"SHOW TABLES IN SCHEMA {self.config.database}.{schema}"
        )
        # Snowflake SHOW returns 'name' column
        return [r.get("name", r.get("Name", "")) for r in rows]

    async def describe_table(self, table: str, schema: str | None = None) -> list[dict]:
        schema = schema or self.config.schema or "PUBLIC"
        rows = self._execute_sync(
            f"DESCRIBE TABLE {self.config.database}.{schema}.{table}"
        )
        # Snowflake DESCRIBE returns 'name', 'type', etc.
        return [{"name": r.get("name", ""), "type": r.get("type", ""), "nullable": "Y" in str(r.get("null?", ""))} for r in rows]

    async def execute_query(self, sql: str) -> list[dict]:
        return self._execute_sync(sql)

    async def count_rows(self, table: str, schema: str | None = None) -> int:
        schema = schema or self.config.schema or "PUBLIC"
        return self._execute_val_sync(f"SELECT COUNT(*) FROM {self.config.database}.{schema}.{table}") or 0

    def build_monitoring_queries(self, mapping: "TableMapping") -> dict[str, str]:
        """Snowflake-specific SQL syntax."""
        if mapping.table_type != "pipeline":
            return super().build_monitoring_queries(mapping)

        c = mapping.columns
        table = mapping.table_name
        schema = self.config.schema or "PUBLIC"
        qualified = f"{self.config.database}.{schema}.{table}"
        failed_vals = "','".join(self.STATUS_FAILED_VALUES)

        return {
            "pipeline_failures": f"""
SELECT {c.get('pipeline_id','id')}, {c.get('pipeline_name','name')}, {c.get('status','status')}, {c.get('started_at','started_at')}, {c.get('error_message','error_message')}
FROM {qualified}
WHERE {c.get('status','status')} IN ('{failed_vals}')
AND {c.get('started_at','started_at')} >= DATEADD(hour, -1, CURRENT_TIMESTAMP())
ORDER BY {c.get('started_at','started_at')} DESC LIMIT 20""",
            "pipeline_freshness": f"""
SELECT {c.get('pipeline_id','id')}, {c.get('pipeline_name','name')}, MAX({c.get('started_at','started_at')}) as last_run
FROM {qualified}
GROUP BY {c.get('pipeline_id','id')}, {c.get('pipeline_name','name')}
HAVING MAX({c.get('started_at','started_at')}) < DATEADD(hour, -1, CURRENT_TIMESTAMP())
ORDER BY last_run ASC""",
        }

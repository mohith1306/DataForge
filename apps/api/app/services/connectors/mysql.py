"""MySQL database connector with auto-discovery."""

from __future__ import annotations

import logging
from typing import Any

from apps.api.app.services.connectors.base import DatabaseConnector, ConnectorConfig

logger = logging.getLogger(__name__)


class MySQLConnector(DatabaseConnector):
    """MySQL connector using aiomysql."""

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self._pool = None

    async def connect(self) -> bool:
        try:
            import aiomysql
            self._pool = await aiomysql.create_pool(
                host=self.config.host,
                port=self.config.port or 3306,
                user=self.config.username,
                password=self.config.password,
                db=self.config.database,
                minsize=1,
                maxsize=5,
                connect_timeout=10,
            )
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT 1")
            logger.info("Connected to MySQL: %s/%s", self.config.host, self.config.database)
            return True
        except Exception as e:
            logger.error("MySQL connection failed: %s", e)
            return False

    async def disconnect(self) -> None:
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None

    async def _execute(self, sql: str) -> list[dict]:
        if not self._pool:
            await self.connect()
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql)
                columns = [desc[0] for desc in cur.description] if cur.description else []
                rows = await cur.fetchall()
                return [dict(zip(columns, row)) for row in rows]

    async def _execute_val(self, sql: str) -> Any:
        if not self._pool:
            await self.connect()
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql)
                row = await cur.fetchone()
                return row[0] if row else None

    async def list_tables(self, schema: str | None = None) -> list[str]:
        schema = schema or self.config.database
        rows = await self._execute(
            f"SELECT table_name FROM information_schema.tables "
            f"WHERE table_schema = '{schema}' AND table_type = 'BASE TABLE' "
            f"ORDER BY table_name"
        )
        return [r["table_name"] for r in rows]

    async def describe_table(self, table: str, schema: str | None = None) -> list[dict]:
        schema = schema or self.config.database
        rows = await self._execute(
            f"SELECT column_name as name, data_type as type, "
            f"is_nullable as nullable "
            f"FROM information_schema.columns "
            f"WHERE table_schema = '{schema}' AND table_name = '{table}' "
            f"ORDER BY ordinal_position"
        )
        return rows

    async def execute_query(self, sql: str) -> list[dict]:
        return await self._execute(sql)

    async def count_rows(self, table: str, schema: str | None = None) -> int:
        schema = schema or self.config.database
        result = await self._execute_val(f"SELECT COUNT(*) FROM `{schema}`.`{table}`")
        return result or 0

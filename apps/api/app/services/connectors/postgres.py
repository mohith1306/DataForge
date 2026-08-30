"""PostgreSQL database connector with auto-discovery."""

from __future__ import annotations

import logging
from typing import Any

from apps.api.app.services.connectors.base import DatabaseConnector, ConnectorConfig

logger = logging.getLogger(__name__)


class PostgresConnector(DatabaseConnector):
    """PostgreSQL connector using asyncpg."""

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self._pool = None

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://{self.config.username}:{self.config.password}"
            f"@{self.config.host}:{self.config.port}/{self.config.database}"
        )

    async def connect(self) -> bool:
        try:
            import asyncpg
            self._pool = await asyncpg.create_pool(
                self.dsn,
                min_size=1,
                max_size=5,
                command_timeout=10,
            )
            # Test connection
            async with self._pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            logger.info("Connected to PostgreSQL: %s/%s", self.config.host, self.config.database)
            return True
        except Exception as e:
            logger.error("PostgreSQL connection failed: %s", e)
            return False

    async def disconnect(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def _execute(self, sql: str) -> list[dict]:
        if not self._pool:
            await self.connect()
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql)
            return [dict(r) for r in rows]

    async def _execute_val(self, sql: str) -> Any:
        if not self._pool:
            await self.connect()
        async with self._pool.acquire() as conn:
            return await conn.fetchval(sql)

    async def list_tables(self, schema: str | None = None) -> list[str]:
        schema = schema or self.config.schema or "public"
        rows = await self._execute(
            f"SELECT table_name FROM information_schema.tables "
            f"WHERE table_schema = '{schema}' AND table_type = 'BASE TABLE' "
            f"ORDER BY table_name"
        )
        return [r["table_name"] for r in rows]

    async def describe_table(self, table: str, schema: str | None = None) -> list[dict]:
        schema = schema or self.config.schema or "public"
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
        schema = schema or self.config.schema or "public"
        return await self._execute_val(f"SELECT COUNT(*) FROM {schema}.{table}")

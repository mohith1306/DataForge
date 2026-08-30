"""Base connector interface for database monitoring.

Each connector knows how to:
1. Connect to a specific database type
2. Auto-discover pipeline-related tables
3. Infer column mappings from naming patterns
4. Run monitoring queries
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TableMapping:
    """Discovered mapping for one table."""
    table_name: str
    table_type: str  # "pipeline" | "quality" | "unknown"
    columns: dict[str, str]  # logical_name → actual_column
    row_count: int = 0
    confidence: float = 0.0  # how sure we are this is a pipeline table


@dataclass
class ConnectorConfig:
    """Stored configuration for a database connector."""
    id: str = ""
    name: str = ""
    db_type: str = ""  # postgres | mysql | clickhouse | bigquery | snowflake
    host: str = ""
    port: int = 0
    database: str = ""
    username: str = ""
    password: str = ""  # stored encrypted in production
    schema: str = "public"
    extra: dict[str, str] = field(default_factory=dict)  # driver-specific options
    enabled: bool = True
    poll_interval: int = 30  # seconds between monitoring checks
    discovered_tables: list[dict] = field(default_factory=list)


class DatabaseConnector(ABC):
    """Abstract base class for database connectors."""

    def __init__(self, config: ConnectorConfig):
        self.config = config
        self._connection = None

    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection. Returns True if successful."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection."""
        ...

    @abstractmethod
    async def list_tables(self, schema: str | None = None) -> list[str]:
        """List all tables in the database."""
        ...

    @abstractmethod
    async def describe_table(self, table: str, schema: str | None = None) -> list[dict]:
        """Return column info: [{"name": ..., "type": ..., "nullable": ...}]"""
        ...

    @abstractmethod
    async def execute_query(self, sql: str) -> list[dict]:
        """Run a read-only query and return rows."""
        ...

    @abstractmethod
    async def count_rows(self, table: str, schema: str | None = None) -> int:
        """Return row count for a table."""
        ...

    # ── Auto-discovery ────────────────────────────────────────────────────────

    # Keywords that suggest a table contains pipeline/ETL run data
    PIPELINE_TABLE_KEYWORDS = [
        "pipeline", "etl", "job", "run", "task", "workflow",
        "dag", "airflow", "spark", "batch", "ingest", "load",
    ]

    # Keywords that suggest a table contains data quality metrics
    QUALITY_TABLE_KEYWORDS = [
        "quality", "dq", "check", "validation", "metric", "monitor",
        "anomaly", "alert", "rule",
    ]

    # Column name patterns → logical names
    COLUMN_PATTERNS = {
        "pipeline_id": ["pipeline_id", "job_id", "task_id", "run_id", "dag_id", "id"],
        "pipeline_name": ["pipeline_name", "job_name", "task_name", "dag_name", "name"],
        "status": ["status", "state", "result", "run_status", "outcome"],
        "started_at": ["started_at", "start_time", "created_at", "run_start", "begin_time", "started"],
        "error_message": ["error_message", "error", "error_detail", "message", "fail_reason", "exception"],
        "rows_processed": ["rows_processed", "row_count", "records", "count", "rows"],
    }

    QUALITY_COLUMN_PATTERNS = {
        "null_check_column": ["region", "customer_region", "category", "type", "source"],
    }

    STATUS_FAILED_VALUES = ["FAILED", "failed", "ERROR", "error", "FAILURE", "failure", "0"]
    STATUS_SUCCESS_VALUES = ["SUCCESS", "success", "OK", "ok", "COMPLETED", "completed", "1"]

    async def auto_discover(self) -> list[TableMapping]:
        """Auto-discover pipeline and quality tables."""
        mappings = []
        try:
            tables = await self.list_tables(self.config.schema)
            logger.info("Found %d tables in %s", len(tables), self.config.database)

            for table in tables:
                mapping = await self._analyze_table(table)
                if mapping and mapping.confidence > 0.3:
                    mappings.append(mapping)
                    logger.info(
                        "Discovered %s table: %s (confidence=%.2f)",
                        mapping.table_type, table, mapping.confidence,
                    )
        except Exception as e:
            logger.error("Auto-discovery failed: %s", e)

        return mappings

    async def _analyze_table(self, table: str) -> TableMapping | None:
        """Analyze a table to determine if it's pipeline/quality data."""
        try:
            columns = await self.describe_table(table, self.config.schema)
            if not columns:
                return None

            col_names = [c["name"].lower() for c in columns]
            table_lower = table.lower()

            # Score as pipeline table
            pipeline_score = 0.0
            for keyword in self.PIPELINE_TABLE_KEYWORDS:
                if keyword in table_lower:
                    pipeline_score += 0.3
                    break

            # Score based on column matches
            matched_columns = {}
            for logical, patterns in self.COLUMN_PATTERNS.items():
                for pattern in patterns:
                    if pattern.lower() in col_names:
                        matched_columns[logical] = pattern
                        pipeline_score += 0.1
                        break

            # Must have at least status + started_at to be useful
            has_minimum = "status" in matched_columns and "started_at" in matched_columns

            if pipeline_score >= 0.4 and has_minimum:
                row_count = await self.count_rows(table, self.config.schema)
                return TableMapping(
                    table_name=table,
                    table_type="pipeline",
                    columns=matched_columns,
                    row_count=row_count,
                    confidence=min(pipeline_score, 1.0),
                )

            # Score as quality table
            quality_score = 0.0
            for keyword in self.QUALITY_TABLE_KEYWORDS:
                if keyword in table_lower:
                    quality_score += 0.4
                    break

            if quality_score >= 0.4:
                row_count = await self.count_rows(table, self.config.schema)
                quality_columns = {}
                for logical, patterns in self.QUALITY_COLUMN_PATTERNS.items():
                    for pattern in patterns:
                        if pattern.lower() in col_names:
                            quality_columns[logical] = pattern
                            break
                if quality_columns:
                    return TableMapping(
                        table_name=table,
                        table_type="quality",
                        columns=quality_columns,
                        row_count=row_count,
                        confidence=min(quality_score, 1.0),
                    )

        except Exception as e:
            logger.debug("Could not analyze table %s: %s", table, e)

        return None

    def build_monitoring_queries(self, mapping: TableMapping) -> dict[str, str]:
        """Build monitoring SQL queries from a discovered mapping."""
        if mapping.table_type == "pipeline":
            return self._build_pipeline_queries(mapping)
        elif mapping.table_type == "quality":
            return self._build_quality_queries(mapping)
        return {}

    def _build_pipeline_queries(self, m: TableMapping) -> dict[str, str]:
        c = m.columns
        table = m.table_name
        schema = self.config.schema
        qualified = f"{schema}.{table}" if schema else table

        failed_pattern = "|".join(self.STATUS_FAILED_VALUES)

        return {
            "pipeline_failures": f"""
SELECT {c.get('pipeline_id','id')}, {c.get('pipeline_name','name')}, {c.get('status','status')}, {c.get('started_at','started_at')}, {c.get('error_message','error_message')}
FROM {qualified}
WHERE {c.get('status','status')} IN ('{ "','".join(self.STATUS_FAILED_VALUES) }')
AND {c.get('started_at','started_at')} >= NOW() - INTERVAL '1 hour'
ORDER BY {c.get('started_at','started_at')} DESC LIMIT 20""",
            "pipeline_freshness": f"""
SELECT {c.get('pipeline_id','id')}, {c.get('pipeline_name','name')}, MAX({c.get('started_at','started_at')}) as last_run
FROM {qualified}
GROUP BY {c.get('pipeline_id','id')}, {c.get('pipeline_name','name')}
HAVING MAX({c.get('started_at','started_at')}) < NOW() - INTERVAL '60 minutes'
ORDER BY last_run ASC""",
        }

    def _build_quality_queries(self, m: TableMapping) -> dict[str, str]:
        c = m.columns
        table = m.table_name
        schema = self.config.schema
        qualified = f"{schema}.{table}" if schema else table
        null_col = c.get("null_check_column", "")

        if null_col:
            return {
                "data_quality": f"""
SELECT COUNT(*) FILTER (WHERE {null_col} IS NULL) as nulls, COUNT(*) as total
FROM {qualified}"""
            }
        return {}

    def to_dict(self) -> dict:
        d = asdict(self.config)
        d.pop("password", None)
        return d

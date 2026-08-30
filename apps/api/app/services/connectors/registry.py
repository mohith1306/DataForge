"""Connector registry — stores credentials, manages connections, runs monitoring."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from apps.api.app.services.connectors.base import (
    ConnectorConfig,
    DatabaseConnector,
    TableMapping,
)

logger = logging.getLogger(__name__)

CONFIG_DIR = Path("data")
CONNECTORS_FILE = CONFIG_DIR / "connectors.json"


def _get_connector_class(db_type: str) -> type[DatabaseConnector]:
    if db_type == "postgres":
        from apps.api.app.services.connectors.postgres import PostgresConnector
        return PostgresConnector
    elif db_type == "mysql":
        from apps.api.app.services.connectors.mysql import MySQLConnector
        return MySQLConnector
    elif db_type == "clickhouse":
        from apps.api.app.services.connectors.clickhouse import ClickHouseConnector
        return ClickHouseConnector
    elif db_type == "snowflake":
        from apps.api.app.services.connectors.snowflake import SnowflakeConnector
        return SnowflakeConnector
    elif db_type == "databricks":
        from apps.api.app.services.connectors.databricks import DatabricksConnector
        return DatabricksConnector
    else:
        raise ValueError(f"Unsupported database type: {db_type}")


class ConnectorRegistry:
    """Manages database connectors, credentials, and monitoring schedules."""

    def __init__(self):
        self._connectors: dict[str, DatabaseConnector] = {}
        self._configs: dict[str, ConnectorConfig] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._load()

    def _load(self) -> None:
        """Load saved connector configs from disk."""
        if CONNECTORS_FILE.exists():
            try:
                data = json.loads(CONNECTORS_FILE.read_text())
                for cid, cdata in data.items():
                    config = ConnectorConfig(**cdata)
                    self._configs[cid] = config
                logger.info("Loaded %d connector configs", len(self._configs))
            except Exception as e:
                logger.error("Failed to load connectors: %s", e)

    def _save(self) -> None:
        """Persist connector configs to disk."""
        CONFIG_DIR.mkdir(exist_ok=True)
        data = {}
        for cid, config in self._configs.items():
            d = {
                "id": config.id,
                "name": config.name,
                "db_type": config.db_type,
                "host": config.host,
                "port": config.port,
                "database": config.database,
                "username": config.username,
                "password": config.password,
                "schema": config.schema,
                "extra": config.extra,
                "enabled": config.enabled,
                "poll_interval": config.poll_interval,
                "discovered_tables": config.discovered_tables,
            }
            data[cid] = d
        CONNECTORS_FILE.write_text(json.dumps(data, indent=2))
        logger.info("Saved %d connector configs", len(data))

    async def add_connector(self, config: ConnectorConfig) -> dict:
        """Add a new connector: connect, discover schema, save."""
        # Create connector
        cls = _get_connector_class(config.db_type)
        connector = cls(config)

        # Test connection
        connected = await connector.connect()
        if not connected:
            host = getattr(connector, '_host', config.host)
            err = getattr(connector, '_last_error', 'unknown error')
            return {"status": "error", "message": f"Could not connect to {config.db_type} at {host}: {err}"}

        # Auto-discover tables
        try:
            mappings = await connector.auto_discover()
            config.discovered_tables = [
                {
                    "table": m.table_name,
                    "type": m.table_type,
                    "columns": m.columns,
                    "row_count": m.row_count,
                    "confidence": m.confidence,
                }
                for m in mappings
            ]
        except Exception as e:
            logger.warning("Auto-discovery failed for %s: %s", config.name, e)
            config.discovered_tables = []

        # Generate monitoring queries
        queries = {}
        for m in mappings:
            q = connector.build_monitoring_queries(m)
            queries.update(q)

        # Store
        self._configs[config.id] = config
        self._connectors[config.id] = connector
        self._save()

        return {
            "status": "success",
            "connector_id": config.id,
            "discovered_tables": config.discovered_tables,
            "monitoring_queries": queries,
        }

    async def remove_connector(self, connector_id: str) -> bool:
        """Remove a connector and stop its monitoring."""
        if connector_id in self._tasks:
            self._tasks[connector_id].cancel()
            del self._tasks[connector_id]

        if connector_id in self._connectors:
            await self._connectors[connector_id].disconnect()
            del self._connectors[connector_id]

        if connector_id in self._configs:
            del self._configs[connector_id]
            self._save()

        return True

    def list_connectors(self) -> list[dict]:
        """List all connectors (without passwords)."""
        result = []
        for cid, config in self._configs.items():
            d = {
                "id": cid,
                "name": config.name,
                "db_type": config.db_type,
                "host": config.host,
                "port": config.port,
                "database": config.database,
                "enabled": config.enabled,
                "poll_interval": config.poll_interval,
                "discovered_tables": config.discovered_tables,
                "monitoring": cid in self._tasks and not self._tasks[cid].done(),
            }
            result.append(d)
        return result

    async def test_connection(self, connector_id: str) -> dict:
        """Test a connector's connection."""
        connector = self._connectors.get(connector_id)
        if not connector:
            config = self._configs.get(connector_id)
            if not config:
                return {"status": "error", "message": "Connector not found"}
            cls = _get_connector_class(config.db_type)
            connector = cls(config)

        connected = await connector.connect()
        if not connected:
            return {"status": "error", "message": "Connection failed"}

        try:
            tables = await connector.list_tables()
            return {"status": "connected", "tables": len(tables), "sample": tables[:10]}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def run_monitoring_check(self, connector_id: str) -> dict:
        """Run a single monitoring check for a connector."""
        connector = self._connectors.get(connector_id)
        if not connector:
            return {"status": "error", "message": "Connector not found"}

        config = self._configs.get(connector_id)
        if not config or not config.enabled:
            return {"status": "skipped", "message": "Connector disabled"}

        results = {
            "connector": config.name,
            "failures": [],
            "stale": [],
            "quality_issues": [],
        }

        try:
            # Build and run queries from discovered tables
            for table_info in config.discovered_tables:
                mapping = TableMapping(
                    table_name=table_info["table"],
                    table_type=table_info["type"],
                    columns=table_info["columns"],
                    row_count=table_info.get("row_count", 0),
                    confidence=table_info.get("confidence", 0),
                )
                queries = connector.build_monitoring_queries(mapping)

                for check_name, sql in queries.items():
                    try:
                        rows = await connector.execute_query(sql)
                        if rows:
                            if "fail" in check_name:
                                results["failures"].extend(rows)
                            elif "fresh" in check_name:
                                results["stale"].extend(rows)
                            elif "quality" in check_name:
                                results["quality_issues"].extend(rows)
                    except Exception as e:
                        logger.warning("Query %s failed: %s", check_name, e)

        except Exception as e:
            logger.error("Monitoring check failed for %s: %s", connector_id, e)
            return {"status": "error", "message": str(e)}

        return results

    async def start_monitoring(self, connector_id: str) -> None:
        """Start background monitoring for a connector."""
        if connector_id in self._tasks and not self._tasks[connector_id].done():
            return  # Already running

        async def _monitor_loop():
            config = self._configs.get(connector_id)
            if not config:
                return
            interval = config.poll_interval or 30
            while True:
                try:
                    results = await self.run_monitoring_check(connector_id)
                    # Create incidents for detected issues
                    await self._handle_results(connector_id, results)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error("Monitor loop error for %s: %s", connector_id, e)
                await asyncio.sleep(interval)

        self._tasks[connector_id] = asyncio.create_task(_monitor_loop())
        logger.info("Started monitoring for %s (every %ds)", connector_id,
                     self._configs[connector_id].poll_interval)

    async def stop_monitoring(self, connector_id: str) -> None:
        """Stop background monitoring for a connector."""
        if connector_id in self._tasks:
            self._tasks[connector_id].cancel()
            del self._tasks[connector_id]

    async def _handle_results(self, connector_id: str, results: dict) -> None:
        """Create incidents from monitoring results."""
        from apps.api.app.services.monitor import _create_incident, _start_investigation
        from apps.api.app.core.config import settings

        for failure in results.get("failures", []):
            inc_id = await _create_incident(
                title=f"Pipeline {failure.get('pipeline_name', failure.get('pipeline_id', '?'))} Failed",
                description=(
                    f"Connector: {results['connector']}\n"
                    f"Pipeline {failure.get('pipeline_name', '?')} failed.\n"
                    f"Error: {failure.get('error_message', 'unknown')}"
                ),
                severity="high",
                incident_type="pipeline_failure",
            )
            if inc_id and settings.trueforge_enabled:
                await _start_investigation(inc_id)

        for stale in results.get("stale", []):
            inc_id = await _create_incident(
                title=f"Pipeline {stale.get('pipeline_name', stale.get('pipeline_id', '?'))} Stale",
                description=(
                    f"Connector: {results['connector']}\n"
                    f"Pipeline {stale.get('pipeline_name', '?')} last ran at {stale.get('last_run', '?')}"
                ),
                severity="medium",
                incident_type="freshness_lag",
            )
            if inc_id and settings.trueforge_enabled:
                await _start_investigation(inc_id)

        for dq in results.get("quality_issues", []):
            nulls = dq.get("nulls", 0)
            total = dq.get("total", 1)
            rate = nulls / total if total > 0 else 0
            if rate > 0.05:
                inc_id = await _create_incident(
                    title=f"Data Quality: {dq.get('table', '?')}.{dq.get('column', '?')} null rate {rate:.1%}",
                    description=(
                        f"Connector: {results['connector']}\n"
                        f"Null rate {rate:.1%} exceeds 5% threshold "
                        f"({nulls}/{total} rows)"
                    ),
                    severity="medium",
                    incident_type="data_quality",
                )
                if inc_id and settings.trueforge_enabled:
                    await _start_investigation(inc_id)


# Singleton
registry = ConnectorRegistry()

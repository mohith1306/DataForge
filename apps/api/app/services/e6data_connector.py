"""e6data Connector — integrates with e6data query engine and ingest pipeline.

Consumes telemetry from e6data:
- Query failures, latency, resource usage
- Ingestion failures, CDC issues, schema changes
- Freshness, throughput anomalies
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class TelemetryType(str, Enum):
    QUERY_FAILURE = "query_failure"
    QUERY_LATENCY = "query_latency"
    QUERY_RESOURCE = "query_resource"
    INGEST_FAILURE = "ingest_failure"
    CDC_ISSUE = "cdc_issue"
    SCHEMA_CHANGE = "schema_change"
    FRESHNESS_ANOMALY = "freshness_anomaly"
    THROUGHPUT_ANOMALY = "throughput_anomaly"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class QueryTelemetry:
    """Query execution telemetry from e6data."""
    query_id: str
    query_text: str
    status: str
    duration_ms: float = 0.0
    rows_returned: int = 0
    rows_scanned: int = 0
    tables_scanned: list[str] = field(default_factory=list)
    error_message: str = ""
    started_at: str = ""
    completed_at: str = ""

    def to_dict(self) -> dict:
        return {
            "query_id": self.query_id,
            "query_text": self.query_text[:500],
            "status": self.status,
            "duration_ms": self.duration_ms,
            "rows_returned": self.rows_returned,
            "rows_scanned": self.rows_scanned,
            "tables_scanned": self.tables_scanned,
            "error_message": self.error_message,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


@dataclass
class IngestTelemetry:
    """Ingestion pipeline telemetry from e6data."""
    pipeline_id: str
    pipeline_name: str
    status: str
    records_processed: int = 0
    records_failed: int = 0
    throughput_rps: float = 0.0
    lag_seconds: float = 0.0
    schema_version: str = ""
    error_message: str = ""
    started_at: str = ""
    completed_at: str = ""

    def to_dict(self) -> dict:
        return {
            "pipeline_id": self.pipeline_id,
            "pipeline_name": self.pipeline_name,
            "status": self.status,
            "records_processed": self.records_processed,
            "records_failed": self.records_failed,
            "throughput_rps": self.throughput_rps,
            "lag_seconds": self.lag_seconds,
            "schema_version": self.schema_version,
            "error_message": self.error_message,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


@dataclass
class TelemetryEvent:
    """A telemetry event from e6data."""
    event_id: str
    event_type: TelemetryType
    severity: Severity
    source: str
    resource_id: str
    resource_type: str
    message: str
    metadata: dict = field(default_factory=dict)
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "source": self.source,
            "resource_id": self.resource_id,
            "resource_type": self.resource_type,
            "message": self.message,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


class E6DataConnector:
    """Connector for e6data query engine and ingest pipeline."""

    def __init__(self, base_url: str = "", api_key: str = ""):
        self.base_url = base_url
        self.api_key = api_key
        self.query_telemetry: list[QueryTelemetry] = []
        self.ingest_telemetry: list[IngestTelemetry] = []
        self.telemetry_events: list[TelemetryEvent] = []

    async def get_query_telemetry(
        self,
        time_range_minutes: int = 60,
        status_filter: str = "",
    ) -> list[QueryTelemetry]:
        """Fetch query telemetry from e6data."""
        results = []
        for qt in self.query_telemetry:
            if status_filter and qt.status != status_filter:
                continue
            results.append(qt)
        return results

    async def get_ingest_telemetry(
        self,
        time_range_minutes: int = 60,
        status_filter: str = "",
    ) -> list[IngestTelemetry]:
        """Fetch ingest telemetry from e6data."""
        results = []
        for it in self.ingest_telemetry:
            if status_filter and it.status != status_filter:
                continue
            results.append(it)
        return results

    async def ingest_query_event(self, event: QueryTelemetry) -> TelemetryEvent:
        """Process a query telemetry event and return a standardized event."""
        severity = Severity.LOW
        if event.status == "FAILED":
            severity = Severity.HIGH
        elif event.duration_ms > 30000:
            severity = Severity.MEDIUM
        elif event.duration_ms > 60000:
            severity = Severity.HIGH

        telemetry_event = TelemetryEvent(
            event_id=f"q-{event.query_id}",
            event_type=TelemetryType.QUERY_FAILURE if event.status == "FAILED" else TelemetryType.QUERY_LATENCY,
            severity=severity,
            source="e6data-query-engine",
            resource_id=event.query_id,
            resource_type="query",
            message=event.error_message or f"Query completed in {event.duration_ms}ms",
            metadata={
                "duration_ms": event.duration_ms,
                "rows_returned": event.rows_returned,
                "tables_scanned": event.tables_scanned,
            },
            timestamp=event.completed_at or datetime.now(timezone.utc).isoformat(),
        )
        self.telemetry_events.append(telemetry_event)
        return telemetry_event

    async def ingest_pipeline_event(self, event: IngestTelemetry) -> TelemetryEvent:
        """Process an ingest pipeline event and return a standardized event."""
        severity = Severity.LOW
        if event.status == "FAILED":
            severity = Severity.HIGH
        elif event.records_failed > 0:
            severity = Severity.MEDIUM
        elif event.lag_seconds > 300:
            severity = Severity.HIGH

        telemetry_event = TelemetryEvent(
            event_id=f"i-{event.pipeline_id}",
            event_type=TelemetryType.INGEST_FAILURE if event.status == "FAILED" else TelemetryType.FRESHNESS_ANOMALY,
            severity=severity,
            source="e6data-ingest-pipeline",
            resource_id=event.pipeline_id,
            resource_type="pipeline",
            message=event.error_message or f"Pipeline {event.pipeline_name}: {event.status}",
            metadata={
                "pipeline_name": event.pipeline_name,
                "records_processed": event.records_processed,
                "records_failed": event.records_failed,
                "lag_seconds": event.lag_seconds,
                "throughput_rps": event.throughput_rps,
            },
            timestamp=event.completed_at or datetime.now(timezone.utc).isoformat(),
        )
        self.telemetry_events.append(telemetry_event)
        return telemetry_event

    def get_anomalies(
        self,
        time_range_minutes: int = 60,
        min_severity: Severity = Severity.MEDIUM,
    ) -> list[TelemetryEvent]:
        """Get telemetry events above a severity threshold."""
        severity_order = {
            Severity.LOW: 0,
            Severity.MEDIUM: 1,
            Severity.HIGH: 2,
            Severity.CRITICAL: 3,
        }
        min_level = severity_order.get(min_severity, 0)
        return [
            e for e in self.telemetry_events
            if severity_order.get(e.severity, 0) >= min_level
        ]

    def get_resource_health(self, resource_id: str) -> dict:
        """Get health status for a specific resource."""
        events = [e for e in self.telemetry_events if e.resource_id == resource_id]
        if not events:
            return {"resource_id": resource_id, "status": "healthy", "event_count": 0}

        failed = [e for e in events if e.severity in (Severity.HIGH, Severity.CRITICAL)]
        return {
            "resource_id": resource_id,
            "status": "degraded" if failed else "healthy",
            "event_count": len(events),
            "failed_count": len(failed),
            "latest_event": events[-1].to_dict() if events else None,
        }

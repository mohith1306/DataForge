"""Observability — metrics and tracing for DataForge itself.

Tracks:
- API latency
- Agent latency and failures
- Connector health
- Execution failures
- Verification failures
- Graph query latency
- Database health
- Incident MTTR
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MetricPoint:
    """A single metric data point."""
    name: str
    value: float
    timestamp: str
    labels: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "timestamp": self.timestamp,
            "labels": self.labels,
        }


class Observability:
    """Metrics and tracing for DataForge observability."""

    def __init__(self):
        self.counters: dict[str, int] = defaultdict(int)
        self.gauges: dict[str, float] = {}
        self.histograms: dict[str, list[float]] = defaultdict(list)
        self.timers: dict[str, float] = {}
        self.metrics_history: list[MetricPoint] = []

    def increment(self, name: str, value: int = 1, labels: dict[str, str] | None = None):
        """Increment a counter metric."""
        key = self._make_key(name, labels)
        self.counters[key] += value
        self._record(name, float(self.counters[key]), labels or {})

    def gauge(self, name: str, value: float, labels: dict[str, str] | None = None):
        """Set a gauge metric."""
        key = self._make_key(name, labels)
        self.gauges[key] = value
        self._record(name, value, labels or {})

    def histogram(self, name: str, value: float, labels: dict[str, str] | None = None):
        """Record a histogram value."""
        key = self._make_key(name, labels)
        self.histograms[key].append(value)
        self._record(name, value, labels or {})

    def start_timer(self, name: str, labels: dict[str, str] | None = None):
        """Start a timer."""
        key = self._make_key(name, labels)
        self.timers[key] = time.time()

    def stop_timer(self, name: str, labels: dict[str, str] | None = None) -> float:
        """Stop a timer and record the duration."""
        key = self._make_key(name, labels)
        start = self.timers.pop(key, time.time())
        duration_ms = (time.time() - start) * 1000
        self.histogram(f"{name}_duration_ms", duration_ms, labels)
        return duration_ms

    def record_api_latency(self, endpoint: str, method: str, duration_ms: float, status: int):
        """Record API request latency."""
        labels = {"endpoint": endpoint, "method": method, "status": str(status)}
        self.histogram("api_latency_ms", duration_ms, labels)
        self.increment("api_requests_total", labels=labels)

    def record_agent_latency(self, agent_name: str, duration_ms: float, success: bool):
        """Record agent execution latency."""
        labels = {"agent": agent_name, "success": str(success)}
        self.histogram("agent_latency_ms", duration_ms, labels)
        self.increment("agent_executions_total", labels=labels)

    def record_connector_health(self, connector_id: str, healthy: bool):
        """Record connector health status."""
        labels = {"connector": connector_id}
        self.gauge("connector_healthy", 1.0 if healthy else 0.0, labels)

    def record_execution(self, executor_type: str, success: bool, risk_level: str):
        """Record execution result."""
        labels = {"executor": executor_type, "success": str(success), "risk": risk_level}
        self.increment("executions_total", labels=labels)

    def record_verification(self, passed: bool, incident_id: str):
        """Record verification result."""
        labels = {"passed": str(passed), "incident": incident_id}
        self.increment("verifications_total", labels=labels)

    def record_graph_query(self, query_type: str, duration_ms: float, node_count: int):
        """Record graph query metrics."""
        labels = {"query_type": query_type}
        self.histogram("graph_query_duration_ms", duration_ms, labels)
        self.gauge("graph_query_nodes", float(node_count), labels)

    def record_incident_mttr(self, incident_id: str, mttr_seconds: float):
        """Record incident mean time to resolution."""
        labels = {"incident": incident_id}
        self.histogram("incident_mttr_seconds", mttr_seconds, labels)

    def record_database_health(self, healthy: bool, latency_ms: float):
        """Record database health."""
        self.gauge("database_healthy", 1.0 if healthy else 0.0)
        self.histogram("database_latency_ms", latency_ms)

    def get_counter(self, name: str, labels: dict[str, str] | None = None) -> int:
        """Get counter value."""
        key = self._make_key(name, labels)
        return self.counters.get(key, 0)

    def get_gauge(self, name: str, labels: dict[str, str] | None = None) -> float:
        """Get gauge value."""
        key = self._make_key(name, labels)
        return self.gauges.get(key, 0.0)

    def get_histogram_stats(self, name: str, labels: dict[str, str] | None = None) -> dict:
        """Get histogram statistics."""
        key = self._make_key(name, labels)
        values = self.histograms.get(key, [])
        if not values:
            return {"count": 0, "min": 0, "max": 0, "avg": 0, "p50": 0, "p95": 0, "p99": 0}

        sorted_vals = sorted(values)
        count = len(sorted_vals)
        return {
            "count": count,
            "min": sorted_vals[0],
            "max": sorted_vals[-1],
            "avg": sum(sorted_vals) / count,
            "p50": sorted_vals[count // 2],
            "p95": sorted_vals[int(count * 0.95)] if count > 1 else sorted_vals[-1],
            "p99": sorted_vals[int(count * 0.99)] if count > 1 else sorted_vals[-1],
        }

    def get_all_metrics(self) -> dict:
        """Get all current metrics."""
        return {
            "counters": dict(self.counters),
            "gauges": dict(self.gauges),
            "histograms": {
                name: self.get_histogram_stats(name)
                for name in self.histograms
            },
        }

    def _make_key(self, name: str, labels: dict[str, str] | None) -> str:
        """Create a unique key from name and labels."""
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def _record(self, name: str, value: float, labels: dict[str, str]):
        """Record a metric data point."""
        point = MetricPoint(
            name=name,
            value=value,
            timestamp=datetime.now(timezone.utc).isoformat(),
            labels=labels,
        )
        self.metrics_history.append(point)
        if len(self.metrics_history) > 10000:
            self.metrics_history = self.metrics_history[-5000:]

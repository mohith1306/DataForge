"""Circuit Breaker — auto-stop and auto-rollback on remediation failure.

Monitors execution state and triggers rollback when:
- A step fails
- Verification fails after execution
- Consecutive failures exceed threshold
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitEvent:
    """An event recorded by the circuit breaker."""
    event_type: str
    timestamp: str
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "details": self.details,
        }


class CircuitBreaker:
    """Monitors execution and triggers rollback on failure."""

    def __init__(self, failure_threshold: int = 3, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = CircuitState.CLOSED
        self.consecutive_failures = 0
        self.events: list[CircuitEvent] = []
        self.rollback_callback: Callable | None = None

    def _record_event(self, event_type: str, details: dict | None = None):
        event = CircuitEvent(
            event_type=event_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            details=details or {},
        )
        self.events.append(event)

    def record_success(self):
        """Record a successful step."""
        self.consecutive_failures = 0
        if self.state == CircuitState.OPEN:
            self.state = CircuitState.HALF_OPEN
            self._record_event("circuit_half_open", {"reason": "success while open"})
        elif self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            self._record_event("circuit_closed", {"reason": "success in half-open"})
        self._record_event("step_success")

    def record_failure(self, details: dict | None = None) -> bool:
        """Record a failed step. Returns True if circuit should trip."""
        self.consecutive_failures += 1
        self._record_event("step_failure", details or {})

        if self.consecutive_failures >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self._record_event("circuit_opened", {
                "consecutive_failures": self.consecutive_failures,
                "threshold": self.failure_threshold,
            })
            logger.warning(
                "Circuit breaker OPENED after %d consecutive failures",
                self.consecutive_failures,
            )
            return True

        return False

    def should_rollback(self) -> bool:
        """Check if circuit is open and rollback should be triggered."""
        return self.state == CircuitState.OPEN

    def register_rollback_callback(self, callback: Callable):
        """Register a callback to execute on rollback."""
        self.rollback_callback = callback

    async def trigger_rollback(self, context: dict | None = None) -> dict:
        """Trigger rollback if callback is registered."""
        if self.rollback_callback:
            self._record_event("rollback_triggered", context or {})
            try:
                result = await self.rollback_callback(context)
                self._record_event("rollback_completed", {"result": str(result)})
                self.state = CircuitState.HALF_OPEN
                return {"status": "rollback_executed", "result": result}
            except Exception as e:
                self._record_event("rollback_failed", {"error": str(e)})
                return {"status": "rollback_failed", "error": str(e)}
        return {"status": "no_callback_registered"}

    def get_status(self) -> dict:
        """Get current circuit breaker status."""
        return {
            "state": self.state.value,
            "consecutive_failures": self.consecutive_failures,
            "failure_threshold": self.failure_threshold,
            "events": [e.to_dict() for e in self.events[-10:]],
        }

    def reset(self):
        """Reset the circuit breaker."""
        self.state = CircuitState.CLOSED
        self.consecutive_failures = 0
        self._record_event("circuit_reset")

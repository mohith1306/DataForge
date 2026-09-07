"""Audit Logger for API Gateway."""
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from enum import Enum
import json
import hashlib


class AuditLevel(str, Enum):
    """Audit levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SECURITY = "security"


class AuditEvent(BaseModel):
    """An audit event."""
    id: str = Field(default_factory=lambda: hashlib.md5(f"{datetime.now(timezone.utc).isoformat()}".encode()).hexdigest()[:16])
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    level: AuditLevel
    event_type: str
    actor: str
    actor_type: str = "user"  # user, api_key, system
    resource: str
    resource_type: str
    action: str
    details: Dict[str, Any] = {}
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    request_id: Optional[str] = None
    tenant_id: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = {}


class AuditLogger:
    """Logs audit events for compliance and security."""

    def __init__(self):
        self.events: List[AuditEvent] = []
        self.event_index: Dict[str, List[int]] = {}  # event_type -> indices
        self.actor_index: Dict[str, List[int]] = {}  # actor -> indices
        self.resource_index: Dict[str, List[int]] = {}  # resource -> indices

    def log_event(
        self,
        level: AuditLevel,
        event_type: str,
        actor: str,
        resource: str,
        action: str,
        resource_type: str = "unknown",
        actor_type: str = "user",
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> AuditEvent:
        """Log an audit event."""
        event = AuditEvent(
            level=level,
            event_type=event_type,
            actor=actor,
            actor_type=actor_type,
            resource=resource,
            resource_type=resource_type,
            action=action,
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            tenant_id=tenant_id,
            success=success,
            error_message=error_message
        )

        idx = len(self.events)
        self.events.append(event)

        # Update indices
        if event_type not in self.event_index:
            self.event_index[event_type] = []
        self.event_index[event_type].append(idx)

        if actor not in self.actor_index:
            self.actor_index[actor] = []
        self.actor_index[actor].append(idx)

        if resource not in self.resource_index:
            self.resource_index[resource] = []
        self.resource_index[resource].append(idx)

        return event

    def log_api_request(
        self,
        method: str,
        path: str,
        actor: str,
        status_code: int,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        duration_ms: Optional[float] = None
    ) -> AuditEvent:
        """Log an API request."""
        level = AuditLevel.INFO
        if status_code >= 500:
            level = AuditLevel.ERROR
        elif status_code >= 400:
            level = AuditLevel.WARNING

        return self.log_event(
            level=level,
            event_type="api_request",
            actor=actor,
            resource=path,
            action=method,
            resource_type="api",
            details={
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": duration_ms
            },
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            tenant_id=tenant_id,
            success=status_code < 400
        )

    def log_auth_event(
        self,
        event_type: str,
        actor: str,
        success: bool,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        tenant_id: Optional[str] = None
    ) -> AuditEvent:
        """Log an authentication event."""
        level = AuditLevel.INFO if success else AuditLevel.SECURITY

        return self.log_event(
            level=level,
            event_type=event_type,
            actor=actor,
            resource="auth",
            action=event_type,
            resource_type="auth",
            details=details or {},
            ip_address=ip_address,
            tenant_id=tenant_id,
            success=success
        )

    def log_data_access(
        self,
        actor: str,
        resource: str,
        action: str,
        resource_type: str = "data",
        details: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[str] = None
    ) -> AuditEvent:
        """Log a data access event."""
        return self.log_event(
            level=AuditLevel.INFO,
            event_type="data_access",
            actor=actor,
            resource=resource,
            action=action,
            resource_type=resource_type,
            details=details or {},
            tenant_id=tenant_id
        )

    def log_security_event(
        self,
        event_type: str,
        actor: str,
        resource: str,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        tenant_id: Optional[str] = None
    ) -> AuditEvent:
        """Log a security event."""
        return self.log_event(
            level=AuditLevel.SECURITY,
            event_type=event_type,
            actor=actor,
            resource=resource,
            action=event_type,
            resource_type="security",
            details=details or {},
            ip_address=ip_address,
            tenant_id=tenant_id,
            success=False
        )

    def get_events(
        self,
        event_type: Optional[str] = None,
        actor: Optional[str] = None,
        resource: Optional[str] = None,
        level: Optional[AuditLevel] = None,
        tenant_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[AuditEvent]:
        """Get audit events with optional filters."""
        if event_type and event_type in self.event_index:
            indices = self.event_index[event_type]
            events = [self.events[i] for i in indices]
        elif actor and actor in self.actor_index:
            indices = self.actor_index[actor]
            events = [self.events[i] for i in indices]
        elif resource and resource in self.resource_index:
            indices = self.resource_index[resource]
            events = [self.events[i] for i in indices]
        else:
            events = self.events.copy()

        # Apply additional filters
        if level:
            events = [e for e in events if e.level == level]
        if tenant_id:
            events = [e for e in events if e.tenant_id == tenant_id]
        if start_time:
            events = [e for e in events if e.timestamp >= start_time]
        if end_time:
            events = [e for e in events if e.timestamp <= end_time]

        return events[-limit:]

    def get_event_by_id(self, event_id: str) -> Optional[AuditEvent]:
        """Get an event by ID."""
        for event in self.events:
            if event.id == event_id:
                return event
        return None

    def get_stats(self) -> Dict[str, Any]:
        """Get audit statistics."""
        level_counts = {}
        for event in self.events:
            level_counts[event.level.value] = level_counts.get(event.level.value, 0) + 1

        return {
            "total_events": len(self.events),
            "events_by_level": level_counts,
            "unique_actors": len(self.actor_index),
            "unique_resources": len(self.resource_index),
            "event_types": list(self.event_index.keys())
        }

    def export_events(self, format: str = "json") -> str:
        """Export events in specified format."""
        if format == "json":
            return json.dumps([e.model_dump() for e in self.events], default=str)
        elif format == "csv":
            if not self.events:
                return ""
            headers = ["id", "timestamp", "level", "event_type", "actor", "resource", "action", "success"]
            rows = [",".join([str(getattr(e, h, "")) for h in headers])]
            for event in self.events:
                row = ",".join([str(getattr(event, h, "")) for h in headers])
                rows.append(row)
            return "\n".join(rows)
        return ""

    def clear_old_events(self, days: int = 30) -> int:
        """Clear events older than specified days."""
        cutoff = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - __import__('datetime').timedelta(days=days)

        old_count = len(self.events)
        self.events = [e for e in self.events if e.timestamp >= cutoff]

        # Rebuild indices
        self.event_index.clear()
        self.actor_index.clear()
        self.resource_index.clear()

        for idx, event in enumerate(self.events):
            if event.event_type not in self.event_index:
                self.event_index[event.event_type] = []
            self.event_index[event.event_type].append(idx)

            if event.actor not in self.actor_index:
                self.actor_index[event.actor] = []
            self.actor_index[event.actor].append(idx)

            if event.resource not in self.resource_index:
                self.resource_index[event.resource] = []
            self.resource_index[event.resource].append(idx)

        return old_count - len(self.events)

"""Audit Trail — immutable audit logging for enterprise compliance.

Logs all critical actions:
- Login/logout
- Permission changes
- Connector changes
- Investigation
- Repair proposal
- Approval
- Execution
- Rollback
- Verification
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class AuditAction(str, Enum):
    LOGIN = "login"
    LOGOUT = "logout"
    PERMISSION_CHANGE = "permission_change"
    CONNECTOR_CREATE = "connector_create"
    CONNECTOR_UPDATE = "connector_update"
    CONNECTOR_DELETE = "connector_delete"
    INCIDENT_CREATE = "incident_create"
    INCIDENT_INVESTIGATE = "incident_investigate"
    INCIDENT_DIAGNOSE = "incident_diagnose"
    INCIDENT_REPAIR_PROPOSAL = "incident_repair_proposal"
    INCIDENT_APPROVE = "incident_approve"
    INCIDENT_REJECT = "incident_reject"
    INCIDENT_EXECUTE = "incident_execute"
    INCIDENT_ROLLBACK = "incident_rollback"
    INCIDENT_VERIFY = "incident_verify"
    INCIDENT_RESOLVE = "incident_resolve"
    GRAPH_WRITE = "graph_write"
    SCHEMA_CHANGE = "schema_change"
    SECRET_ACCESS = "secret_access"
    API_KEY_CREATE = "api_key_create"
    API_KEY_REVOKE = "api_key_revoke"
    ORG_SETTINGS_CHANGE = "org_settings_change"
    PROJECT_CREATE = "project_create"
    PROJECT_DELETE = "project_delete"


class AuditSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class AuditEntry:
    """A single audit log entry."""
    entry_id: str
    timestamp: str
    action: AuditAction
    severity: AuditSeverity
    user_id: str
    org_id: str
    resource_type: str
    resource_id: str
    details: dict = field(default_factory=dict)
    ip_address: str = ""
    user_agent: str = ""
    previous_value: Any = None
    new_value: Any = None
    checksum: str = ""

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp,
            "action": self.action.value,
            "severity": self.severity.value,
            "user_id": self.user_id,
            "org_id": self.org_id,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "details": self.details,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "previous_value": self.previous_value,
            "new_value": self.new_value,
            "checksum": self.checksum,
        }


class AuditTrail:
    """Immutable audit trail for enterprise compliance."""

    def __init__(self):
        self.entries: list[AuditEntry] = []
        self._previous_checksum = "0" * 64

    def _compute_checksum(self, entry_data: dict, prev_checksum: str) -> str:
        """Compute SHA-256 checksum for chain integrity."""
        content = json.dumps(entry_data, sort_keys=True, default=str) + prev_checksum
        return hashlib.sha256(content.encode()).hexdigest()

    def log(
        self,
        action: AuditAction,
        user_id: str,
        org_id: str,
        resource_type: str,
        resource_id: str,
        details: dict | None = None,
        severity: AuditSeverity = AuditSeverity.INFO,
        ip_address: str = "",
        user_agent: str = "",
        previous_value: Any = None,
        new_value: Any = None,
    ) -> AuditEntry:
        """Log an audit entry."""
        import uuid

        entry_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        entry_data = {
            "entry_id": entry_id,
            "timestamp": timestamp,
            "action": action.value,
            "user_id": user_id,
            "org_id": org_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
        }

        checksum = self._compute_checksum(entry_data, self._previous_checksum)

        entry = AuditEntry(
            entry_id=entry_id,
            timestamp=timestamp,
            action=action,
            severity=severity,
            user_id=user_id,
            org_id=org_id,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent,
            previous_value=previous_value,
            new_value=new_value,
            checksum=checksum,
        )

        self.entries.append(entry)
        self._previous_checksum = checksum

        log_msg = f"AUDIT: {action.value} by {user_id} on {resource_type}/{resource_id}"
        if severity == AuditSeverity.CRITICAL:
            logger.critical(log_msg)
        elif severity == AuditSeverity.WARNING:
            logger.warning(log_msg)
        else:
            logger.info(log_msg)

        return entry

    def verify_chain(self) -> bool:
        """Verify the integrity of the audit chain."""
        if not self.entries:
            return True

        prev_checksum = "0" * 64
        for entry in self.entries:
            entry_data = {
                "entry_id": entry.entry_id,
                "timestamp": entry.timestamp,
                "action": entry.action.value,
                "user_id": entry.user_id,
                "org_id": entry.org_id,
                "resource_type": entry.resource_type,
                "resource_id": entry.resource_id,
            }
            expected = self._compute_checksum(entry_data, prev_checksum)
            if entry.checksum != expected:
                logger.error(
                    "Audit chain broken at entry %s: expected %s, got %s",
                    entry.entry_id, expected, entry.checksum,
                )
                return False
            prev_checksum = entry.checksum
        return True

    def query(
        self,
        user_id: str | None = None,
        org_id: str | None = None,
        action: AuditAction | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        severity: AuditSeverity | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """Query audit entries with filters."""
        results = self.entries

        if user_id:
            results = [e for e in results if e.user_id == user_id]
        if org_id:
            results = [e for e in results if e.org_id == org_id]
        if action:
            results = [e for e in results if e.action == action]
        if resource_type:
            results = [e for e in results if e.resource_type == resource_type]
        if resource_id:
            results = [e for e in results if e.resource_id == resource_id]
        if severity:
            results = [e for e in results if e.severity == severity]

        return results[-limit:]

    def get_stats(self, org_id: str | None = None) -> dict:
        """Get audit statistics."""
        entries = self.entries
        if org_id:
            entries = [e for e in entries if e.org_id == org_id]

        action_counts = {}
        for e in entries:
            action_counts[e.action.value] = action_counts.get(e.action.value, 0) + 1

        severity_counts = {}
        for e in entries:
            severity_counts[e.severity.value] = severity_counts.get(e.severity.value, 0) + 1

        return {
            "total_entries": len(entries),
            "action_counts": action_counts,
            "severity_counts": severity_counts,
            "chain_valid": self.verify_chain(),
        }

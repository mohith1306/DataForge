"""RBAC — Role-Based Access Control for enterprise authorization.

Roles:
- ORG_ADMIN: Full organization control
- PROJECT_ADMIN: Project-level control
- DATA_ENGINEER: Pipeline and data operations
- SRE: Incident response and reliability
- ANALYST: Read-only with analysis
- VIEWER: Read-only access

Permission model:
- Resource-level authorization
- Organization isolation
- Project isolation
- Connector ownership
- Executor permissions
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class Role(str, Enum):
    ORG_ADMIN = "org_admin"
    PROJECT_ADMIN = "project_admin"
    DATA_ENGINEER = "data_engineer"
    SRE = "sre"
    ANALYST = "analyst"
    VIEWER = "viewer"


class Permission(str, Enum):
    # Organization
    ORG_READ = "org:read"
    ORG_WRITE = "org:write"
    ORG_DELETE = "org:delete"
    ORG_MANAGE_USERS = "org:manage_users"
    ORG_MANAGE_BILLING = "org:manage_billing"

    # Projects
    PROJECT_READ = "project:read"
    PROJECT_WRITE = "project:write"
    PROJECT_DELETE = "project:delete"

    # Connectors
    CONNECTOR_READ = "connector:read"
    CONNECTOR_WRITE = "connector:write"
    CONNECTOR_DELETE = "connector:delete"
    CONNECTOR_EXECUTE = "connector:execute"

    # Incidents
    INCIDENT_READ = "incident:read"
    INCIDENT_WRITE = "incident:write"
    INCIDENT_INVESTIGATE = "incident:investigate"
    INCIDENT_APPROVE = "incident:approve"
    INCIDENT_EXECUTE = "incident:execute"

    # Graph
    GRAPH_READ = "graph:read"
    GRAPH_WRITE = "graph:write"

    # Intelligence
    INTEL_READ = "intel:read"
    INTEL_WRITE = "intel:write"

    # Execution
    EXECUTE_LOW_RISK = "execute:low_risk"
    EXECUTE_MEDIUM_RISK = "execute:medium_risk"
    EXECUTE_HIGH_RISK = "execute:high_risk"
    EXECUTE_CRITICAL = "execute:critical"

    # Audit
    AUDIT_READ = "audit:read"

    # Admin
    ADMIN_FULL = "admin:full"


ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.ORG_ADMIN: {
        Permission.ORG_READ, Permission.ORG_WRITE, Permission.ORG_DELETE,
        Permission.ORG_MANAGE_USERS, Permission.ORG_MANAGE_BILLING,
        Permission.PROJECT_READ, Permission.PROJECT_WRITE, Permission.PROJECT_DELETE,
        Permission.CONNECTOR_READ, Permission.CONNECTOR_WRITE, Permission.CONNECTOR_DELETE,
        Permission.CONNECTOR_EXECUTE,
        Permission.INCIDENT_READ, Permission.INCIDENT_WRITE, Permission.INCIDENT_INVESTIGATE,
        Permission.INCIDENT_APPROVE, Permission.INCIDENT_EXECUTE,
        Permission.GRAPH_READ, Permission.GRAPH_WRITE,
        Permission.INTEL_READ, Permission.INTEL_WRITE,
        Permission.EXECUTE_LOW_RISK, Permission.EXECUTE_MEDIUM_RISK,
        Permission.EXECUTE_HIGH_RISK, Permission.EXECUTE_CRITICAL,
        Permission.AUDIT_READ, Permission.ADMIN_FULL,
    },
    Role.PROJECT_ADMIN: {
        Permission.ORG_READ,
        Permission.PROJECT_READ, Permission.PROJECT_WRITE,
        Permission.CONNECTOR_READ, Permission.CONNECTOR_WRITE, Permission.CONNECTOR_DELETE,
        Permission.CONNECTOR_EXECUTE,
        Permission.INCIDENT_READ, Permission.INCIDENT_WRITE, Permission.INCIDENT_INVESTIGATE,
        Permission.INCIDENT_APPROVE, Permission.INCIDENT_EXECUTE,
        Permission.GRAPH_READ, Permission.GRAPH_WRITE,
        Permission.INTEL_READ, Permission.INTEL_WRITE,
        Permission.EXECUTE_LOW_RISK, Permission.EXECUTE_MEDIUM_RISK,
        Permission.EXECUTE_HIGH_RISK,
        Permission.AUDIT_READ,
    },
    Role.DATA_ENGINEER: {
        Permission.ORG_READ,
        Permission.PROJECT_READ,
        Permission.CONNECTOR_READ, Permission.CONNECTOR_WRITE, Permission.CONNECTOR_EXECUTE,
        Permission.INCIDENT_READ, Permission.INCIDENT_WRITE, Permission.INCIDENT_INVESTIGATE,
        Permission.GRAPH_READ, Permission.GRAPH_WRITE,
        Permission.INTEL_READ,
        Permission.EXECUTE_LOW_RISK, Permission.EXECUTE_MEDIUM_RISK,
    },
    Role.SRE: {
        Permission.ORG_READ,
        Permission.PROJECT_READ,
        Permission.CONNECTOR_READ,
        Permission.INCIDENT_READ, Permission.INCIDENT_WRITE, Permission.INCIDENT_INVESTIGATE,
        Permission.INCIDENT_APPROVE, Permission.INCIDENT_EXECUTE,
        Permission.GRAPH_READ,
        Permission.INTEL_READ,
        Permission.EXECUTE_LOW_RISK, Permission.EXECUTE_MEDIUM_RISK,
        Permission.EXECUTE_HIGH_RISK,
    },
    Role.ANALYST: {
        Permission.ORG_READ,
        Permission.PROJECT_READ,
        Permission.CONNECTOR_READ,
        Permission.INCIDENT_READ,
        Permission.GRAPH_READ,
        Permission.INTEL_READ,
    },
    Role.VIEWER: {
        Permission.ORG_READ,
        Permission.PROJECT_READ,
        Permission.CONNECTOR_READ,
        Permission.INCIDENT_READ,
        Permission.GRAPH_READ,
    },
}


@dataclass
class AccessContext:
    """Context for access control evaluation."""
    user_id: str = ""
    org_id: str = ""
    project_id: str = ""
    role: Role = Role.VIEWER
    resource_org_id: str = ""
    resource_project_id: str = ""
    resource_owner_id: str = ""


@dataclass
class AccessResult:
    """Result of an access check."""
    allowed: bool
    reason: str = ""
    required_permission: str = ""

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "required_permission": self.required_permission,
        }


class RBACEngine:
    """Role-based access control engine."""

    def __init__(self):
        self.role_permissions = ROLE_PERMISSIONS

    def get_permissions(self, role: Role) -> set[Permission]:
        """Get all permissions for a role."""
        return self.role_permissions.get(role, set())

    def has_permission(self, role: Role, permission: Permission) -> bool:
        """Check if a role has a specific permission."""
        return permission in self.get_permissions(role)

    def check_access(
        self,
        context: AccessContext,
        permission: Permission,
    ) -> AccessResult:
        """Check if a user has access based on their role and context."""
        if not self.has_permission(context.role, permission):
            return AccessResult(
                allowed=False,
                reason=f"Role '{context.role.value}' does not have permission '{permission.value}'",
                required_permission=permission.value,
            )

        if context.resource_org_id and context.resource_org_id != context.org_id:
            return AccessResult(
                allowed=False,
                reason="Cross-organization access denied",
                required_permission=permission.value,
            )

        if context.resource_project_id and context.resource_project_id != context.project_id:
            if context.role not in (Role.ORG_ADMIN,):
                return AccessResult(
                    allowed=False,
                    reason="Cross-project access denied",
                    required_permission=permission.value,
                )

        if context.resource_owner_id and context.resource_owner_id != context.user_id:
            if context.role not in (Role.ORG_ADMIN, Role.PROJECT_ADMIN):
                return AccessResult(
                    allowed=False,
                    reason="Resource ownership required",
                    required_permission=permission.value,
                )

        return AccessResult(allowed=True, reason="Access granted")

    def check_risk_permission(self, role: Role, risk_level: str) -> AccessResult:
        """Check if a role can execute an action at a given risk level."""
        risk_permission_map = {
            "low": Permission.EXECUTE_LOW_RISK,
            "medium": Permission.EXECUTE_MEDIUM_RISK,
            "high": Permission.EXECUTE_HIGH_RISK,
            "critical": Permission.EXECUTE_CRITICAL,
        }
        permission = risk_permission_map.get(risk_level)
        if not permission:
            return AccessResult(allowed=False, reason=f"Unknown risk level: {risk_level}")

        if self.has_permission(role, permission):
            return AccessResult(allowed=True)
        return AccessResult(
            allowed=False,
            reason=f"Role '{role.value}' cannot execute {risk_level} risk actions",
            required_permission=permission.value,
        )

    def get_allowed_roles(self, permission: Permission) -> list[Role]:
        """Get all roles that have a specific permission."""
        return [
            role for role, perms in self.role_permissions.items()
            if permission in perms
        ]

    def list_roles(self) -> list[dict]:
        """List all roles with their permission counts."""
        return [
            {
                "role": role.value,
                "permission_count": len(perms),
                "permissions": sorted([p.value for p in perms]),
            }
            for role, perms in self.role_permissions.items()
        ]

"""DataForge API — Tenant-aware database queries."""
from typing import Optional
from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.core.auth import UserContext, get_current_user
from apps.api.app.db.session import get_db


class TenantContext:
    """Provides tenant-scoped database access."""

    def __init__(self, user: UserContext, db: AsyncSession):
        self.user = user
        self.db = db
        self.org_id: Optional[UUID] = user.org_id

    def filter_by_org(self, model, query=None):
        """Add org_id filter to a query."""
        if query is None:
            query = select(model)
        if self.org_id:
            query = query.where(model.org_id == self.org_id)
        return query


async def get_tenant_context(
    user: UserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TenantContext:
    """Dependency that provides tenant-scoped access."""
    return TenantContext(user=user, db=db)

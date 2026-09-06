"""DataForge API — Multi-tenancy middleware."""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class TenantMiddleware(BaseHTTPMiddleware):
    """Extract org_id from authenticated user and inject into request state."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Tenant context is set by auth dependency
        # This middleware ensures tenant_id is available in request state
        request.state.tenant_id = getattr(request.state, "tenant_id", None)
        response = await call_next(request)
        return response

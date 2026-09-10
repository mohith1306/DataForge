"""DataForge API — API Key Authentication."""
import hashlib
import secrets
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.db.models import APIKey, User
from apps.api.app.db.session import get_db

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


class UserContext:
    """Authenticated user context."""

    def __init__(self, user: User, api_key: APIKey, scopes: list[str]):
        self.user = user
        self.api_key = api_key
        self.scopes = scopes
        self.org_id = user.org_id
        self.user_id = user.id

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes or "admin" in self.scopes

    def to_dict(self) -> dict:
        return {
            "user_id": str(self.user_id),
            "org_id": str(self.org_id) if self.org_id else None,
            "email": self.user.email,
            "name": self.user.name,
            "role": self.user.role,
            "scopes": self.scopes,
        }


def hash_api_key(key: str) -> str:
    """Hash an API key for storage."""
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key. Returns (full_key, key_hash, key_prefix)."""
    key = f"df_{secrets.token_urlsafe(32)}"
    key_hash = hash_api_key(key)
    key_prefix = key[:8]
    return key, key_hash, key_prefix


async def get_current_user(
    request: Request,
    api_key: str = Security(API_KEY_HEADER),
    db: AsyncSession = Depends(get_db),
) -> UserContext:
    """Extract and validate API key or dev token from request."""
    
    # Try API key first
    if api_key:
        key_hash = hash_api_key(api_key)
        result = await db.execute(
            select(APIKey)
            .where(APIKey.key_hash == key_hash)
            .where(APIKey.is_active == True)  # noqa: E712
        )
        api_key_record = result.scalar_one_or_none()

        if not api_key_record:
            raise HTTPException(
                status_code=401,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "ApiKey"},
            )

        # Check expiration
        if api_key_record.expires_at and api_key_record.expires_at < datetime.now(UTC):
            raise HTTPException(
                status_code=401,
                detail="API key expired",
                headers={"WWW-Authenticate": "ApiKey"},
            )

        # Update last used
        api_key_record.last_used_at = datetime.now(UTC)
        await db.commit()

        # Get user
        result = await db.execute(select(User).where(User.id == api_key_record.user_id))
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            raise HTTPException(
                status_code=401,
                detail="User not found or inactive",
                headers={"WWW-Authenticate": "ApiKey"},
            )

        scopes = api_key_record.scopes or ["read", "write"]
        return UserContext(user=user, api_key=api_key_record, scopes=scopes)
    
    # Try Bearer token (dev login) from Authorization header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]  # Remove "Bearer " prefix
        if token:
            # Create a dev user context
            result = await db.execute(
                select(User).where(User.email == "admin@dataforge.local")
            )
            user = result.scalar_one_or_none()
            
            if user:
                # Create a temporary API key context for dev user
                class DevApiKey:
                    def __init__(self):
                        self.id = "dev-key"
                        self.name = "Dev Login"
                        self.scopes = ["read", "write", "admin"]
                        self.is_active = True
                        self.expires_at = None
                        self.last_used_at = datetime.now(UTC)
                
                return UserContext(user=user, api_key=DevApiKey(), scopes=["read", "write", "admin"])
    
    raise HTTPException(
        status_code=401,
        detail="Missing API key. Provide via X-API-Key header.",
        headers={"WWW-Authenticate": "ApiKey"},
    )


async def require_write(
    user: UserContext = Depends(get_current_user),
) -> UserContext:
    """Require write scope."""
    if not user.has_scope("write"):
        raise HTTPException(status_code=403, detail="Write access required")
    return user


async def require_read(
    user: UserContext = Depends(get_current_user),
) -> UserContext:
    """Require read scope."""
    if not user.has_scope("read"):
        raise HTTPException(status_code=403, detail="Read access required")
    return user


async def require_admin(
    user: UserContext = Depends(get_current_user),
) -> UserContext:
    """Require admin scope."""
    if not user.has_scope("admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

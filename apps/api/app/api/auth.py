"""Auth API — API key management."""
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.core.auth import (
    UserContext,
    generate_api_key,
    get_current_user,
    require_write,
)

# Valid scopes that can be granted
VALID_SCOPES = {"read", "write", "admin"}
from apps.api.app.db.models import APIKey
from apps.api.app.db.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


# ─── Schemas ──────────────────────────────────────────────────────────


class CreateAPIKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    scopes: list[str] = Field(default=["read", "write"])
    expires_in_days: int | None = Field(default=None, ge=1, le=365)


class CreateAPIKeyResponse(BaseModel):
    id: str
    name: str
    key: str  # Only shown once!
    key_prefix: str
    scopes: list[str]
    expires_at: str | None


class APIKeyInfo(BaseModel):
    id: str
    name: str
    key_prefix: str
    scopes: list[str]
    expires_at: str | None
    last_used_at: str | None
    created_at: str


class UserProfile(BaseModel):
    id: str
    email: str
    name: str | None
    org_id: str | None
    role: str


# ─── User Profile ─────────────────────────────────────────────────────


@router.get("/me", response_model=UserProfile)
async def get_current_user_profile(
    user: UserContext = Depends(get_current_user),
) -> UserProfile:
    """Get the current authenticated user's profile."""
    return UserProfile(
        id=str(user.user_id),
        email=user.user.email,
        name=user.user.name,
        org_id=str(user.org_id) if user.org_id else None,
        role=user.user.role,
    )


# ─── API Key Management ───────────────────────────────────────────────


@router.post("/api-keys", response_model=CreateAPIKeyResponse, status_code=201)
async def create_api_key(
    payload: CreateAPIKeyRequest,
    user: UserContext = Depends(require_write),
    db: AsyncSession = Depends(get_db),
) -> CreateAPIKeyResponse:
    """Create a new API key. The key is shown only once!"""
    # Bug #8 fix: Validate requested scopes against allowed set
    requested_scopes = set(payload.scopes)
    if not requested_scopes.issubset(VALID_SCOPES):
        invalid = requested_scopes - VALID_SCOPES
        raise HTTPException(
            status_code=400,
            detail=f"Invalid scopes: {invalid}. Valid scopes: {VALID_SCOPES}",
        )
    
    # Bug #8 fix: Users can only grant scopes they themselves have
    user_scopes = set(user.scopes)
    if not requested_scopes.issubset(user_scopes):
        insufficient = requested_scopes - user_scopes
        raise HTTPException(
            status_code=403,
            detail=f"Cannot grant scopes you don't have: {insufficient}",
        )
    
    # Bug #8 fix: Admin scope requires admin role
    if "admin" in requested_scopes and not user.has_scope("admin"):
        raise HTTPException(
            status_code=403,
            detail="Admin scope requires admin privileges",
        )
    
    full_key, key_hash, key_prefix = generate_api_key()

    expires_at = None
    if payload.expires_in_days:
        expires_at = datetime.now(UTC) + timedelta(days=payload.expires_in_days)

    api_key = APIKey(
        user_id=user.user.id,
        name=payload.name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        scopes=payload.scopes,
        expires_at=expires_at,
    )
    db.add(api_key)
    await db.flush()
    await db.commit()

    return CreateAPIKeyResponse(
        id=str(api_key.id),
        name=api_key.name,
        key=full_key,
        key_prefix=key_prefix,
        scopes=api_key.scopes,
        expires_at=str(expires_at) if expires_at else None,
    )


@router.get("/api-keys", response_model=list[APIKeyInfo])
async def list_api_keys(
    user: UserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[APIKeyInfo]:
    """List API keys for the current user (without key values)."""
    result = await db.execute(
        select(APIKey)
        .where(APIKey.user_id == user.user.id)
        .where(APIKey.is_active == True)  # noqa: E712
        .order_by(APIKey.created_at.desc())
    )
    keys = result.scalars().all()

    return [
        APIKeyInfo(
            id=str(k.id),
            name=k.name,
            key_prefix=k.key_prefix,
            scopes=k.scopes or [],
            expires_at=str(k.expires_at) if k.expires_at else None,
            last_used_at=str(k.last_used_at) if k.last_used_at else None,
            created_at=str(k.created_at),
        )
        for k in keys
    ]


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: str,
    user: UserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Revoke (deactivate) an API key."""
    result = await db.execute(
        select(APIKey)
        .where(APIKey.id == key_id)
        .where(APIKey.user_id == user.user.id)
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    api_key.is_active = False
    await db.commit()

    return {"status": "revoked", "key_id": key_id, "name": api_key.name}


# Bug #15 fix: Bootstrap endpoint for new installations
@router.post("/bootstrap", response_model=CreateAPIKeyResponse, status_code=201)
async def bootstrap_api_key(
    db: AsyncSession = Depends(get_db),
) -> CreateAPIKeyResponse:
    """Create a bootstrap API key for new installations.
    
    Bug #15 fix: One-time bootstrap endpoint that creates an admin key
    when no users exist. This endpoint is only available when the database
    is empty (no users exist).
    """
    from sqlalchemy import func
    
    # Check if any users exist
    result = await db.execute(select(func.count()))
    user_count = result.scalar()
    
    if user_count > 0:
        raise HTTPException(
            status_code=403,
            detail="Bootstrap endpoint is only available for new installations",
        )
    
    # Create a default admin user
    from apps.api.app.db.models import User
    
    user = User(
        email="admin@dataforge.local",
        name="Admin",
        role="admin",
        org_id=None,
    )
    db.add(user)
    await db.flush()
    
    # Create admin API key
    full_key, key_hash, key_prefix = generate_api_key()
    
    api_key = APIKey(
        user_id=user.id,
        name="Bootstrap Admin Key",
        key_hash=key_hash,
        key_prefix=key_prefix,
        scopes=["read", "write", "admin"],
        expires_at=None,
    )
    db.add(api_key)
    await db.flush()
    await db.commit()
    
    return CreateAPIKeyResponse(
        id=str(api_key.id),
        name=api_key.name,
        key=full_key,
        key_prefix=key_prefix,
        scopes=api_key.scopes,
        expires_at=None,
    )

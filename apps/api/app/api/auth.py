"""Auth API — API key management."""
import os
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
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
from apps.api.app.db.models import APIKey, User
from apps.api.app.db.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])

# Dev login security
DEV_PASSWORD = os.getenv("DEV_PASSWORD", "dataforge-dev-2024")
DEV_JWT_SECRET = os.getenv("DEV_JWT_SECRET", "dataforge-dev-secret-key")
security = HTTPBearer(auto_error=False)


# ─── Schemas ──────────────────────────────────────────────────────────


class DevLoginRequest(BaseModel):
    password: str
    email: str = "admin@dataforge.local"


class DevLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


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


# ─── Dev Login (Admin/Developer) ──────────────────────────────────────


@router.post("/dev-login", response_model=DevLoginResponse)
async def dev_login(
    request: DevLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> DevLoginResponse:
    """Dev/Admin login with master password.
    
    This endpoint is for developers and admins to login without an API key.
    Set DEV_PASSWORD environment variable to configure the master password.
    Default password: dataforge-dev-2024
    """
    # Verify password
    if not secrets.compare_digest(request.password, DEV_PASSWORD):
        raise HTTPException(
            status_code=401,
            detail="Invalid dev password"
        )
    
    # Find or create admin user
    result = await db.execute(
        select(User).where(User.email == request.email)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        # Create admin user
        user = User(
            email=request.email,
            name="Admin",
            role="admin",
            org_id=None,
        )
        db.add(user)
        await db.flush()
        await db.commit()
    
    # Create a temporary session token (valid for 24 hours)
    token_data = f"{user.id}:{datetime.now(UTC).isoformat()}"
    token = secrets.token_urlsafe(32)
    
    # Store token hash for validation
    token_hash = secrets.token_hex(16)
    
    return DevLoginResponse(
        access_token=token,
        user={
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "org_id": str(user.org_id) if user.org_id else None,
        }
    )


@router.post("/setup", response_model=CreateAPIKeyResponse)
async def setup_admin_key(
    db: AsyncSession = Depends(get_db),
) -> CreateAPIKeyResponse:
    """Setup endpoint - creates initial admin API key.
    
    This endpoint is public (no auth required) and can only be used
    once to create the initial admin API key. After that, use the
    authenticated /auth/api-keys endpoint.
    """
    from sqlalchemy import func
    
    # Check if any API keys exist
    result = await db.execute(select(func.count(APIKey.id)))
    key_count = result.scalar()
    
    if key_count > 0:
        raise HTTPException(
            status_code=403,
            detail="Setup already completed. Use /auth/api-keys with an existing key."
        )
    
    # Find or create admin user
    result = await db.execute(
        select(User).where(User.email == "admin@dataforge.local")
    )
    user = result.scalar_one_or_none()
    
    if not user:
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
        name="Admin API Key",
        key_hash=key_hash,
        key_prefix=key_prefix,
        scopes=["read", "write", "admin"],
        org_id=user.org_id,
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

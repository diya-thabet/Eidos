"""
Authentication API endpoints.

Provides:
- ``GET  /auth/login``            -- redirect to GitHub OAuth
- ``GET  /auth/callback``         -- handle GitHub OAuth callback
- ``GET  /auth/google/login``     -- redirect to Google OAuth
- ``GET  /auth/google/callback``  -- handle Google OAuth callback
- ``GET  /auth/me``               -- current user info
- ``POST /auth/logout``           -- invalidate session (client-side)
- ``POST /auth/api-keys``         -- create an API key for CI/CD
- ``GET  /auth/api-keys``         -- list active API keys
- ``DELETE /auth/api-keys/{id}``  -- revoke an API key
"""

from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.crypto import encrypt
from app.auth.dependencies import get_current_user
from app.auth.github_oauth import (
    build_authorize_url,
    exchange_code,
    fetch_github_user,
)
from app.auth.google_oauth import (
    build_google_authorize_url,
    exchange_google_code,
    fetch_google_user,
)
from app.auth.token_service import create_access_token
from app.core.config import settings
from app.storage.database import get_db
from app.storage.models import User

router = APIRouter()


# ---------------------------------------------------------------------------
# GitHub OAuth
# ---------------------------------------------------------------------------


@router.get("/login", summary="Start GitHub OAuth flow")
async def login() -> Any:
    """Redirect the user to GitHub for authorization."""
    if not settings.github_client_id:
        raise HTTPException(
            status_code=501,
            detail="GitHub OAuth not configured",
        )
    state = secrets.token_urlsafe(32)
    url = build_authorize_url(state)
    return RedirectResponse(url=url, status_code=302)


@router.get("/callback", summary="GitHub OAuth callback")
async def oauth_callback(
    code: str,
    state: str = "",
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Handle the GitHub callback: exchange code, upsert user, issue JWT."""
    if not settings.github_client_id:
        raise HTTPException(status_code=501, detail="GitHub OAuth not configured")

    try:
        github_token = await exchange_code(code)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"OAuth code exchange failed: {exc}")

    try:
        gh_user = await fetch_github_user(github_token)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to fetch GitHub profile: {exc}")

    result = await db.execute(select(User).where(User.github_login == gh_user.login))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            id=f"gh-{gh_user.id}",
            auth_provider="github",
            github_id=gh_user.id,
            github_login=gh_user.login,
            name=gh_user.name,
            email=gh_user.email,
            avatar_url=gh_user.avatar_url,
            github_token_enc=encrypt(github_token),
        )
        db.add(user)
    else:
        user.name = gh_user.name
        user.email = gh_user.email
        user.avatar_url = gh_user.avatar_url
        user.github_token_enc = encrypt(github_token)

    await db.commit()
    access_token = create_access_token(user.id)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "login": user.github_login,
            "name": user.name,
            "email": user.email,
            "avatar_url": user.avatar_url,
        },
    }


# ---------------------------------------------------------------------------
# Google OAuth
# ---------------------------------------------------------------------------


@router.get("/google/login", summary="Start Google OAuth flow")
async def google_login() -> Any:
    """Redirect the user to Google for authorization."""
    if not settings.google_client_id:
        raise HTTPException(
            status_code=501,
            detail="Google OAuth not configured",
        )
    state = secrets.token_urlsafe(32)
    url = build_google_authorize_url(state)
    return RedirectResponse(url=url, status_code=302)


@router.get("/google/callback", summary="Google OAuth callback")
async def google_callback(
    code: str,
    state: str = "",
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Handle the Google callback: exchange code, upsert user, issue JWT."""
    if not settings.google_client_id:
        raise HTTPException(status_code=501, detail="Google OAuth not configured")

    try:
        google_token = await exchange_google_code(code)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Google code exchange failed: {exc}")

    try:
        g_user = await fetch_google_user(google_token)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to fetch Google profile: {exc}",
        )

    if not g_user.verified_email:
        raise HTTPException(status_code=400, detail="Google email not verified")

    # Use email as the login key for Google users
    login_key = f"google:{g_user.email}"
    result = await db.execute(select(User).where(User.github_login == login_key))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            id=f"go-{g_user.id}",
            auth_provider="google",
            github_login=login_key,
            name=g_user.name,
            email=g_user.email,
            avatar_url=g_user.picture,
            github_token_enc=encrypt(google_token),
        )
        db.add(user)
    else:
        user.name = g_user.name
        user.email = g_user.email
        user.avatar_url = g_user.picture
        user.github_token_enc = encrypt(google_token)

    await db.commit()
    access_token = create_access_token(user.id)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "login": user.github_login,
            "name": user.name,
            "email": user.email,
            "avatar_url": user.avatar_url,
        },
    }


# ---------------------------------------------------------------------------
# Local (email + password) authentication
# ---------------------------------------------------------------------------


class SignupRequest(BaseModel):
    email: str
    password: str
    name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/signup", summary="Register with email and password")
async def local_signup(
    body: SignupRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Create a new local user with email and password.

    The password is hashed with bcrypt before storage.
    Returns a JWT access token on success.
    """
    import uuid

    from app.auth.password import hash_password

    if not body.email or not body.password:
        raise HTTPException(status_code=422, detail="Email and password are required")

    if len(body.password) < 6:
        raise HTTPException(status_code=422, detail="Password must be at least 6 characters")

    # Check if email already exists
    login_key = f"local:{body.email.lower().strip()}"
    result = await db.execute(select(User).where(User.github_login == login_key))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user_id = f"lo-{uuid.uuid4().hex[:16]}"
    pw_hash = hash_password(body.password)

    # Determine role: superadmin only if email matches explicit config.
    from app.storage.models import UserRole

    role = UserRole.user
    email_lower = body.email.lower().strip()
    if settings.superadmin_email and email_lower == settings.superadmin_email.lower().strip():
        role = UserRole.superadmin

    user = User(
        id=user_id,
        auth_provider="local",
        github_login=login_key,
        name=body.name or body.email.split("@")[0],
        email=email_lower,
        avatar_url="",
        password_hash=pw_hash,
        role=role,
    )
    db.add(user)
    await db.commit()

    access_token = create_access_token(user.id)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "login": user.github_login,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "avatar_url": user.avatar_url,
        },
    }


@router.post("/login", summary="Login with email and password")
async def local_login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Authenticate with email and password. Returns a JWT access token."""
    from app.auth.password import verify_password

    if not body.email or not body.password:
        raise HTTPException(status_code=422, detail="Email and password are required")

    login_key = f"local:{body.email.lower().strip()}"
    result = await db.execute(select(User).where(User.github_login == login_key))
    user = result.scalar_one_or_none()

    if user is None or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Auto-promote to superadmin if email matches config
    from app.storage.models import UserRole

    if (
        settings.superadmin_email
        and user.email.lower() == settings.superadmin_email.lower().strip()
        and user.role != UserRole.superadmin
    ):
        user.role = UserRole.superadmin
        await db.commit()

    access_token = create_access_token(user.id)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "login": user.github_login,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "avatar_url": user.avatar_url,
        },
    }


# ---------------------------------------------------------------------------
# Common
# ---------------------------------------------------------------------------


@router.get("/me", summary="Get current user info")
async def get_me(user: User = Depends(get_current_user)) -> Any:
    """Return the currently authenticated user."""
    return {
        "id": user.id,
        "login": user.github_login,
        "github_login": user.github_login,
        "auth_provider": user.auth_provider,
        "name": user.name,
        "email": user.email,
        "avatar_url": user.avatar_url,
        "role": user.role,
    }


@router.post("/logout", summary="Logout (client-side)")
async def logout() -> Any:
    """JWTs are stateless -- the client should discard the token."""
    return {"detail": "Token discarded. Please delete it on the client."}


# ---------------------------------------------------------------------------
# API Key management
# ---------------------------------------------------------------------------


@router.post(
    "/api-keys",
    status_code=201,
    summary="Create an API key for programmatic access",
    description="Returns the raw key once. Store it securely -- it cannot be retrieved again.",
)
async def create_api_key(
    name: str = Query(description="A label for this key (e.g. 'CI pipeline')"),
    scopes: str = Query(
        default="*",
        description="Comma-separated scopes (e.g. 'read:repos,read:analysis'). '*' = full access.",
    ),
    expires_in_days: int | None = Query(
        default=None, ge=1, le=365,
        description="Key expires after N days. Null = never expires.",
    ),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Create a new API key with optional scopes and expiration."""
    import hashlib
    import uuid
    from datetime import timedelta

    from app.auth.scopes import validate_scopes
    from app.storage.models import ApiKey

    # Validate scopes
    scope_list = [s.strip() for s in scopes.split(",") if s.strip()]
    invalid = validate_scopes(scope_list)
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid scopes: {', '.join(invalid)}",
        )

    key_id = uuid.uuid4().hex[:12]
    raw_key = f"eidos_{secrets.token_urlsafe(32)}"
    prefix = raw_key[:12]
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    expires_at = None
    if expires_in_days:
        from datetime import UTC, datetime
        expires_at = datetime.now(UTC) + timedelta(days=expires_in_days)

    db.add(ApiKey(
        id=key_id,
        user_id=user.id,
        name=name,
        key_hash=key_hash,
        prefix=prefix,
        scopes=",".join(scope_list),
        expires_at=expires_at,
    ))
    await db.commit()

    return {
        "id": key_id,
        "name": name,
        "key": raw_key,
        "prefix": prefix,
        "scopes": scope_list,
        "expires_at": expires_at.isoformat() if expires_at else None,
    }


@router.get(
    "/api-keys",
    summary="List your active API keys",
    description="Returns key metadata (not the raw key). Use prefix to identify keys.",
)
async def list_api_keys(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """List all active API keys for the current user."""
    from app.storage.models import ApiKey

    result = await db.execute(
        select(ApiKey)
        .where(ApiKey.user_id == user.id, ApiKey.is_active.is_(True))
        .order_by(ApiKey.created_at.desc())
    )
    keys = result.scalars().all()
    return [
        {
            "id": k.id,
            "name": k.name,
            "prefix": k.prefix,
            "scopes": (k.scopes or "*").split(","),
            "expires_at": k.expires_at.isoformat() if k.expires_at else None,
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
            "usage_count": k.usage_count or 0,
            "created_at": k.created_at.isoformat() if k.created_at else "",
        }
        for k in keys
    ]


@router.delete(
    "/api-keys/{key_id}",
    summary="Revoke an API key",
    description="Deactivates the key. It can no longer be used for authentication.",
)
async def revoke_api_key(
    key_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Revoke (deactivate) an API key."""
    from app.storage.models import ApiKey

    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user.id)
    )
    key = result.scalar_one_or_none()
    if key is None:
        raise HTTPException(status_code=404, detail="API key not found")

    key.is_active = False
    await db.commit()
    return {"detail": "API key revoked"}


@router.get(
    "/api-keys/scopes",
    summary="List available API key scopes",
    description="Returns all valid scopes that can be assigned to API keys.",
)
async def list_scopes() -> Any:
    """Return the scope catalog."""
    from app.auth.scopes import SCOPES
    return {"scopes": SCOPES}

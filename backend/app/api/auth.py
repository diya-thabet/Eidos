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
# Common
# ---------------------------------------------------------------------------


@router.get("/me", summary="Get current user info")
async def get_me(user: User = Depends(get_current_user)) -> Any:
    """Return the currently authenticated user."""
    return {
        "id": user.id,
        "login": user.github_login,
        "name": user.name,
        "email": user.email,
        "avatar_url": user.avatar_url,
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
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Create a new API key. The raw key is returned only once."""
    import hashlib
    import uuid

    from app.storage.models import ApiKey

    key_id = uuid.uuid4().hex[:12]
    raw_key = f"eidos_{secrets.token_urlsafe(32)}"
    prefix = raw_key[:12]
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    db.add(ApiKey(
        id=key_id,
        user_id=user.id,
        name=name,
        key_hash=key_hash,
        prefix=prefix,
    ))
    await db.commit()

    return {"id": key_id, "name": name, "key": raw_key, "prefix": prefix}


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

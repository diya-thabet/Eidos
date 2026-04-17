"""
Authentication API endpoints.

Provides:
- ``GET  /auth/login``            -- redirect to GitHub OAuth
- ``GET  /auth/callback``         -- handle GitHub OAuth callback
- ``GET  /auth/google/login``     -- redirect to Google OAuth
- ``GET  /auth/google/callback``  -- handle Google OAuth callback
- ``GET  /auth/me``               -- current user info
- ``POST /auth/logout``           -- invalidate session (client-side)
"""

from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
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

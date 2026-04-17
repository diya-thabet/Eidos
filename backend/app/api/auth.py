"""
Authentication API endpoints.

Provides:
- ``GET  /auth/login``     -- redirect to GitHub OAuth
- ``GET  /auth/callback``  -- handle OAuth callback
- ``GET  /auth/me``        -- current user info
- ``POST /auth/logout``    -- invalidate session (client-side)
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
from app.auth.token_service import create_access_token
from app.core.config import settings
from app.storage.database import get_db
from app.storage.models import User

router = APIRouter()


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
    """
    Handle the GitHub callback.

    1. Exchange code for GitHub access token
    2. Fetch GitHub profile
    3. Upsert local User record
    4. Issue JWT session token
    """
    if not settings.github_client_id:
        raise HTTPException(
            status_code=501,
            detail="GitHub OAuth not configured",
        )

    try:
        github_token = await exchange_code(code)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"OAuth code exchange failed: {exc}",
        )

    try:
        gh_user = await fetch_github_user(github_token)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to fetch GitHub profile: {exc}",
        )

    # Upsert user
    result = await db.execute(select(User).where(User.github_login == gh_user.login))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            id=f"gh-{gh_user.id}",
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
    """
    Logout hint.

    JWTs are stateless -- the client should discard the token.
    A future enhancement could maintain a blocklist in Redis.
    """
    return {"detail": "Token discarded. Please delete it on the client."}

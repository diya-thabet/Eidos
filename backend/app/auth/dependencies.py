"""
FastAPI dependency injectors for authentication and authorization.

- ``get_current_user``     -- validate JWT, return User row
- ``get_optional_user``    -- same but returns None if no token
- ``require_repo_access``  -- verify current user owns the repo
"""

from __future__ import annotations

import logging

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.token_service import decode_access_token
from app.core.config import settings
from app.storage.database import get_db
from app.storage.models import Repo, User

logger = logging.getLogger(__name__)


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Extract and validate the Bearer token, return the User row.

    When ``EIDOS_AUTH_ENABLED`` is false the entire check is skipped
    and a sentinel "anonymous" user is returned so that existing
    tests and local-dev workflows keep working.
    """
    if not settings.auth_enabled:
        return _anonymous_user()

    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    return user


async def get_optional_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Like ``get_current_user`` but returns None instead of 401."""
    if not settings.auth_enabled:
        return _anonymous_user()
    try:
        return await get_current_user(request, db)
    except HTTPException:
        return None


async def require_repo_access(
    repo_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Verify the current user owns (or has access to) the repo.

    Raises 404 (not 403) to avoid leaking existence of other repos.
    """
    if not settings.auth_enabled:
        return user

    result = await db.execute(
        select(Repo).where(
            Repo.id == repo_id,
            Repo.owner_id == user.id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Repo not found")
    return user


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------


def _extract_token(request: Request) -> str | None:
    """Extract Bearer token from the Authorization header."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def _anonymous_user() -> User:
    """Synthetic user for when auth is disabled."""

    # Build a transient (detached) ORM instance properly
    u = User(
        id="anonymous",
        github_login="anonymous",
        name="Anonymous",
        email="",
        avatar_url="",
        github_token_enc="",
    )
    # Expunge from any session to avoid accidental flushes
    return u

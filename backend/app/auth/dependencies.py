"""
FastAPI dependency injectors for authentication and authorization.

- ``get_current_user``     -- validate JWT, return User row
- ``get_optional_user``    -- same but returns None if no token
- ``require_repo_access``  -- verify current user owns the repo
- ``require_role``         -- verify current user has the required role
- ``require_quota``        -- verify current user has remaining quota
"""

from __future__ import annotations

import logging
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.metering import check_quota
from app.auth.token_service import decode_access_token
from app.core.config import settings
from app.storage.database import get_db
from app.storage.models import Repo, User, UserRole

logger = logging.getLogger(__name__)

# Role hierarchy: higher index = more privilege
_ROLE_HIERARCHY: dict[str, int] = {
    UserRole.user: 0,
    UserRole.support: 1,
    UserRole.employee: 2,
    UserRole.admin: 3,
    UserRole.superadmin: 4,
}


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Authenticate via Bearer JWT or X-API-Key header.

    When ``EIDOS_AUTH_ENABLED`` is false the entire check is skipped
    and a sentinel "anonymous" user is returned.
    """
    if not settings.auth_enabled:
        return _anonymous_user()

    # Try API key first (for CI/CD)
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return await _authenticate_api_key(api_key, db)

    # Fall back to JWT
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

    Superadmins and admins can access any repo.
    Raises 404 (not 403) to avoid leaking existence of other repos.
    """
    if not settings.auth_enabled:
        return user

    # Admins+ can access any repo
    if _role_level(user.role) >= _ROLE_HIERARCHY[UserRole.admin]:
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


def require_role(*allowed_roles: str) -> Any:
    """
    FastAPI dependency factory: require the user to have one of the given roles.

    Usage:
        @router.get("/admin/users", dependencies=[Depends(require_role("superadmin", "admin"))])

    In ``internal`` edition all role checks are bypassed.
    """

    async def _check(user: User = Depends(get_current_user)) -> User:
        if settings.edition == "internal":
            return user
        if not settings.auth_enabled:
            return user
        if user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return _check


def require_quota(action: str) -> Any:
    """
    FastAPI dependency factory: check the user's usage quota before proceeding.

    In ``internal`` edition all quota checks are bypassed.
    """

    async def _check(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        if settings.edition == "internal":
            return user
        if not settings.auth_enabled:
            return user
        # Internal roles (employee+) have unlimited access
        if _role_level(user.role) >= _ROLE_HIERARCHY[UserRole.employee]:
            return user
        allowed, reason = await check_quota(user.id, action, db)
        if not allowed:
            raise HTTPException(status_code=429, detail=reason)
        return user

    return _check


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------


def _role_level(role: str) -> int:
    return _ROLE_HIERARCHY.get(role, 0)


def _extract_token(request: Request) -> str | None:
    """Extract Bearer token from the Authorization header."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def _anonymous_user() -> User:
    """Synthetic user for when auth is disabled."""
    u = User(
        id="anonymous",
        github_login="anonymous",
        name="Anonymous",
        email="",
        avatar_url="",
        github_token_enc="",
        role=UserRole.superadmin,  # anonymous in dev mode = full access
    )
    return u


async def _authenticate_api_key(raw_key: str, db: AsyncSession) -> User:
    """Validate an API key and return the owning user."""
    import hashlib

    from app.storage.models import ApiKey

    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    result = await db.execute(
        select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True))
    )
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise HTTPException(status_code=401, detail="Invalid API key")

    user = await db.get(User, api_key.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="API key owner not found")

    return user

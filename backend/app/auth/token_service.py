"""
JWT session token service.

Issues short-lived access tokens after GitHub OAuth login.
Tokens carry the user id and are validated on every request.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import jwt

from app.core.config import settings

logger = logging.getLogger(__name__)

_ALGORITHM = "HS256"


def create_access_token(
    user_id: str,
    *,
    expires_in: int | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """Create a signed JWT access token."""
    now = int(time.time())
    ttl = expires_in or settings.jwt_expire_seconds
    payload: dict[str, Any] = {
        "sub": user_id,
        "iat": now,
        "exp": now + ttl,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode and validate a JWT token.

    Raises ``jwt.ExpiredSignatureError`` or ``jwt.InvalidTokenError``
    on failure.
    """
    return jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])

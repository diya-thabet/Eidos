"""
Google OAuth2 authorization flow.

Handles:
1. Building the Google authorization URL
2. Exchanging the callback code for a Google access token
3. Fetching the authenticated Google user profile
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


@dataclass
class GoogleUser:
    """Minimal profile from the Google API."""

    id: str
    email: str
    name: str
    picture: str
    verified_email: bool


def build_google_authorize_url(state: str) -> str:
    """Build the Google OAuth authorization URL."""
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{_GOOGLE_AUTHORIZE_URL}?{qs}"


async def exchange_google_code(code: str) -> str:
    """Exchange an OAuth callback code for a Google access token."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.google_redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

    token = data.get("access_token")
    if not token:
        error = data.get("error_description", data.get("error", "unknown"))
        raise ValueError(f"Google token exchange failed: {error}")
    return str(token)


async def fetch_google_user(access_token: str) -> GoogleUser:
    """Fetch the authenticated user's profile from Google."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            _GOOGLE_USERINFO_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

    return GoogleUser(
        id=str(data.get("id", "")),
        email=data.get("email", ""),
        name=data.get("name", "") or data.get("email", ""),
        picture=data.get("picture", ""),
        verified_email=data.get("verified_email", False),
    )

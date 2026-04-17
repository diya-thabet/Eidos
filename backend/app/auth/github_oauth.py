"""
GitHub OAuth2 authorization flow.

Handles:
1. Building the authorization URL
2. Exchanging the callback code for a GitHub access token
3. Fetching the authenticated GitHub user profile
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
_GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
_GITHUB_USER_URL = "https://api.github.com/user"


@dataclass
class GitHubUser:
    """Minimal profile from the GitHub API."""

    id: int
    login: str
    name: str
    email: str
    avatar_url: str


def build_authorize_url(state: str) -> str:
    """Build the GitHub OAuth authorization URL."""
    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": settings.github_redirect_uri,
        "scope": "read:user user:email",
        "state": state,
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{_GITHUB_AUTHORIZE_URL}?{qs}"


async def exchange_code(code: str) -> str:
    """Exchange an OAuth callback code for a GitHub access token."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            _GITHUB_TOKEN_URL,
            json={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
            },
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

    token = data.get("access_token")
    if not token:
        error = data.get("error_description", data.get("error", "unknown"))
        raise ValueError(f"GitHub token exchange failed: {error}")
    return str(token)


async def fetch_github_user(access_token: str) -> GitHubUser:
    """Fetch the authenticated user's profile from GitHub."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            _GITHUB_USER_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

    return GitHubUser(
        id=data.get("id", 0),
        login=data.get("login", ""),
        name=data.get("name", "") or data.get("login", ""),
        email=data.get("email", "") or "",
        avatar_url=data.get("avatar_url", ""),
    )

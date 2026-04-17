"""
Tests for GitHub OAuth module.

Covers: authorize URL building, code exchange (mocked),
user profile fetch (mocked).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.auth.github_oauth import (
    GitHubUser,
    build_authorize_url,
    exchange_code,
    fetch_github_user,
)


class TestBuildAuthorizeUrl:
    def test_contains_client_id(self):
        with patch("app.auth.github_oauth.settings") as ms:
            ms.github_client_id = "test-client-123"
            ms.github_redirect_uri = "http://localhost/callback"
            url = build_authorize_url("state-abc")
        assert "test-client-123" in url
        assert "state-abc" in url
        assert "github.com" in url

    def test_contains_scope(self):
        with patch("app.auth.github_oauth.settings") as ms:
            ms.github_client_id = "x"
            ms.github_redirect_uri = "http://localhost/cb"
            url = build_authorize_url("s1")
        assert "read:user" in url


class TestExchangeCode:
    @pytest.mark.asyncio
    async def test_success(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "gho_abc123"}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("app.auth.github_oauth.settings") as ms,
            patch("app.auth.github_oauth.httpx.AsyncClient", return_value=mock_client),
        ):
            ms.github_client_id = "id"
            ms.github_client_secret = "secret"
            token = await exchange_code("code123")

        assert token == "gho_abc123"

    @pytest.mark.asyncio
    async def test_error_response(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"error": "bad_verification_code"}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("app.auth.github_oauth.settings") as ms,
            patch("app.auth.github_oauth.httpx.AsyncClient", return_value=mock_client),
        ):
            ms.github_client_id = "id"
            ms.github_client_secret = "secret"
            with pytest.raises(ValueError, match="failed"):
                await exchange_code("bad-code")


class TestFetchGithubUser:
    @pytest.mark.asyncio
    async def test_success(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "id": 42,
            "login": "octocat",
            "name": "The Octocat",
            "email": "octo@github.com",
            "avatar_url": "https://avatar.url",
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch(
            "app.auth.github_oauth.httpx.AsyncClient",
            return_value=mock_client,
        ):
            user = await fetch_github_user("token-123")

        assert isinstance(user, GitHubUser)
        assert user.login == "octocat"
        assert user.id == 42

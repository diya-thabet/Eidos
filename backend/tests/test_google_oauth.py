"""
Google OAuth module tests.

Covers: authorize URL, code exchange, user profile fetch, error handling.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.auth.google_oauth import (
    GoogleUser,
    build_google_authorize_url,
    exchange_google_code,
    fetch_google_user,
)


class TestBuildGoogleAuthorizeUrl:
    def test_contains_client_id(self):
        with patch("app.auth.google_oauth.settings") as ms:
            ms.google_client_id = "google-id-123"
            ms.google_redirect_uri = "http://localhost/cb"
            url = build_google_authorize_url("state1")
        assert "google-id-123" in url
        assert "state1" in url
        assert "accounts.google.com" in url

    def test_contains_scopes(self):
        with patch("app.auth.google_oauth.settings") as ms:
            ms.google_client_id = "x"
            ms.google_redirect_uri = "http://localhost/cb"
            url = build_google_authorize_url("s")
        assert "openid" in url
        assert "email" in url
        assert "profile" in url

    def test_contains_redirect_uri(self):
        with patch("app.auth.google_oauth.settings") as ms:
            ms.google_client_id = "x"
            ms.google_redirect_uri = "http://myapp.com/auth/google/callback"
            url = build_google_authorize_url("s")
        assert "myapp.com" in url


class TestExchangeGoogleCode:
    @pytest.mark.asyncio
    async def test_success(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "ya29.abc"}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("app.auth.google_oauth.settings") as ms,
            patch("app.auth.google_oauth.httpx.AsyncClient", return_value=mock_client),
        ):
            ms.google_client_id = "id"
            ms.google_client_secret = "secret"
            ms.google_redirect_uri = "http://localhost/cb"
            token = await exchange_google_code("code123")

        assert token == "ya29.abc"

    @pytest.mark.asyncio
    async def test_error_response(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"error": "invalid_grant"}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("app.auth.google_oauth.settings") as ms,
            patch("app.auth.google_oauth.httpx.AsyncClient", return_value=mock_client),
        ):
            ms.google_client_id = "id"
            ms.google_client_secret = "secret"
            ms.google_redirect_uri = "http://localhost/cb"
            with pytest.raises(ValueError, match="failed"):
                await exchange_google_code("bad")


class TestFetchGoogleUser:
    @pytest.mark.asyncio
    async def test_success(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "id": "12345",
            "email": "user@gmail.com",
            "name": "Test User",
            "picture": "https://pic.url",
            "verified_email": True,
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch(
            "app.auth.google_oauth.httpx.AsyncClient",
            return_value=mock_client,
        ):
            user = await fetch_google_user("token-123")

        assert isinstance(user, GoogleUser)
        assert user.email == "user@gmail.com"
        assert user.verified_email is True

    @pytest.mark.asyncio
    async def test_unverified_email(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "id": "99",
            "email": "unverified@test.com",
            "name": "Test",
            "picture": "",
            "verified_email": False,
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch(
            "app.auth.google_oauth.httpx.AsyncClient",
            return_value=mock_client,
        ):
            user = await fetch_google_user("token")

        assert user.verified_email is False

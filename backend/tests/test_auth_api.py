"""
Tests for the auth API endpoints.

Covers: /auth/login, /auth/callback, /auth/me, /auth/logout,
GitHub OAuth mocking, user upsert.
"""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.auth.github_oauth import GitHubUser
from app.auth.token_service import create_access_token
from app.main import app
from app.storage.database import get_db
from app.storage.models import User
from tests.conftest import (
    create_tables,
    drop_tables,
    override_get_db,
    test_sessionmaker,
)

app.dependency_overrides[get_db] = override_get_db


async def _seed():
    async with test_sessionmaker() as db:
        db.add(
            User(
                id="u-existing",
                github_id=99,
                github_login="existinguser",
                name="Existing",
            )
        )
        await db.commit()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await create_tables()
    await _seed()
    yield
    await drop_tables()


@pytest_asyncio.fixture
async def client():
    with patch("app.api.repos.run_ingestion", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            follow_redirects=False,
        ) as ac:
            yield ac


class TestLoginEndpoint:
    @pytest.mark.asyncio
    async def test_login_no_oauth_configured(self, client):
        with patch("app.api.auth.settings") as ms:
            ms.github_client_id = ""
            resp = await client.get("/auth/login")
        assert resp.status_code == 501

    @pytest.mark.asyncio
    async def test_login_redirects(self, client):
        with patch("app.api.auth.settings") as ms:
            ms.github_client_id = "test-client-id"
            ms.github_redirect_uri = "http://localhost:8000/auth/callback"
            resp = await client.get("/auth/login")
        assert resp.status_code == 302
        assert "github.com" in resp.headers.get("location", "")


class TestCallbackEndpoint:
    @pytest.mark.asyncio
    async def test_callback_no_oauth_configured(self, client):
        with patch("app.api.auth.settings") as ms:
            ms.github_client_id = ""
            resp = await client.get("/auth/callback?code=abc&state=xyz")
        assert resp.status_code == 501

    @pytest.mark.asyncio
    async def test_callback_creates_user(self, client):
        mock_gh_user = GitHubUser(
            id=42,
            login="newuser",
            name="New User",
            email="new@test.com",
            avatar_url="https://github.com/avatar",
        )
        with (
            patch("app.api.auth.settings") as ms,
            patch("app.api.auth.exchange_code", new_callable=AsyncMock) as mock_exchange,
            patch("app.api.auth.fetch_github_user", new_callable=AsyncMock) as mock_fetch,
        ):
            ms.github_client_id = "test-id"
            ms.github_client_secret = "test-secret"
            mock_exchange.return_value = "gh-token-123"
            mock_fetch.return_value = mock_gh_user

            resp = await client.get("/auth/callback?code=testcode&state=xyz")

        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["user"]["login"] == "newuser"

    @pytest.mark.asyncio
    async def test_callback_updates_existing_user(self, client):
        mock_gh_user = GitHubUser(
            id=99,
            login="existinguser",
            name="Updated Name",
            email="updated@test.com",
            avatar_url="https://avatar.new",
        )
        with (
            patch("app.api.auth.settings") as ms,
            patch("app.api.auth.exchange_code", new_callable=AsyncMock) as mock_exchange,
            patch("app.api.auth.fetch_github_user", new_callable=AsyncMock) as mock_fetch,
        ):
            ms.github_client_id = "test-id"
            ms.github_client_secret = "test-secret"
            mock_exchange.return_value = "gh-token-456"
            mock_fetch.return_value = mock_gh_user

            resp = await client.get("/auth/callback?code=testcode&state=xyz")

        assert resp.status_code == 200
        data = resp.json()
        assert data["user"]["name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_callback_bad_code(self, client):
        with (
            patch("app.api.auth.settings") as ms,
            patch("app.api.auth.exchange_code", new_callable=AsyncMock) as mock_exchange,
        ):
            ms.github_client_id = "test-id"
            mock_exchange.side_effect = ValueError("bad code")

            resp = await client.get("/auth/callback?code=bad&state=xyz")
        assert resp.status_code == 400


class TestMeEndpoint:
    @pytest.mark.asyncio
    async def test_me_anonymous(self, client):
        resp = await client.get("/auth/me")
        assert resp.status_code == 200
        assert resp.json()["login"] == "anonymous"

    @pytest.mark.asyncio
    async def test_me_authenticated(self, client):
        token = create_access_token("u-existing")
        with patch("app.auth.dependencies.settings") as ms:
            ms.auth_enabled = True
            resp = await client.get(
                "/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        assert resp.json()["id"] == "u-existing"


class TestLogoutEndpoint:
    @pytest.mark.asyncio
    async def test_logout(self, client):
        resp = await client.post("/auth/logout")
        assert resp.status_code == 200
        assert "discard" in resp.json()["detail"].lower()

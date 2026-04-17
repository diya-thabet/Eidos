"""
Google OAuth API endpoint tests.

Covers: /auth/google/login, /auth/google/callback with mocked Google API.
"""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.auth.google_oauth import GoogleUser
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


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await create_tables()
    yield
    await drop_tables()


@pytest_asyncio.fixture
async def client():
    with patch("app.api.repos.run_ingestion", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", follow_redirects=False
        ) as ac:
            yield ac


class TestGoogleLogin:
    @pytest.mark.asyncio
    async def test_not_configured_returns_501(self, client):
        with patch("app.api.auth.settings") as ms:
            ms.google_client_id = ""
            resp = await client.get("/auth/google/login")
        assert resp.status_code == 501

    @pytest.mark.asyncio
    async def test_redirects_to_google(self, client):
        with patch("app.api.auth.settings") as ms:
            ms.google_client_id = "google-test-id"
            ms.google_redirect_uri = "http://localhost/cb"
            resp = await client.get("/auth/google/login")
        assert resp.status_code == 302
        assert "accounts.google.com" in resp.headers.get("location", "")


class TestGoogleCallback:
    @pytest.mark.asyncio
    async def test_not_configured_returns_501(self, client):
        with patch("app.api.auth.settings") as ms:
            ms.google_client_id = ""
            resp = await client.get("/auth/google/callback?code=x&state=y")
        assert resp.status_code == 501

    @pytest.mark.asyncio
    async def test_creates_google_user(self, client):
        mock_user = GoogleUser(
            id="123",
            email="user@gmail.com",
            name="Test",
            picture="https://pic",
            verified_email=True,
        )
        with (
            patch("app.api.auth.settings") as ms,
            patch("app.api.auth.exchange_google_code", new_callable=AsyncMock) as me,
            patch("app.api.auth.fetch_google_user", new_callable=AsyncMock) as mf,
        ):
            ms.google_client_id = "id"
            ms.google_client_secret = "secret"
            me.return_value = "ya29.token"
            mf.return_value = mock_user

            resp = await client.get("/auth/google/callback?code=valid&state=s")

        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["user"]["email"] == "user@gmail.com"
        assert data["user"]["login"] == "google:user@gmail.com"

    @pytest.mark.asyncio
    async def test_rejects_unverified_email(self, client):
        mock_user = GoogleUser(
            id="99",
            email="bad@test.com",
            name="Bad",
            picture="",
            verified_email=False,
        )
        with (
            patch("app.api.auth.settings") as ms,
            patch("app.api.auth.exchange_google_code", new_callable=AsyncMock) as me,
            patch("app.api.auth.fetch_google_user", new_callable=AsyncMock) as mf,
        ):
            ms.google_client_id = "id"
            me.return_value = "token"
            mf.return_value = mock_user

            resp = await client.get("/auth/google/callback?code=c&state=s")

        assert resp.status_code == 400
        assert "not verified" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_updates_existing_google_user(self, client):
        # Pre-create user
        async with test_sessionmaker() as db:
            db.add(
                User(
                    id="go-123",
                    auth_provider="google",
                    github_login="google:user@gmail.com",
                    name="Old Name",
                    email="user@gmail.com",
                )
            )
            await db.commit()

        mock_user = GoogleUser(
            id="123",
            email="user@gmail.com",
            name="New Name",
            picture="https://newpic",
            verified_email=True,
        )
        with (
            patch("app.api.auth.settings") as ms,
            patch("app.api.auth.exchange_google_code", new_callable=AsyncMock) as me,
            patch("app.api.auth.fetch_google_user", new_callable=AsyncMock) as mf,
        ):
            ms.google_client_id = "id"
            me.return_value = "ya29.new"
            mf.return_value = mock_user

            resp = await client.get("/auth/google/callback?code=c&state=s")

        assert resp.status_code == 200
        assert resp.json()["user"]["name"] == "New Name"

    @pytest.mark.asyncio
    async def test_bad_code_returns_400(self, client):
        with (
            patch("app.api.auth.settings") as ms,
            patch("app.api.auth.exchange_google_code", new_callable=AsyncMock) as me,
        ):
            ms.google_client_id = "id"
            me.side_effect = ValueError("bad code")
            resp = await client.get("/auth/google/callback?code=bad&state=s")
        assert resp.status_code == 400

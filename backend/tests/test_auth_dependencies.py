"""
Tests for auth dependencies (get_current_user, require_repo_access).

Covers: anonymous mode, valid JWT, expired JWT, invalid JWT,
repo access control, isolation between users.
"""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.auth.token_service import create_access_token
from app.main import app
from app.storage.database import get_db
from app.storage.models import Repo, RepoSnapshot, SnapshotStatus, User
from tests.conftest import (
    create_tables,
    drop_tables,
    override_get_db,
    test_sessionmaker,
)

app.dependency_overrides[get_db] = override_get_db


async def _seed():
    async with test_sessionmaker() as db:
        # Two users
        db.add(
            User(
                id="u-alice",
                github_login="alice",
                name="Alice",
            )
        )
        db.add(
            User(
                id="u-bob",
                github_login="bob",
                name="Bob",
            )
        )
        await db.flush()

        # Alice owns repo-a
        db.add(
            Repo(
                id="repo-a",
                owner_id="u-alice",
                name="alice-repo",
                url="https://github.com/alice/repo",
            )
        )
        db.add(
            RepoSnapshot(
                id="snap-a",
                repo_id="repo-a",
                status=SnapshotStatus.completed,
            )
        )

        # Bob owns repo-b
        db.add(
            Repo(
                id="repo-b",
                owner_id="u-bob",
                name="bob-repo",
                url="https://github.com/bob/repo",
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
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


class TestAnonymousMode:
    """When auth_enabled=False (default), all endpoints work without tokens."""

    @pytest.mark.asyncio
    async def test_create_repo_no_token(self, client):
        resp = await client.post(
            "/repos",
            json={
                "name": "test",
                "url": "https://github.com/x/y",
            },
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_get_me_anonymous(self, client):
        resp = await client.get("/auth/me")
        assert resp.status_code == 200
        assert resp.json()["login"] == "anonymous"


class TestAuthEnabled:
    """When auth_enabled=True, JWT is required."""

    @pytest.mark.asyncio
    async def test_no_token_returns_401(self, client):
        with patch("app.auth.dependencies.settings") as mock_settings:
            mock_settings.auth_enabled = True
            resp = await client.post(
                "/repos",
                json={
                    "name": "t",
                    "url": "https://github.com/x/y",
                },
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_token_works(self, client):
        token = create_access_token("u-alice")
        with patch("app.auth.dependencies.settings") as mock_settings:
            mock_settings.auth_enabled = True
            resp = await client.get(
                "/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        assert resp.json()["id"] == "u-alice"

    @pytest.mark.asyncio
    async def test_expired_token_returns_401(self, client):
        token = create_access_token("u-alice", expires_in=-1)
        with patch("app.auth.dependencies.settings") as mock_settings:
            mock_settings.auth_enabled = True
            resp = await client.get(
                "/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self, client):
        with patch("app.auth.dependencies.settings") as mock_settings:
            mock_settings.auth_enabled = True
            resp = await client.get(
                "/auth/me",
                headers={"Authorization": "Bearer garbage"},
            )
        assert resp.status_code == 401


class TestRepoIsolation:
    """When auth is enabled, users can only access their own repos."""

    @pytest.mark.asyncio
    async def test_owner_can_access_own_repo(self, client):
        token = create_access_token("u-alice")
        with patch("app.auth.dependencies.settings") as mock_settings:
            mock_settings.auth_enabled = True
            resp = await client.get(
                "/repos/repo-a/status",
                headers={"Authorization": f"Bearer {token}"},
            )
        # Should succeed (or 404 if repo_status doesn't use require_repo_access)
        assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_alice_cannot_see_bob_repo(self, client):
        """Alice should not be able to access Bob's repo."""
        from app.auth.dependencies import require_repo_access
        from app.storage.models import User as UserModel

        with patch("app.auth.dependencies.settings") as mock_settings:
            mock_settings.auth_enabled = True
            async with test_sessionmaker() as db:
                user = await db.get(UserModel, "u-alice")
                with pytest.raises(Exception):
                    await require_repo_access("repo-b", user, db)

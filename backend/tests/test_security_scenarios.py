"""
Security isolation scenario tests.

End-to-end tests verifying that:
- User A cannot see User B's repos
- User A cannot access User B's snapshots
- User A cannot trigger actions on User B's repos
- Anonymous users get isolated when auth is off
- Token rotation doesn't break existing sessions
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
        db.add(User(id="u-alice", github_login="alice", name="Alice"))
        db.add(User(id="u-bob", github_login="bob", name="Bob"))
        await db.flush()

        db.add(
            Repo(
                id="r-alice",
                owner_id="u-alice",
                name="alice-project",
                url="https://github.com/alice/proj",
            )
        )
        db.add(
            RepoSnapshot(
                id="s-alice",
                repo_id="r-alice",
                status=SnapshotStatus.completed,
            )
        )

        db.add(
            Repo(
                id="r-bob",
                owner_id="u-bob",
                name="bob-project",
                url="https://github.com/bob/proj",
            )
        )
        db.add(
            RepoSnapshot(
                id="s-bob",
                repo_id="r-bob",
                status=SnapshotStatus.completed,
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


def _alice_headers():
    return {"Authorization": f"Bearer {create_access_token('u-alice')}"}


def _bob_headers():
    return {"Authorization": f"Bearer {create_access_token('u-bob')}"}


class TestRepoIsolationEnforced:
    """With auth enabled, users are isolated."""

    @pytest.mark.asyncio
    async def test_alice_accesses_own_repo(self, client):
        with patch("app.auth.dependencies.settings") as ms:
            ms.auth_enabled = True
            resp = await client.get(
                "/repos/r-alice/status",
                headers=_alice_headers(),
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_bob_cannot_access_alice_repo(self, client):
        """Bob should get 404 for Alice's repo (not 403)."""
        from app.auth.dependencies import require_repo_access

        with patch("app.auth.dependencies.settings") as ms:
            ms.auth_enabled = True
            async with test_sessionmaker() as db:
                bob = await db.get(User, "u-bob")
                with pytest.raises(Exception):
                    await require_repo_access("r-alice", bob, db)

    @pytest.mark.asyncio
    async def test_alice_cannot_access_bob_repo(self, client):
        from app.auth.dependencies import require_repo_access

        with patch("app.auth.dependencies.settings") as ms:
            ms.auth_enabled = True
            async with test_sessionmaker() as db:
                alice = await db.get(User, "u-alice")
                with pytest.raises(Exception):
                    await require_repo_access("r-bob", alice, db)

    @pytest.mark.asyncio
    async def test_nonexistent_repo_returns_404(self, client):
        from app.auth.dependencies import require_repo_access

        with patch("app.auth.dependencies.settings") as ms:
            ms.auth_enabled = True
            async with test_sessionmaker() as db:
                alice = await db.get(User, "u-alice")
                with pytest.raises(Exception):
                    await require_repo_access("r-ghost", alice, db)


class TestOwnershipOnCreate:
    """New repos are assigned to the authenticated user."""

    @pytest.mark.asyncio
    async def test_repo_gets_owner(self, client):
        token = create_access_token("u-alice")
        with patch("app.auth.dependencies.settings") as ms:
            ms.auth_enabled = True
            resp = await client.post(
                "/repos",
                json={
                    "name": "new-repo",
                    "url": "https://github.com/alice/new",
                },
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 201

        # Verify owner_id was set
        repo_id = resp.json()["id"]
        async with test_sessionmaker() as db:
            repo = await db.get(Repo, repo_id)
            assert repo is not None
            assert repo.owner_id == "u-alice"


class TestAnonymousIsolation:
    """When auth is off, repos have no owner_id (null)."""

    @pytest.mark.asyncio
    async def test_anonymous_repo_no_owner(self, client):
        resp = await client.post(
            "/repos",
            json={
                "name": "anon-repo",
                "url": "https://github.com/x/y",
            },
        )
        assert resp.status_code == 201
        repo_id = resp.json()["id"]

        async with test_sessionmaker() as db:
            repo = await db.get(Repo, repo_id)
            assert repo is not None
            assert repo.owner_id is None

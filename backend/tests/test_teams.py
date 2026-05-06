"""
Tests for RBAC Phase 5: Team / Organization Model.

Tests 9 API endpoints for team CRUD, members, and repo access.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.auth.token_service import create_access_token
from app.core.config import settings
from app.main import app
from app.storage.database import get_db
from app.storage.models import Repo, User, UserRole
from tests.conftest import create_tables, drop_tables, override_get_db

app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await drop_tables()
    await create_tables()
    async for db in override_get_db():
        db.add(User(
            id="u1", github_login="alice", name="Alice",
            email="a@x.com", avatar_url="", github_token_enc="",
            role=UserRole.user,
        ))
        db.add(User(
            id="u2", github_login="bob", name="Bob",
            email="b@x.com", avatar_url="", github_token_enc="",
            role=UserRole.user,
        ))
        db.add(User(
            id="admin1", github_login="admin", name="Admin",
            email="admin@x.com", avatar_url="", github_token_enc="",
            role=UserRole.admin,
        ))
        db.add(Repo(id="r1", name="demo", url="http://x", owner_id="u1"))
        await db.commit()
    yield
    await drop_tables()


def _jwt(uid: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token(uid)}"}


@pytest_asyncio.fixture
async def client():
    original = settings.auth_enabled
    settings.auth_enabled = True
    with patch("app.api.repos.run_ingestion", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    settings.auth_enabled = original


class TestTeamCRUD:

    @pytest.mark.asyncio
    async def test_create_team(self, client):
        resp = await client.post(
            "/teams", json={"name": "Backend", "description": "Backend devs"},
            headers=_jwt("u1"),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Backend"
        assert data["member_count"] == 1
        assert data["created_by"] == "u1"

    @pytest.mark.asyncio
    async def test_create_team_empty_name(self, client):
        resp = await client.post(
            "/teams", json={"name": "  "},
            headers=_jwt("u1"),
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_list_teams(self, client):
        await client.post("/teams", json={"name": "A"}, headers=_jwt("u1"))
        await client.post("/teams", json={"name": "B"}, headers=_jwt("u1"))
        resp = await client.get("/teams", headers=_jwt("u1"))
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    @pytest.mark.asyncio
    async def test_list_teams_only_mine(self, client):
        await client.post("/teams", json={"name": "A"}, headers=_jwt("u1"))
        resp = await client.get("/teams", headers=_jwt("u2"))
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_get_team(self, client):
        r = await client.post("/teams", json={"name": "X"}, headers=_jwt("u1"))
        tid = r.json()["id"]
        resp = await client.get(f"/teams/{tid}", headers=_jwt("u1"))
        assert resp.status_code == 200
        assert resp.json()["name"] == "X"

    @pytest.mark.asyncio
    async def test_get_team_non_member(self, client):
        r = await client.post("/teams", json={"name": "X"}, headers=_jwt("u1"))
        tid = r.json()["id"]
        resp = await client.get(f"/teams/{tid}", headers=_jwt("u2"))
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_team(self, client):
        r = await client.post("/teams", json={"name": "Old"}, headers=_jwt("u1"))
        tid = r.json()["id"]
        resp = await client.patch(
            f"/teams/{tid}", json={"name": "New"},
            headers=_jwt("u1"),
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New"

    @pytest.mark.asyncio
    async def test_update_team_non_admin(self, client):
        r = await client.post("/teams", json={"name": "T"}, headers=_jwt("u1"))
        tid = r.json()["id"]
        # Add u2 as member
        await client.post(
            f"/teams/{tid}/members",
            json={"user_id": "u2", "role": "member"},
            headers=_jwt("u1"),
        )
        resp = await client.patch(
            f"/teams/{tid}", json={"name": "Nope"},
            headers=_jwt("u2"),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_team(self, client):
        r = await client.post("/teams", json={"name": "T"}, headers=_jwt("u1"))
        tid = r.json()["id"]
        resp = await client.delete(f"/teams/{tid}", headers=_jwt("u1"))
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_team_non_admin(self, client):
        r = await client.post("/teams", json={"name": "T"}, headers=_jwt("u1"))
        tid = r.json()["id"]
        await client.post(
            f"/teams/{tid}/members",
            json={"user_id": "u2"}, headers=_jwt("u1"),
        )
        resp = await client.delete(f"/teams/{tid}", headers=_jwt("u2"))
        assert resp.status_code == 403


class TestTeamMembers:

    @pytest.mark.asyncio
    async def test_add_member(self, client):
        r = await client.post("/teams", json={"name": "T"}, headers=_jwt("u1"))
        tid = r.json()["id"]
        resp = await client.post(
            f"/teams/{tid}/members",
            json={"user_id": "u2", "role": "member"},
            headers=_jwt("u1"),
        )
        assert resp.status_code == 201
        assert resp.json()["user_id"] == "u2"

    @pytest.mark.asyncio
    async def test_add_member_duplicate(self, client):
        r = await client.post("/teams", json={"name": "T"}, headers=_jwt("u1"))
        tid = r.json()["id"]
        await client.post(
            f"/teams/{tid}/members", json={"user_id": "u2"},
            headers=_jwt("u1"),
        )
        resp = await client.post(
            f"/teams/{tid}/members", json={"user_id": "u2"},
            headers=_jwt("u1"),
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_list_members(self, client):
        r = await client.post("/teams", json={"name": "T"}, headers=_jwt("u1"))
        tid = r.json()["id"]
        await client.post(
            f"/teams/{tid}/members", json={"user_id": "u2"},
            headers=_jwt("u1"),
        )
        resp = await client.get(f"/teams/{tid}/members", headers=_jwt("u1"))
        assert len(resp.json()) == 2  # creator + u2

    @pytest.mark.asyncio
    async def test_remove_member(self, client):
        r = await client.post("/teams", json={"name": "T"}, headers=_jwt("u1"))
        tid = r.json()["id"]
        await client.post(
            f"/teams/{tid}/members", json={"user_id": "u2"},
            headers=_jwt("u1"),
        )
        resp = await client.delete(
            f"/teams/{tid}/members/u2", headers=_jwt("u1"),
        )
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_remove_member_not_found(self, client):
        r = await client.post("/teams", json={"name": "T"}, headers=_jwt("u1"))
        tid = r.json()["id"]
        resp = await client.delete(
            f"/teams/{tid}/members/u2", headers=_jwt("u1"),
        )
        assert resp.status_code == 404


class TestTeamRepoAccess:

    @pytest.mark.asyncio
    async def test_grant_repo_access(self, client):
        r = await client.post("/teams", json={"name": "T"}, headers=_jwt("u1"))
        tid = r.json()["id"]
        resp = await client.post(
            f"/teams/{tid}/repos",
            json={"repo_id": "r1", "level": "editor"},
            headers=_jwt("u1"),
        )
        assert resp.status_code == 201
        assert resp.json()["level"] == "editor"

    @pytest.mark.asyncio
    async def test_grant_invalid_level(self, client):
        r = await client.post("/teams", json={"name": "T"}, headers=_jwt("u1"))
        tid = r.json()["id"]
        resp = await client.post(
            f"/teams/{tid}/repos",
            json={"repo_id": "r1", "level": "superuser"},
            headers=_jwt("u1"),
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_list_team_repos(self, client):
        r = await client.post("/teams", json={"name": "T"}, headers=_jwt("u1"))
        tid = r.json()["id"]
        await client.post(
            f"/teams/{tid}/repos",
            json={"repo_id": "r1", "level": "viewer"},
            headers=_jwt("u1"),
        )
        resp = await client.get(f"/teams/{tid}/repos", headers=_jwt("u1"))
        assert len(resp.json()) == 1

    @pytest.mark.asyncio
    async def test_team_access_grants_repo_read(self, client):
        """Team member can access repo via team repo access."""
        r = await client.post("/teams", json={"name": "T"}, headers=_jwt("u1"))
        tid = r.json()["id"]
        # Add u2 to team
        await client.post(
            f"/teams/{tid}/members", json={"user_id": "u2"},
            headers=_jwt("u1"),
        )
        # Grant team access to r1
        await client.post(
            f"/teams/{tid}/repos",
            json={"repo_id": "r1", "level": "viewer"},
            headers=_jwt("u1"),
        )
        # u2 can now access r1 via team
        resp = await client.get("/repos/r1/status", headers=_jwt("u2"))
        assert resp.status_code == 200


class TestAppAdminBypass:

    @pytest.mark.asyncio
    async def test_admin_can_update_any_team(self, client):
        r = await client.post("/teams", json={"name": "T"}, headers=_jwt("u1"))
        tid = r.json()["id"]
        resp = await client.patch(
            f"/teams/{tid}", json={"name": "Admin Edit"},
            headers=_jwt("admin1"),
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Admin Edit"

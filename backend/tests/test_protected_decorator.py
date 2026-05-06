"""
Tests for RBAC Phase 3: Unified `protected()` permission decorator.

Verifies that the combined scope + role + repo ownership check works.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.auth.scopes import protected
from app.core.config import settings
from app.main import app
from app.storage.database import get_db
from app.storage.models import Repo, User, UserRole
from tests.conftest import create_tables, drop_tables, override_get_db

app.dependency_overrides[get_db] = override_get_db


# We'll add a temporary test endpoint that uses protected()
from fastapi import APIRouter, Depends  # noqa: E402

_test_router = APIRouter()


@_test_router.delete(
    "/test-protected/{repo_id}/action",
    dependencies=[Depends(protected(
        scope="delete:snapshots",
        roles=["admin", "employee", "user"],
        require_repo_owner=True,
    ))],
)
async def _test_endpoint(repo_id: str) -> dict:
    return {"ok": True}


@_test_router.get(
    "/test-protected/scope-only",
    dependencies=[Depends(protected(scope="admin:users"))],
)
async def _test_scope_only() -> dict:
    return {"ok": True}


@_test_router.post(
    "/test-protected/role-only",
    dependencies=[Depends(protected(roles=["admin", "superadmin"]))],
)
async def _test_role_only() -> dict:
    return {"ok": True}


@_test_router.get(
    "/test-protected/no-restrictions",
    dependencies=[Depends(protected())],
)
async def _test_no_restrictions() -> dict:
    return {"ok": True}


app.include_router(_test_router)


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await drop_tables()
    await create_tables()
    async for db in override_get_db():
        db.add(User(
            id="admin1", github_login="admin", name="Admin",
            email="a@x.com", avatar_url="", github_token_enc="",
            role=UserRole.admin,
        ))
        db.add(User(
            id="user1", github_login="user", name="User",
            email="u@x.com", avatar_url="", github_token_enc="",
            role=UserRole.user,
        ))
        db.add(User(
            id="support1", github_login="support", name="Support",
            email="s@x.com", avatar_url="", github_token_enc="",
            role=UserRole.support,
        ))
        db.add(Repo(id="r1", name="demo", url="http://x", owner_id="user1"))
        db.add(Repo(id="r2", name="other", url="http://y", owner_id="admin1"))
        await db.commit()
    yield
    await drop_tables()


def _jwt(user_id: str) -> dict:
    from app.auth.token_service import create_access_token
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


@pytest_asyncio.fixture
async def client():
    original = settings.auth_enabled
    settings.auth_enabled = True
    with patch("app.api.repos.run_ingestion", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    settings.auth_enabled = original


class TestProtectedScopeCheck:

    @pytest.mark.asyncio
    async def test_admin_has_scope(self, client):
        resp = await client.get(
            "/test-protected/scope-only", headers=_jwt("admin1"),
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_user_lacks_admin_scope(self, client):
        resp = await client.get(
            "/test-protected/scope-only", headers=_jwt("user1"),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_support_lacks_admin_scope(self, client):
        resp = await client.get(
            "/test-protected/scope-only", headers=_jwt("support1"),
        )
        assert resp.status_code == 403


class TestProtectedRoleCheck:

    @pytest.mark.asyncio
    async def test_admin_allowed(self, client):
        resp = await client.post(
            "/test-protected/role-only", headers=_jwt("admin1"),
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_user_blocked(self, client):
        resp = await client.post(
            "/test-protected/role-only", headers=_jwt("user1"),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_support_blocked(self, client):
        resp = await client.post(
            "/test-protected/role-only", headers=_jwt("support1"),
        )
        assert resp.status_code == 403


class TestProtectedRepoOwnership:

    @pytest.mark.asyncio
    async def test_owner_allowed(self, client):
        resp = await client.delete(
            "/test-protected/r1/action", headers=_jwt("user1"),
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_non_owner_blocked(self, client):
        resp = await client.delete(
            "/test-protected/r2/action", headers=_jwt("user1"),
        )
        assert resp.status_code == 404  # 404 to not leak existence

    @pytest.mark.asyncio
    async def test_admin_bypasses_ownership(self, client):
        resp = await client.delete(
            "/test-protected/r1/action", headers=_jwt("admin1"),
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_support_blocked_by_scope(self, client):
        # support doesn't have delete:snapshots scope
        resp = await client.delete(
            "/test-protected/r1/action", headers=_jwt("support1"),
        )
        assert resp.status_code == 403


class TestProtectedNoRestrictions:

    @pytest.mark.asyncio
    async def test_anyone_allowed(self, client):
        resp = await client.get(
            "/test-protected/no-restrictions", headers=_jwt("support1"),
        )
        assert resp.status_code == 200


class TestProtectedCombined:
    """Test the full combination: scope + role + ownership."""

    @pytest.mark.asyncio
    async def test_owner_with_correct_role_and_scope(self, client):
        # user1 owns r1, has user role (in allowed list), has delete:snapshots
        resp = await client.delete(
            "/test-protected/r1/action", headers=_jwt("user1"),
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_support_blocked_at_role_level(self, client):
        # support not in roles list ["admin", "employee", "user"]
        resp = await client.delete(
            "/test-protected/r1/action", headers=_jwt("support1"),
        )
        assert resp.status_code == 403

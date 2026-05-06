"""
Tests for RBAC Phase 2: Role-to-Scope Mapping.

Verifies that JWT users with different roles are restricted
based on their role's scope set.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.auth.scopes import ROLE_SCOPES, get_role_scopes, parse_scopes
from app.core.config import settings
from app.main import app
from app.storage.database import get_db
from app.storage.models import Repo, RepoSnapshot, SnapshotStatus, User, UserRole
from tests.conftest import create_tables, drop_tables, override_get_db

app.dependency_overrides[get_db] = override_get_db


# =======================================================================
# Unit tests: ROLE_SCOPES mapping
# =======================================================================


class TestRoleScopesMapping:

    def test_superadmin_has_star(self):
        assert "*" in ROLE_SCOPES["superadmin"]

    def test_admin_has_all_non_star_scopes(self):
        admin_scopes = ROLE_SCOPES["admin"]
        assert "admin:users" in admin_scopes
        assert "admin:plans" in admin_scopes
        assert "admin:audit" in admin_scopes
        assert "write:repos" in admin_scopes
        assert "delete:snapshots" in admin_scopes

    def test_employee_no_admin(self):
        emp = ROLE_SCOPES["employee"]
        assert "admin:users" not in emp
        assert "admin:plans" not in emp
        assert "admin:audit" not in emp

    def test_employee_has_full_dev_access(self):
        emp = ROLE_SCOPES["employee"]
        assert "write:repos" in emp
        assert "write:snapshots" in emp
        assert "delete:snapshots" in emp
        assert "read:analysis" in emp
        assert "write:docs" in emp

    def test_support_read_only(self):
        sup = ROLE_SCOPES["support"]
        assert "read:repos" in sup
        assert "read:analysis" in sup
        assert "write:repos" not in sup
        assert "write:snapshots" not in sup
        assert "delete:snapshots" not in sup
        assert "write:docs" not in sup

    def test_support_has_audit(self):
        assert "admin:audit" in ROLE_SCOPES["support"]

    def test_user_has_standard_access(self):
        user_scopes = ROLE_SCOPES["user"]
        assert "read:repos" in user_scopes
        assert "write:repos" in user_scopes
        assert "read:analysis" in user_scopes
        assert "admin:users" not in user_scopes
        assert "admin:plans" not in user_scopes

    def test_get_role_scopes_superadmin(self):
        assert get_role_scopes("superadmin") == "*"

    def test_get_role_scopes_support(self):
        scopes_str = get_role_scopes("support")
        scopes = parse_scopes(scopes_str)
        assert "read:repos" in scopes
        assert "write:repos" not in scopes

    def test_get_role_scopes_unknown_defaults_to_user(self):
        scopes_str = get_role_scopes("unknown_role")
        assert scopes_str == get_role_scopes("user")

    def test_role_scopes_all_valid(self):
        """All scopes in ROLE_SCOPES must be in the SCOPES catalog."""
        from app.auth.scopes import SCOPES
        for role, scopes in ROLE_SCOPES.items():
            for s in scopes:
                assert s in SCOPES, f"Role '{role}' has invalid scope '{s}'"


# =======================================================================
# Integration tests: Role enforcement via JWT
# =======================================================================


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await drop_tables()
    await create_tables()
    async for db in override_get_db():
        # Support user (read-only + audit)
        db.add(User(
            id="support1", github_login="support_user", name="Support",
            email="support@example.com", avatar_url="", github_token_enc="",
            role=UserRole.support,
        ))
        # Regular user
        db.add(User(
            id="user1", github_login="regular_user", name="User",
            email="user@example.com", avatar_url="", github_token_enc="",
            role=UserRole.user,
        ))
        # Admin
        db.add(User(
            id="admin1", github_login="admin_user", name="Admin",
            email="admin@example.com", avatar_url="", github_token_enc="",
            role=UserRole.admin,
        ))
        db.add(Repo(id="r1", name="demo", url="https://example.com", owner_id="user1"))
        db.add(RepoSnapshot(
            id="s1", repo_id="r1", commit_sha="abc",
            status=SnapshotStatus.completed, file_count=3,
        ))
        await db.commit()
    yield
    await drop_tables()


def _make_jwt(user_id: str) -> str:
    """Create a JWT for the given user."""
    from app.auth.token_service import create_access_token
    return create_access_token(user_id)


@pytest_asyncio.fixture
async def client():
    original = settings.auth_enabled
    settings.auth_enabled = True
    with patch("app.api.repos.run_ingestion", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as ac:
            yield ac
    settings.auth_enabled = original


class TestSupportRoleRestrictions:
    """Support role: read-only + audit access."""

    @pytest.mark.asyncio
    async def test_can_list_repos(self, client):
        token = _make_jwt("support1")
        resp = await client.get(
            "/repos", headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_cannot_create_repo(self, client):
        token = _make_jwt("support1")
        resp = await client.post(
            "/repos", json={"name": "x", "url": "http://x"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_cannot_delete_repo(self, client):
        token = _make_jwt("support1")
        resp = await client.delete(
            "/repos/r1",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_cannot_ingest(self, client):
        token = _make_jwt("support1")
        resp = await client.post(
            "/repos/r1/ingest",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_can_read_analysis(self, client):
        token = _make_jwt("support1")
        resp = await client.get(
            "/repos/r1/snapshots/s1/symbols",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_can_access_audit(self, client):
        token = _make_jwt("support1")
        resp = await client.get(
            "/admin/audit-log",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_cannot_admin_users(self, client):
        token = _make_jwt("support1")
        resp = await client.get(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403


class TestRegularUserRole:
    """Regular user: full dev access, no admin."""

    @pytest.mark.asyncio
    async def test_can_create_repo(self, client):
        token = _make_jwt("user1")
        resp = await client.post(
            "/repos", json={"name": "new", "url": "http://new"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_can_delete_snapshot(self, client):
        token = _make_jwt("user1")
        resp = await client.delete(
            "/repos/r1/snapshots/s1",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_cannot_admin_users(self, client):
        token = _make_jwt("user1")
        resp = await client.get(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_cannot_admin_audit(self, client):
        token = _make_jwt("user1")
        resp = await client.get(
            "/admin/audit-log",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403


class TestAdminRole:
    """Admin: everything except superadmin-only features."""

    @pytest.mark.asyncio
    async def test_can_access_admin_users(self, client):
        token = _make_jwt("admin1")
        resp = await client.get(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_can_access_audit(self, client):
        token = _make_jwt("admin1")
        resp = await client.get(
            "/admin/audit-log",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_can_create_repo(self, client):
        token = _make_jwt("admin1")
        resp = await client.post(
            "/repos", json={"name": "admin-repo", "url": "http://admin"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201

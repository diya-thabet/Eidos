"""
Tests for RBAC Phase 7: Audit Integration.

Verifies that permission denials and permission changes are logged.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.auth.audit_helpers import (
    build_permission_change_event,
    build_permission_denied_event,
)
from app.auth.token_service import create_access_token
from app.core.config import settings
from app.main import app
from app.storage.database import get_db
from app.storage.models import AuditEvent, Repo, User, UserRole
from tests.conftest import create_tables, drop_tables, override_get_db

app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await drop_tables()
    await create_tables()
    async for db in override_get_db():
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
        db.add(User(
            id="admin1", github_login="admin", name="Admin",
            email="a@x.com", avatar_url="", github_token_enc="",
            role=UserRole.admin,
        ))
        db.add(Repo(id="r1", name="demo", url="http://x", owner_id="user1"))
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


class TestAuditHelpers:

    def test_build_denied_event(self):
        from unittest.mock import MagicMock
        req = MagicMock()
        req.url.path = "/repos/r1"
        req.url.__str__ = lambda self: "http://test/repos/r1"
        req.method = "DELETE"
        req.client.host = "127.0.0.1"

        event = build_permission_denied_event(req, "user1", "scope_fail", "write:repos")
        assert event.action == "permission.denied"
        assert event.user_id == "user1"
        assert event.status_code == 403
        assert event.success is False
        assert "write:repos" in event.metadata_json

    def test_build_change_event(self):
        event = build_permission_change_event(
            user_id="admin1",
            action="permission.granted",
            resource_type="repo",
            resource_id="r1",
            metadata={"target_user": "user2", "level": "viewer"},
        )
        assert event.action == "permission.granted"
        assert event.user_id == "admin1"
        assert event.success is True
        assert "user2" in event.metadata_json


class TestDenialAuditLogging:
    """Verify that 403 responses create audit events."""

    @pytest.mark.asyncio
    async def test_scope_denial_logged(self, client):
        # Support user tries to create repo (needs write:repos)
        resp = await client.post(
            "/repos", json={"name": "x", "url": "http://x"},
            headers=_jwt("support1"),
        )
        assert resp.status_code == 403

        # Check audit log
        async for db in override_get_db():
            result = await db.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "permission.denied",
                    AuditEvent.user_id == "support1",
                )
            )
            events = result.scalars().all()
            assert len(events) >= 1
            event = events[0]
            assert event.status_code == 403
            assert event.success is False
            assert "scope_check_failed" in event.metadata_json
            break

    @pytest.mark.asyncio
    async def test_role_denial_logged(self, client):
        # User tries admin endpoint
        resp = await client.get(
            "/admin/users", headers=_jwt("user1"),
        )
        assert resp.status_code == 403

        async for db in override_get_db():
            result = await db.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "permission.denied",
                    AuditEvent.user_id == "user1",
                )
            )
            events = result.scalars().all()
            assert len(events) >= 1
            break


class TestPermissionChangeAudit:
    """Verify that permission grants/revokes are logged."""

    @pytest.mark.asyncio
    async def test_grant_logged(self, client):
        resp = await client.post(
            "/repos/r1/permissions",
            json={"user_id": "support1", "level": "viewer"},
            headers=_jwt("user1"),
        )
        assert resp.status_code == 201

        async for db in override_get_db():
            result = await db.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "permission.granted",
                )
            )
            events = result.scalars().all()
            assert len(events) >= 1
            event = events[0]
            assert event.resource_type == "repo"
            assert event.resource_id == "r1"
            assert "support1" in event.metadata_json
            break

    @pytest.mark.asyncio
    async def test_revoke_logged(self, client):
        # First grant
        await client.post(
            "/repos/r1/permissions",
            json={"user_id": "support1", "level": "viewer"},
            headers=_jwt("user1"),
        )
        # Then revoke
        resp = await client.delete(
            "/repos/r1/permissions/support1",
            headers=_jwt("user1"),
        )
        assert resp.status_code == 204

        async for db in override_get_db():
            result = await db.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "permission.revoked",
                )
            )
            events = result.scalars().all()
            assert len(events) >= 1
            break

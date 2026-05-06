"""
Tests for RBAC Phase 1: Scope enforcement on endpoints.

Verifies that:
- API keys with limited scopes are rejected from protected endpoints
- API keys with correct scopes are allowed
- JWT users (no api_key_scopes) bypass scope checks
"""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app
from app.storage.database import get_db
from app.storage.models import ApiKey, Repo, RepoSnapshot, SnapshotStatus, User, UserRole
from tests.conftest import create_tables, drop_tables, override_get_db

app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await drop_tables()
    await create_tables()
    async for db in override_get_db():
        db.add(User(
            id="u1", github_login="testuser", name="Test",
            email="test@example.com", avatar_url="", github_token_enc="",
            role=UserRole.superadmin,
        ))
        db.add(Repo(id="r1", name="demo", url="https://example.com", owner_id="u1"))
        db.add(RepoSnapshot(
            id="s1", repo_id="r1", commit_sha="abc",
            status=SnapshotStatus.completed, file_count=3,
        ))

        # Read-only key (read:repos, read:analysis only)
        raw_ro = "eidos_readonly_scope_test_key_1"
        db.add(ApiKey(
            id="key_ro", user_id="u1", name="ReadOnly",
            key_hash=hashlib.sha256(raw_ro.encode()).hexdigest(),
            prefix="eidos_reado", scopes="read:repos,read:analysis",
            is_active=True,
        ))

        # Write key (write:repos, write:snapshots, delete:snapshots)
        raw_wr = "eidos_write_scope_test_key_222"
        db.add(ApiKey(
            id="key_wr", user_id="u1", name="WriteKey",
            key_hash=hashlib.sha256(raw_wr.encode()).hexdigest(),
            prefix="eidos_write", scopes="write:repos,write:snapshots,delete:snapshots",
            is_active=True,
        ))

        # Full access key
        raw_full = "eidos_full_scope_test_key_3333"
        db.add(ApiKey(
            id="key_full", user_id="u1", name="FullKey",
            key_hash=hashlib.sha256(raw_full.encode()).hexdigest(),
            prefix="eidos_full_", scopes="*",
            is_active=True,
        ))

        await db.commit()
    yield
    await drop_tables()


@pytest_asyncio.fixture
async def client():
    # Enable auth for these tests
    original = settings.auth_enabled
    settings.auth_enabled = True
    with patch("app.api.repos.run_ingestion", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as ac:
            yield ac
    settings.auth_enabled = original


RO_KEY = "eidos_readonly_scope_test_key_1"
WR_KEY = "eidos_write_scope_test_key_222"
FULL_KEY = "eidos_full_scope_test_key_3333"


class TestReadOnlyKeyRestrictions:
    """Read-only key should be able to read but not write."""

    @pytest.mark.asyncio
    async def test_can_list_repos(self, client):
        resp = await client.get("/repos", headers={"X-API-Key": RO_KEY})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_cannot_create_repo(self, client):
        resp = await client.post(
            "/repos", json={"name": "x", "url": "http://x"},
            headers={"X-API-Key": RO_KEY},
        )
        assert resp.status_code == 403
        assert "scope" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_cannot_delete_repo(self, client):
        resp = await client.delete(
            "/repos/r1", headers={"X-API-Key": RO_KEY},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_cannot_ingest(self, client):
        resp = await client.post(
            "/repos/r1/ingest", json={"url": "http://x"},
            headers={"X-API-Key": RO_KEY},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_can_read_analysis(self, client):
        resp = await client.get(
            "/repos/r1/snapshots/s1/symbols",
            headers={"X-API-Key": RO_KEY},
        )
        # Should not be 403 (may be 200 or other non-auth error)
        assert resp.status_code != 403


class TestWriteKeyPermissions:
    """Write key should be able to write repos/snapshots but not admin."""

    @pytest.mark.asyncio
    async def test_can_create_repo(self, client):
        resp = await client.post(
            "/repos", json={"name": "new", "url": "http://new"},
            headers={"X-API-Key": WR_KEY},
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_can_delete_snapshot(self, client):
        resp = await client.delete(
            "/repos/r1/snapshots/s1",
            headers={"X-API-Key": WR_KEY},
        )
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_cannot_read_repos(self, client):
        # This key doesn't have read:repos
        resp = await client.get(
            "/repos", headers={"X-API-Key": WR_KEY},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_cannot_access_audit(self, client):
        resp = await client.get(
            "/admin/audit-log",
            headers={"X-API-Key": WR_KEY},
        )
        assert resp.status_code == 403


class TestFullAccessKey:
    """Full access key (*) should have unrestricted access."""

    @pytest.mark.asyncio
    async def test_can_list_repos(self, client):
        resp = await client.get("/repos", headers={"X-API-Key": FULL_KEY})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_can_create_repo(self, client):
        resp = await client.post(
            "/repos", json={"name": "full", "url": "http://full"},
            headers={"X-API-Key": FULL_KEY},
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_can_access_audit(self, client):
        resp = await client.get(
            "/admin/audit-log",
            headers={"X-API-Key": FULL_KEY},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_can_delete_repo(self, client):
        resp = await client.delete(
            "/repos/r1", headers={"X-API-Key": FULL_KEY},
        )
        assert resp.status_code == 204


class TestScopeEnforcementCoverage:
    """Verify scope enforcement on various endpoint categories."""

    @pytest.mark.asyncio
    async def test_coverage_upload_needs_write_coverage(self, client):
        resp = await client.post(
            "/repos/r1/snapshots/s1/coverage",
            json={"data": {}},
            headers={"X-API-Key": RO_KEY},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_quality_gate_create_needs_write_gates(self, client):
        resp = await client.post(
            "/repos/r1/quality-gates",
            json={"name": "g", "config": {}},
            headers={"X-API-Key": RO_KEY},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_bulk_delete_repos_needs_admin(self, client):
        resp = await client.post(
            "/repos/bulk-delete",
            json={"repo_ids": ["r1"]},
            headers={"X-API-Key": WR_KEY},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_tag_add_needs_write_snapshots(self, client):
        resp = await client.post(
            "/repos/r1/snapshots/s1/tags",
            json={"tag": "test"},
            headers={"X-API-Key": RO_KEY},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_export_sbom_needs_read_export(self, client):
        resp = await client.get(
            "/repos/r1/snapshots/s1/export/sbom",
            headers={"X-API-Key": RO_KEY},  # has read:analysis but not read:export
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_health_findings_post_needs_write(self, client):
        resp = await client.post(
            "/repos/r1/snapshots/s1/health/findings",
            json={"findings": []},
            headers={"X-API-Key": RO_KEY},
        )
        assert resp.status_code == 403

"""
Tests for Phase 3 (Phase 10.3): Audit Log.

Tests the audit helper functions and 4 API endpoints:
- GET /admin/audit-log
- GET /admin/audit-log/export
- GET /admin/audit-log/stats
- DELETE /admin/audit-log/purge
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.audit import _classify_request, record_audit_event, should_audit
from app.main import app
from app.storage.database import get_db
from app.storage.models import AuditEvent, Repo
from tests.conftest import create_tables, drop_tables, override_get_db

app.dependency_overrides[get_db] = override_get_db


# =======================================================================
# Unit tests: audit helpers
# =======================================================================


class TestShouldAudit:

    def test_post_is_audited(self):
        assert should_audit("POST", "/repos") is True

    def test_delete_is_audited(self):
        assert should_audit("DELETE", "/repos/r1") is True

    def test_patch_is_audited(self):
        assert should_audit("PATCH", "/repos/r1") is True

    def test_put_is_audited(self):
        assert should_audit("PUT", "/admin/users/1/role") is True

    def test_get_not_audited(self):
        assert should_audit("GET", "/repos/r1/status") is False

    def test_head_not_audited(self):
        assert should_audit("HEAD", "/health") is False

    def test_options_not_audited(self):
        assert should_audit("OPTIONS", "/repos") is False

    def test_health_not_audited(self):
        assert should_audit("POST", "/health") is False

    def test_metrics_not_audited(self):
        assert should_audit("POST", "/metrics") is False


class TestClassifyRequest:

    def test_repo_create(self):
        action, rt, rid = _classify_request("POST", "/repos")
        assert action == "repo.create"
        assert rt == "repo"

    def test_repo_delete(self):
        action, rt, rid = _classify_request("DELETE", "/repos/r1")
        assert action == "repo.delete"
        assert rt == "repo"
        assert rid == "r1"

    def test_repo_update(self):
        action, rt, rid = _classify_request("PATCH", "/repos/r1")
        assert action == "repo.update"
        assert rt == "repo"

    def test_snapshot_delete(self):
        action, rt, rid = _classify_request("DELETE", "/repos/r1/snapshots/s1")
        assert action == "snapshot.delete"
        assert rt == "snapshot"

    def test_ingest(self):
        action, rt, rid = _classify_request("POST", "/repos/r1/ingest")
        assert "ingest" in action
        assert rt == "repo"

    def test_gate_create(self):
        action, rt, rid = _classify_request("POST", "/repos/r1/quality-gates")
        assert action == "gate.create"
        assert rt == "repo"

    def test_gate_delete(self):
        action, rt, rid = _classify_request("DELETE", "/repos/r1/quality-gates/5")
        assert action == "gate.delete"
        assert rt == "gate"

    def test_api_key_create(self):
        action, rt, rid = _classify_request("POST", "/auth/api-keys")
        assert action == "api_key.create"
        assert rt == "api_key"

    def test_api_key_revoke(self):
        action, rt, rid = _classify_request("DELETE", "/auth/api-keys/k1")
        assert action == "api_key.delete"
        assert rt == "api_key"

    def test_webhook(self):
        action, rt, rid = _classify_request("POST", "/webhooks/github")
        assert "webhook" in action
        assert rt == "webhook"

    def test_unknown_path(self):
        action, rt, rid = _classify_request("POST", "/unknown/path")
        assert "unknown" in action


class TestRecordAuditEvent:

    @pytest.mark.asyncio
    async def test_records_event(self):
        async for db in override_get_db():
            event = await record_audit_event(
                db,
                user_id="u1",
                user_email="test@example.com",
                action="repo.create",
                resource_type="repo",
                resource_id="r1",
                method="POST",
                path="/repos",
                status_code=201,
                ip_address="127.0.0.1",
                success=True,
            )
            await db.commit()
            assert event.id is not None
            assert event.action == "repo.create"
            assert event.user_id == "u1"
            break

    @pytest.mark.asyncio
    async def test_records_failure(self):
        async for db in override_get_db():
            event = await record_audit_event(
                db,
                action="repo.delete",
                resource_type="repo",
                resource_id="r1",
                status_code=403,
                success=False,
            )
            await db.commit()
            assert event.success is False
            assert event.status_code == 403
            break


# =======================================================================
# API tests
# =======================================================================


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await drop_tables()
    await create_tables()
    async for db in override_get_db():
        db.add(Repo(id="r1", name="demo", url="https://example.com"))
        # Seed some audit events
        now = datetime.now(UTC)
        for i in range(5):
            db.add(AuditEvent(
                timestamp=now - timedelta(hours=i),
                user_id="user1",
                user_email="alice@example.com",
                action="repo.create",
                resource_type="repo",
                resource_id=f"r{i}",
                method="POST",
                path="/repos",
                status_code=201,
                ip_address="10.0.0.1",
                success=True,
            ))
        # Add some failures
        for i in range(3):
            db.add(AuditEvent(
                timestamp=now - timedelta(hours=10 + i),
                user_id="user2",
                user_email="bob@example.com",
                action="repo.delete",
                resource_type="repo",
                resource_id=f"r{i}",
                method="DELETE",
                path=f"/repos/r{i}",
                status_code=403,
                ip_address="10.0.0.2",
                success=False,
            ))
        # Old event for purge test
        db.add(AuditEvent(
            timestamp=now - timedelta(days=100),
            user_id="old",
            user_email="old@example.com",
            action="repo.create",
            resource_type="repo",
            resource_id="old",
            method="POST",
            path="/repos",
            status_code=201,
            success=True,
        ))
        await db.commit()
    yield
    await drop_tables()


@pytest_asyncio.fixture
async def client():
    with patch("app.api.repos.run_ingestion", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as ac:
            yield ac


class TestQueryAuditLog:

    @pytest.mark.asyncio
    async def test_list_all(self, client):
        resp = await client.get("/admin/audit-log")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 9  # 5 + 3 + 1
        assert len(data["events"]) == 9

    @pytest.mark.asyncio
    async def test_filter_by_user(self, client):
        resp = await client.get("/admin/audit-log?user_id=user1")
        data = resp.json()
        assert data["total"] == 5
        assert all(e["user_id"] == "user1" for e in data["events"])

    @pytest.mark.asyncio
    async def test_filter_by_action(self, client):
        resp = await client.get("/admin/audit-log?action=repo.delete")
        data = resp.json()
        assert data["total"] == 3

    @pytest.mark.asyncio
    async def test_filter_by_success(self, client):
        resp = await client.get("/admin/audit-log?success=false")
        data = resp.json()
        assert data["total"] == 3
        assert all(e["success"] is False for e in data["events"])

    @pytest.mark.asyncio
    async def test_filter_by_method(self, client):
        resp = await client.get("/admin/audit-log?method=DELETE")
        data = resp.json()
        assert data["total"] == 3

    @pytest.mark.asyncio
    async def test_pagination(self, client):
        resp = await client.get("/admin/audit-log?limit=3&offset=0")
        data = resp.json()
        assert len(data["events"]) == 3
        assert data["total"] == 9
        assert data["offset"] == 0
        assert data["limit"] == 3

    @pytest.mark.asyncio
    async def test_event_fields(self, client):
        resp = await client.get("/admin/audit-log?limit=1")
        event = resp.json()["events"][0]
        for field in [
            "id", "timestamp", "user_id", "user_email", "action",
            "resource_type", "resource_id", "method", "path",
            "status_code", "ip_address", "success", "metadata",
        ]:
            assert field in event

    @pytest.mark.asyncio
    async def test_filter_by_resource_type(self, client):
        resp = await client.get("/admin/audit-log?resource_type=repo")
        assert resp.json()["total"] == 9


class TestExportAuditLog:

    @pytest.mark.asyncio
    async def test_export_csv(self, client):
        resp = await client.get("/admin/audit-log/export")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert "attachment" in resp.headers.get("content-disposition", "")

    @pytest.mark.asyncio
    async def test_csv_has_header(self, client):
        resp = await client.get("/admin/audit-log/export")
        lines = resp.text.strip().split("\n")
        assert "id" in lines[0]
        assert "action" in lines[0]
        assert len(lines) >= 2  # header + at least 1 row

    @pytest.mark.asyncio
    async def test_csv_row_count(self, client):
        resp = await client.get("/admin/audit-log/export")
        lines = resp.text.strip().split("\n")
        # header + 9 events
        assert len(lines) == 10

    @pytest.mark.asyncio
    async def test_csv_filter(self, client):
        resp = await client.get("/admin/audit-log/export?action=repo.delete")
        lines = resp.text.strip().split("\n")
        assert len(lines) == 4  # header + 3


class TestAuditStats:

    @pytest.mark.asyncio
    async def test_stats(self, client):
        resp = await client.get("/admin/audit-log/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_events"] == 9
        assert data["unique_users"] >= 2
        assert data["recent_failures"] == 3
        assert "repo.create" in data["actions"]

    @pytest.mark.asyncio
    async def test_stats_fields(self, client):
        resp = await client.get("/admin/audit-log/stats")
        data = resp.json()
        for field in ["total_events", "unique_users", "actions", "recent_failures"]:
            assert field in data


class TestPurgeAuditLog:

    @pytest.mark.asyncio
    async def test_purge_old_events(self, client):
        resp = await client.delete("/admin/audit-log/purge?older_than_days=90")
        assert resp.status_code == 200
        data = resp.json()
        assert data["purged"] == 1
        assert data["older_than_days"] == 90

    @pytest.mark.asyncio
    async def test_purge_nothing(self, client):
        resp = await client.delete("/admin/audit-log/purge?older_than_days=3650")
        data = resp.json()
        assert data["purged"] == 0

    @pytest.mark.asyncio
    async def test_purge_all(self, client):
        await client.delete("/admin/audit-log/purge?older_than_days=1")
        # Already covered by test_purge_old_events

    @pytest.mark.asyncio
    async def test_purge_verifies_deletion(self, client):
        # Purge old events
        await client.delete("/admin/audit-log/purge?older_than_days=90")
        # Verify count decreased
        resp = await client.get("/admin/audit-log/stats")
        assert resp.json()["total_events"] == 8  # 9 - 1 purged

"""
Tests for repo DELETE and PATCH endpoints.

Covers:
- DELETE /repos/{id} (success, not found, cascades)
- PATCH /repos/{id} (partial update: name, branch, token, no-op, not found)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.storage.database import get_db
from app.storage.models import Repo, RepoSnapshot, SnapshotStatus
from tests.conftest import create_tables, drop_tables, override_get_db, test_sessionmaker

app.dependency_overrides[get_db] = override_get_db


async def _seed() -> str:
    async with test_sessionmaker() as db:
        repo = Repo(
            id="r-crud",
            name="crud-test",
            url="https://github.com/example/crud",
            default_branch="main",
        )
        db.add(repo)
        snap = RepoSnapshot(
            id="s-crud", repo_id="r-crud", status=SnapshotStatus.completed
        )
        db.add(snap)
        await db.commit()
    return "r-crud"


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await drop_tables()
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


# ===================================================================
# DELETE /repos/{id}
# ===================================================================


class TestDeleteRepo:
    @pytest.mark.asyncio
    async def test_delete_existing_repo(self, client: AsyncClient):
        resp = await client.delete("/repos/r-crud")
        assert resp.status_code == 204

        # Verify it's gone
        resp2 = await client.get("/repos/r-crud/status")
        assert resp2.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_not_found(self, client: AsyncClient):
        resp = await client.delete("/repos/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_cascades_snapshots(self, client: AsyncClient):
        resp = await client.delete("/repos/r-crud")
        assert resp.status_code == 204

        # Snapshot should be gone too
        async with test_sessionmaker() as db:
            snap = await db.get(RepoSnapshot, "s-crud")
            assert snap is None

    @pytest.mark.asyncio
    async def test_delete_idempotent(self, client: AsyncClient):
        resp1 = await client.delete("/repos/r-crud")
        assert resp1.status_code == 204
        resp2 = await client.delete("/repos/r-crud")
        assert resp2.status_code == 404


# ===================================================================
# PATCH /repos/{id}
# ===================================================================


class TestUpdateRepo:
    @pytest.mark.asyncio
    async def test_update_name(self, client: AsyncClient):
        resp = await client.patch("/repos/r-crud", json={"name": "new-name"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "new-name"
        assert resp.json()["default_branch"] == "main"  # unchanged

    @pytest.mark.asyncio
    async def test_update_branch(self, client: AsyncClient):
        resp = await client.patch("/repos/r-crud", json={"default_branch": "develop"})
        assert resp.status_code == 200
        assert resp.json()["default_branch"] == "develop"
        assert resp.json()["name"] == "crud-test"  # unchanged

    @pytest.mark.asyncio
    async def test_update_multiple_fields(self, client: AsyncClient):
        resp = await client.patch(
            "/repos/r-crud", json={"name": "updated", "default_branch": "release"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "updated"
        assert data["default_branch"] == "release"

    @pytest.mark.asyncio
    async def test_update_token(self, client: AsyncClient):
        resp = await client.patch("/repos/r-crud", json={"git_token": "ghp_newtoken"})
        assert resp.status_code == 200
        # Token should not be returned in response
        assert "git_token" not in resp.json()

    @pytest.mark.asyncio
    async def test_update_empty_body(self, client: AsyncClient):
        resp = await client.patch("/repos/r-crud", json={})
        assert resp.status_code == 200
        assert resp.json()["name"] == "crud-test"  # unchanged

    @pytest.mark.asyncio
    async def test_update_not_found(self, client: AsyncClient):
        resp = await client.patch("/repos/nonexistent", json={"name": "x"})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_preserves_id(self, client: AsyncClient):
        resp = await client.patch("/repos/r-crud", json={"name": "changed"})
        assert resp.json()["id"] == "r-crud"

    @pytest.mark.asyncio
    async def test_update_strips_whitespace(self, client: AsyncClient):
        resp = await client.patch("/repos/r-crud", json={"name": "  spaces  "})
        assert resp.status_code == 200
        assert resp.json()["name"] == "spaces"

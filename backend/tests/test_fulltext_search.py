"""
Tests for PostgreSQL full-text search endpoint (P3.13).

Tests the ILIKE fallback since tests run on SQLite.

Covers:
- /fulltext endpoint returns results
- Fallback to ILIKE on non-PostgreSQL
- _is_postgresql detection
- Empty query handling
- Result structure
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api.search import _ilike_fulltext_search, _is_postgresql
from app.main import app
from app.storage.database import get_db
from app.storage.models import (
    Repo,
    RepoSnapshot,
    SnapshotStatus,
    Symbol,
)
from tests.conftest import create_tables, drop_tables, override_get_db, test_sessionmaker

app.dependency_overrides[get_db] = override_get_db


async def _seed_search_data() -> None:
    async with test_sessionmaker() as db:
        db.add(Repo(id="r-fts", name="fts-repo", url="https://example.com/fts"))
        db.add(RepoSnapshot(
            id="s-fts", repo_id="r-fts", status=SnapshotStatus.completed,
            file_count=2,
        ))
        db.add(Symbol(
            snapshot_id="s-fts", name="UserService", kind="class",
            fq_name="app.UserService", file_path="user.py",
            start_line=1, end_line=50, signature="class UserService:",
        ))
        db.add(Symbol(
            snapshot_id="s-fts", name="OrderProcessor", kind="class",
            fq_name="app.OrderProcessor", file_path="order.py",
            start_line=1, end_line=30, signature="class OrderProcessor:",
        ))
        db.add(Symbol(
            snapshot_id="s-fts", name="process_order", kind="method",
            fq_name="app.OrderProcessor.process_order", file_path="order.py",
            start_line=10, end_line=25, signature="def process_order(self, order_id):",
        ))
        await db.commit()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await drop_tables()
    await create_tables()
    await _seed_search_data()
    yield
    await drop_tables()


@pytest_asyncio.fixture
async def client():
    with patch("app.api.repos.run_ingestion", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


class TestFulltextEndpoint:
    @pytest.mark.asyncio
    async def test_returns_200(self, client: AsyncClient):
        resp = await client.get("/repos/r-fts/snapshots/s-fts/fulltext?q=User")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_finds_matching_symbol(self, client: AsyncClient):
        resp = await client.get("/repos/r-fts/snapshots/s-fts/fulltext?q=UserService")
        data = resp.json()
        assert data["total"] >= 1
        names = [item["entity_id"] for item in data["items"]]
        assert "app.UserService" in names

    @pytest.mark.asyncio
    async def test_partial_match(self, client: AsyncClient):
        resp = await client.get("/repos/r-fts/snapshots/s-fts/fulltext?q=Order")
        data = resp.json()
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_no_results_for_unmatched(self, client: AsyncClient):
        resp = await client.get("/repos/r-fts/snapshots/s-fts/fulltext?q=zzzznonexistent")
        data = resp.json()
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_result_structure(self, client: AsyncClient):
        resp = await client.get("/repos/r-fts/snapshots/s-fts/fulltext?q=process")
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert "has_more" in data
        if data["items"]:
            item = data["items"][0]
            assert "entity_type" in item
            assert "entity_id" in item
            assert "title" in item
            assert "score" in item

    @pytest.mark.asyncio
    async def test_respects_limit(self, client: AsyncClient):
        resp = await client.get("/repos/r-fts/snapshots/s-fts/fulltext?q=app&limit=1")
        data = resp.json()
        assert len(data["items"]) <= 1

    @pytest.mark.asyncio
    async def test_invalid_snapshot_404(self, client: AsyncClient):
        resp = await client.get("/repos/r-fts/snapshots/nonexistent/fulltext?q=test")
        assert resp.status_code == 404


class TestIsPostgresql:
    @pytest.mark.asyncio
    async def test_sqlite_returns_false(self):
        async with test_sessionmaker() as db:
            assert _is_postgresql(db) is False


class TestIlikeFallback:
    @pytest.mark.asyncio
    async def test_ilike_finds_symbols(self):
        async with test_sessionmaker() as db:
            hits = await _ilike_fulltext_search(db, "s-fts", "User", 50)
        assert len(hits) >= 1
        assert any("UserService" in h.entity_id for h in hits)

    @pytest.mark.asyncio
    async def test_ilike_no_match(self):
        async with test_sessionmaker() as db:
            hits = await _ilike_fulltext_search(db, "s-fts", "zzzzz", 50)
        assert len(hits) == 0

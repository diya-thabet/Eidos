"""
Tests for the indexing API endpoints.

Covers: summary listing, filtering, individual summary retrieval,
and error handling.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.storage.database import get_db
from app.storage.models import Repo, RepoSnapshot, SnapshotStatus, Summary
from tests.conftest import create_tables, drop_tables, override_get_db, test_sessionmaker

app.dependency_overrides[get_db] = override_get_db


async def _seed_data() -> None:
    async with test_sessionmaker() as db:
        db.add(
            Repo(id="repo-idx", name="test", url="https://example.com/test", default_branch="main")
        )
        db.add(
            RepoSnapshot(
                id="snap-idx", repo_id="repo-idx", commit_sha="abc", status=SnapshotStatus.completed
            )
        )
        await db.flush()

        db.add(
            Summary(
                snapshot_id="snap-idx",
                scope_type="symbol",
                scope_id="MyApp.Foo",
                summary_json=json.dumps(
                    {
                        "fq_name": "MyApp.Foo",
                        "kind": "class",
                        "purpose": "Test class.",
                        "citations": [{"file_path": "Foo.cs", "start_line": 1, "end_line": 10}],
                        "confidence": "high",
                    }
                ),
            )
        )
        db.add(
            Summary(
                snapshot_id="snap-idx",
                scope_type="symbol",
                scope_id="MyApp.Foo.Bar",
                summary_json=json.dumps(
                    {
                        "fq_name": "MyApp.Foo.Bar",
                        "kind": "method",
                        "purpose": "Test method.",
                        "citations": [{"file_path": "Foo.cs", "start_line": 5, "end_line": 8}],
                        "confidence": "medium",
                    }
                ),
            )
        )
        db.add(
            Summary(
                snapshot_id="snap-idx",
                scope_type="module",
                scope_id="MyApp",
                summary_json=json.dumps(
                    {
                        "name": "MyApp",
                        "purpose": "Main module.",
                        "key_classes": ["MyApp.Foo"],
                        "citations": [{"file_path": "Foo.cs"}],
                        "confidence": "high",
                    }
                ),
            )
        )
        db.add(
            Summary(
                snapshot_id="snap-idx",
                scope_type="file",
                scope_id="Foo.cs",
                summary_json=json.dumps(
                    {
                        "path": "Foo.cs",
                        "purpose": "Defines Foo.",
                        "symbols": ["MyApp.Foo"],
                        "citations": [{"file_path": "Foo.cs"}],
                        "confidence": "high",
                    }
                ),
            )
        )
        await db.commit()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await create_tables()
    await _seed_data()
    yield
    await drop_tables()


@pytest_asyncio.fixture
async def client():
    with patch("app.api.repos.run_ingestion", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


class TestListSummaries:
    @pytest.mark.asyncio
    async def test_list_all(self, client):
        resp = await client.get("/repos/repo-idx/snapshots/snap-idx/summaries")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 4
        assert len(data["items"]) == 4

    @pytest.mark.asyncio
    async def test_filter_by_scope_type(self, client):
        resp = await client.get("/repos/repo-idx/snapshots/snap-idx/summaries?scope_type=symbol")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert all(s["scope_type"] == "symbol" for s in data["items"])

    @pytest.mark.asyncio
    async def test_filter_by_scope_id(self, client):
        resp = await client.get("/repos/repo-idx/snapshots/snap-idx/summaries?scope_id=MyApp.Foo")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["scope_id"] == "MyApp.Foo"

    @pytest.mark.asyncio
    async def test_pagination(self, client):
        resp = await client.get("/repos/repo-idx/snapshots/snap-idx/summaries?limit=2&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total"] == 4
        assert data["has_more"] is True

    @pytest.mark.asyncio
    async def test_snapshot_not_found(self, client):
        resp = await client.get("/repos/repo-idx/snapshots/nonexistent/summaries")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_summary_json_parsed(self, client):
        resp = await client.get(
            "/repos/repo-idx/snapshots/snap-idx/summaries?scope_type=symbol&scope_id=MyApp.Foo"
        )
        data = resp.json()
        assert data["items"][0]["summary"]["purpose"] == "Test class."
        assert data["items"][0]["summary"]["confidence"] == "high"


class TestGetSummary:
    @pytest.mark.asyncio
    async def test_get_symbol_summary(self, client):
        resp = await client.get("/repos/repo-idx/snapshots/snap-idx/summaries/symbol/MyApp.Foo")
        assert resp.status_code == 200
        data = resp.json()
        assert data["scope_type"] == "symbol"
        assert data["summary"]["fq_name"] == "MyApp.Foo"

    @pytest.mark.asyncio
    async def test_get_module_summary(self, client):
        resp = await client.get("/repos/repo-idx/snapshots/snap-idx/summaries/module/MyApp")
        assert resp.status_code == 200
        assert resp.json()["summary"]["name"] == "MyApp"

    @pytest.mark.asyncio
    async def test_get_file_summary(self, client):
        resp = await client.get("/repos/repo-idx/snapshots/snap-idx/summaries/file/Foo.cs")
        assert resp.status_code == 200
        assert resp.json()["summary"]["path"] == "Foo.cs"

    @pytest.mark.asyncio
    async def test_not_found(self, client):
        resp = await client.get("/repos/repo-idx/snapshots/snap-idx/summaries/symbol/Nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_summary_has_citations(self, client):
        resp = await client.get("/repos/repo-idx/snapshots/snap-idx/summaries/symbol/MyApp.Foo")
        data = resp.json()
        citations = data["summary"]["citations"]
        assert len(citations) >= 1
        assert citations[0]["file_path"] == "Foo.cs"

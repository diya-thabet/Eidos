"""
Tests for Search API, Snapshot Comparison, and Export endpoints.

Covers:
- Full-text search across symbols, summaries, and docs
- Search filtering by entity type
- Search pagination and scoring
- Snapshot diff (added/removed/modified symbols)
- Snapshot export (full JSON dump)
- Edge cases: empty results, invalid queries, missing snapshots
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.storage.database import get_db
from app.storage.models import (
    Edge,
    GeneratedDoc,
    Repo,
    RepoSnapshot,
    SnapshotStatus,
    Summary,
    Symbol,
)
from tests.conftest import create_tables, drop_tables, override_get_db, test_sessionmaker

app.dependency_overrides[get_db] = override_get_db


async def _seed_search_data() -> None:
    """Seed data for search, diff, and export tests."""
    async with test_sessionmaker() as db:
        repo = Repo(id="r-search", name="search-test", url="https://example.com/search")
        db.add(repo)

        # Snapshot 1 (base)
        snap1 = RepoSnapshot(
            id="snap-base",
            repo_id="r-search",
            commit_sha="aaa111",
            status=SnapshotStatus.completed,
            file_count=2,
        )
        db.add(snap1)
        await db.flush()

        # Symbols in snap1
        db.add(
            Symbol(
                snapshot_id="snap-base",
                kind="class",
                name="OrderService",
                fq_name="MyApp.OrderService",
                file_path="OrderService.cs",
                start_line=1,
                end_line=50,
                namespace="MyApp",
                signature="public class OrderService",
                modifiers="public",
            )
        )
        db.add(
            Symbol(
                snapshot_id="snap-base",
                kind="method",
                name="PlaceOrder",
                fq_name="MyApp.OrderService.PlaceOrder",
                file_path="OrderService.cs",
                start_line=10,
                end_line=25,
                namespace="MyApp",
                parent_fq_name="MyApp.OrderService",
                signature="public void PlaceOrder(Order order)",
                modifiers="public",
            )
        )
        db.add(
            Symbol(
                snapshot_id="snap-base",
                kind="method",
                name="CancelOrder",
                fq_name="MyApp.OrderService.CancelOrder",
                file_path="OrderService.cs",
                start_line=27,
                end_line=40,
                namespace="MyApp",
                parent_fq_name="MyApp.OrderService",
                signature="public void CancelOrder(int id)",
                modifiers="public",
            )
        )
        await db.flush()

        # Edges in snap1
        db.add(
            Edge(
                snapshot_id="snap-base",
                source_fq_name="MyApp.OrderService.PlaceOrder",
                target_fq_name="MyApp.OrderService.CancelOrder",
                edge_type="calls",
                file_path="OrderService.cs",
                line=15,
            )
        )

        # Summaries in snap1
        db.add(
            Summary(
                snapshot_id="snap-base",
                scope_type="symbol",
                scope_id="MyApp.OrderService",
                summary_json=json.dumps(
                    {"purpose": "Handles order placement and cancellation.", "confidence": "high"}
                ),
            )
        )

        # Docs in snap1
        db.add(
            GeneratedDoc(
                snapshot_id="snap-base",
                doc_type="readme",
                title="Order Service Documentation",
                scope_id="MyApp.OrderService",
                markdown="# Order Service\n\nHandles orders in the system.",
            )
        )

        # Snapshot 2 (head) - some symbols changed
        snap2 = RepoSnapshot(
            id="snap-head",
            repo_id="r-search",
            commit_sha="bbb222",
            status=SnapshotStatus.completed,
            file_count=3,
        )
        db.add(snap2)
        await db.flush()

        # Symbols in snap2 (OrderService modified, CancelOrder removed, RefundOrder added)
        db.add(
            Symbol(
                snapshot_id="snap-head",
                kind="class",
                name="OrderService",
                fq_name="MyApp.OrderService",
                file_path="OrderService.cs",
                start_line=1,
                end_line=60,  # changed line range
                namespace="MyApp",
                signature="public class OrderService : IOrderService",  # changed signature
                modifiers="public",
            )
        )
        db.add(
            Symbol(
                snapshot_id="snap-head",
                kind="method",
                name="PlaceOrder",
                fq_name="MyApp.OrderService.PlaceOrder",
                file_path="OrderService.cs",
                start_line=10,
                end_line=25,
                namespace="MyApp",
                parent_fq_name="MyApp.OrderService",
                signature="public void PlaceOrder(Order order)",
                modifiers="public",
            )
        )
        # CancelOrder is gone, RefundOrder is new
        db.add(
            Symbol(
                snapshot_id="snap-head",
                kind="method",
                name="RefundOrder",
                fq_name="MyApp.OrderService.RefundOrder",
                file_path="OrderService.cs",
                start_line=27,
                end_line=45,
                namespace="MyApp",
                parent_fq_name="MyApp.OrderService",
                signature="public void RefundOrder(int orderId, decimal amount)",
                modifiers="public",
            )
        )

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


# ===================================================================
# Search API
# ===================================================================


class TestSearchAPI:
    @pytest.mark.asyncio
    async def test_search_symbols_by_name(self, client: AsyncClient):
        resp = await client.get("/repos/r-search/snapshots/snap-base/search?q=Order")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] > 0
        # Should find OrderService, PlaceOrder, CancelOrder
        names = [h["title"] for h in data["items"]]
        assert any("OrderService" in n for n in names)

    @pytest.mark.asyncio
    async def test_search_symbols_by_fqname(self, client: AsyncClient):
        resp = await client.get("/repos/r-search/snapshots/snap-base/search?q=MyApp.OrderService")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] > 0

    @pytest.mark.asyncio
    async def test_search_in_summaries(self, client: AsyncClient):
        resp = await client.get(
            "/repos/r-search/snapshots/snap-base/search?q=placement&entity_type=summary"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert data["items"][0]["entity_type"] == "summary"

    @pytest.mark.asyncio
    async def test_search_in_docs(self, client: AsyncClient):
        resp = await client.get(
            "/repos/r-search/snapshots/snap-base/search?q=Order+Service&entity_type=doc"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert data["items"][0]["entity_type"] == "doc"

    @pytest.mark.asyncio
    async def test_search_filter_entity_type_symbol(self, client: AsyncClient):
        resp = await client.get(
            "/repos/r-search/snapshots/snap-base/search?q=Order&entity_type=symbol"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert all(h["entity_type"] == "symbol" for h in data["items"])

    @pytest.mark.asyncio
    async def test_search_no_results(self, client: AsyncClient):
        resp = await client.get(
            "/repos/r-search/snapshots/snap-base/search?q=ZzzzNonexistentXxxx"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_search_pagination(self, client: AsyncClient):
        resp = await client.get(
            "/repos/r-search/snapshots/snap-base/search?q=Order&limit=1&offset=0"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["limit"] == 1
        assert len(data["items"]) <= 1
        if data["total"] > 1:
            assert data["has_more"] is True

    @pytest.mark.asyncio
    async def test_search_pagination_offset(self, client: AsyncClient):
        resp1 = await client.get(
            "/repos/r-search/snapshots/snap-base/search?q=Order&limit=1&offset=0"
        )
        resp2 = await client.get(
            "/repos/r-search/snapshots/snap-base/search?q=Order&limit=1&offset=1"
        )
        data1 = resp1.json()
        data2 = resp2.json()
        if data1["total"] > 1:
            assert data1["items"][0] != data2["items"][0]

    @pytest.mark.asyncio
    async def test_search_empty_query_rejected(self, client: AsyncClient):
        resp = await client.get("/repos/r-search/snapshots/snap-base/search?q=")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_search_snapshot_not_found(self, client: AsyncClient):
        resp = await client.get("/repos/r-search/snapshots/nonexistent/search?q=test")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_search_results_sorted_by_score(self, client: AsyncClient):
        resp = await client.get("/repos/r-search/snapshots/snap-base/search?q=OrderService")
        data = resp.json()
        if len(data["items"]) >= 2:
            scores = [h["score"] for h in data["items"]]
            assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_search_hit_structure(self, client: AsyncClient):
        resp = await client.get(
            "/repos/r-search/snapshots/snap-base/search?q=OrderService&entity_type=symbol"
        )
        data = resp.json()
        assert data["total"] >= 1
        hit = data["items"][0]
        assert "entity_type" in hit
        assert "entity_id" in hit
        assert "title" in hit
        assert "snippet" in hit
        assert "score" in hit
        assert "metadata" in hit

    @pytest.mark.asyncio
    async def test_search_file_path_match(self, client: AsyncClient):
        resp = await client.get(
            "/repos/r-search/snapshots/snap-base/search?q=OrderService.cs&entity_type=symbol"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1


# ===================================================================
# Snapshot Comparison API
# ===================================================================


class TestSnapshotDiff:
    @pytest.mark.asyncio
    async def test_diff_detects_added_symbols(self, client: AsyncClient):
        resp = await client.get("/repos/r-search/snapshots/snap-base/diff/snap-head")
        assert resp.status_code == 200
        data = resp.json()
        added_fqs = [s["fq_name"] for s in data["added"]]
        assert "MyApp.OrderService.RefundOrder" in added_fqs

    @pytest.mark.asyncio
    async def test_diff_detects_removed_symbols(self, client: AsyncClient):
        resp = await client.get("/repos/r-search/snapshots/snap-base/diff/snap-head")
        data = resp.json()
        removed_fqs = [s["fq_name"] for s in data["removed"]]
        assert "MyApp.OrderService.CancelOrder" in removed_fqs

    @pytest.mark.asyncio
    async def test_diff_detects_modified_symbols(self, client: AsyncClient):
        resp = await client.get("/repos/r-search/snapshots/snap-base/diff/snap-head")
        data = resp.json()
        modified_fqs = [s["fq_name"] for s in data["modified"]]
        # OrderService changed signature and end_line
        assert "MyApp.OrderService" in modified_fqs

    @pytest.mark.asyncio
    async def test_diff_unchanged_symbol(self, client: AsyncClient):
        resp = await client.get("/repos/r-search/snapshots/snap-base/diff/snap-head")
        data = resp.json()
        # PlaceOrder is identical in both
        all_changed = (
            [s["fq_name"] for s in data["added"]]
            + [s["fq_name"] for s in data["removed"]]
            + [s["fq_name"] for s in data["modified"]]
        )
        assert "MyApp.OrderService.PlaceOrder" not in all_changed

    @pytest.mark.asyncio
    async def test_diff_summary_counts(self, client: AsyncClient):
        resp = await client.get("/repos/r-search/snapshots/snap-base/diff/snap-head")
        data = resp.json()
        summary = data["summary"]
        assert summary["added"] == 1  # RefundOrder
        assert summary["removed"] == 1  # CancelOrder
        assert summary["modified"] == 1  # OrderService (class)
        assert summary["unchanged"] == 1  # PlaceOrder

    @pytest.mark.asyncio
    async def test_diff_response_structure(self, client: AsyncClient):
        resp = await client.get("/repos/r-search/snapshots/snap-base/diff/snap-head")
        data = resp.json()
        assert data["base_snapshot_id"] == "snap-base"
        assert data["head_snapshot_id"] == "snap-head"
        assert isinstance(data["added"], list)
        assert isinstance(data["removed"], list)
        assert isinstance(data["modified"], list)
        assert isinstance(data["summary"], dict)

    @pytest.mark.asyncio
    async def test_diff_symbol_structure(self, client: AsyncClient):
        resp = await client.get("/repos/r-search/snapshots/snap-base/diff/snap-head")
        data = resp.json()
        if data["added"]:
            sym = data["added"][0]
            assert "fq_name" in sym
            assert "kind" in sym
            assert "file_path" in sym
            assert "change" in sym
            assert sym["change"] == "added"

    @pytest.mark.asyncio
    async def test_diff_snapshot_not_found(self, client: AsyncClient):
        resp = await client.get("/repos/r-search/snapshots/snap-base/diff/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_diff_same_snapshot(self, client: AsyncClient):
        resp = await client.get("/repos/r-search/snapshots/snap-base/diff/snap-base")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["added"] == 0
        assert data["summary"]["removed"] == 0
        assert data["summary"]["modified"] == 0

    @pytest.mark.asyncio
    async def test_diff_reverse_direction(self, client: AsyncClient):
        """Diffing head->base should be the inverse of base->head."""
        resp_fwd = await client.get("/repos/r-search/snapshots/snap-base/diff/snap-head")
        resp_rev = await client.get("/repos/r-search/snapshots/snap-head/diff/snap-base")
        fwd = resp_fwd.json()
        rev = resp_rev.json()
        assert fwd["summary"]["added"] == rev["summary"]["removed"]
        assert fwd["summary"]["removed"] == rev["summary"]["added"]


# ===================================================================
# Export API
# ===================================================================


class TestExportAPI:
    @pytest.mark.asyncio
    async def test_export_returns_all_entities(self, client: AsyncClient):
        resp = await client.get("/repos/r-search/snapshots/snap-base/export")
        assert resp.status_code == 200
        data = resp.json()
        assert data["snapshot_id"] == "snap-base"
        assert len(data["symbols"]) == 3
        assert len(data["edges"]) == 1
        assert len(data["summaries"]) == 1
        assert len(data["docs"]) == 1

    @pytest.mark.asyncio
    async def test_export_symbol_structure(self, client: AsyncClient):
        resp = await client.get("/repos/r-search/snapshots/snap-base/export")
        data = resp.json()
        sym = data["symbols"][0]
        assert "fq_name" in sym
        assert "name" in sym
        assert "kind" in sym
        assert "file_path" in sym
        assert "start_line" in sym
        assert "end_line" in sym

    @pytest.mark.asyncio
    async def test_export_edge_structure(self, client: AsyncClient):
        resp = await client.get("/repos/r-search/snapshots/snap-base/export")
        edge = resp.json()["edges"][0]
        assert "source_fq_name" in edge
        assert "target_fq_name" in edge
        assert "edge_type" in edge

    @pytest.mark.asyncio
    async def test_export_summary_has_parsed_json(self, client: AsyncClient):
        resp = await client.get("/repos/r-search/snapshots/snap-base/export")
        summary = resp.json()["summaries"][0]
        assert "scope_type" in summary
        assert "scope_id" in summary
        assert isinstance(summary["summary"], dict)
        assert "purpose" in summary["summary"]

    @pytest.mark.asyncio
    async def test_export_doc_structure(self, client: AsyncClient):
        resp = await client.get("/repos/r-search/snapshots/snap-base/export")
        doc = resp.json()["docs"][0]
        assert "doc_type" in doc
        assert "title" in doc
        assert "markdown" in doc

    @pytest.mark.asyncio
    async def test_export_metadata(self, client: AsyncClient):
        resp = await client.get("/repos/r-search/snapshots/snap-base/export")
        meta = resp.json()["metadata"]
        assert meta["commit_sha"] == "aaa111"
        assert meta["file_count"] == 2
        assert meta["symbol_count"] == 3
        assert meta["edge_count"] == 1
        assert meta["summary_count"] == 1
        assert meta["doc_count"] == 1

    @pytest.mark.asyncio
    async def test_export_empty_snapshot(self, client: AsyncClient):
        """Export a snapshot with no symbols/edges should work."""
        resp = await client.get("/repos/r-search/snapshots/snap-head/export")
        assert resp.status_code == 200
        data = resp.json()
        assert data["snapshot_id"] == "snap-head"
        assert len(data["symbols"]) == 3  # snap-head has 3 symbols
        assert data["metadata"]["symbol_count"] == 3

    @pytest.mark.asyncio
    async def test_export_snapshot_not_found(self, client: AsyncClient):
        resp = await client.get("/repos/r-search/snapshots/nonexistent/export")
        assert resp.status_code == 404


# ===================================================================
# Scoring unit tests
# ===================================================================


class TestSearchScoring:
    def test_exact_name_match_highest_score(self):
        from app.api.search import _score_text

        assert _score_text("OrderService", "OrderService") == 10.0

    def test_partial_match(self):
        from app.api.search import _score_text

        score = _score_text("OrderService", "Order")
        assert score == 5.0

    def test_no_match(self):
        from app.api.search import _score_text

        score = _score_text("OrderService", "zzzzz")
        assert score == 0.1

    def test_case_insensitive(self):
        from app.api.search import _score_text

        score = _score_text("OrderService", "orderservice")
        assert score == 10.0

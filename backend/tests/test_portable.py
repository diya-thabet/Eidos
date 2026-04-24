"""
Tests for portable snapshot export/import (.eidos format).

Covers:
- Export: produces valid gzip, contains all entities, compact keys, response headers
- Import: restores snapshot, creates symbols/edges/summaries/docs/evaluations
- Round-trip: export then import preserves all data
- Error cases: bad gzip, bad JSON, missing metadata, empty file, repo not found
- Compression: exported file is smaller than raw JSON
"""

from __future__ import annotations

import gzip
import json
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.storage.database import get_db
from app.storage.models import (
    Edge,
    Evaluation,
    GeneratedDoc,
    Repo,
    RepoSnapshot,
    SnapshotStatus,
    Summary,
    Symbol,
)
from tests.conftest import create_tables, drop_tables, override_get_db, test_sessionmaker

app.dependency_overrides[get_db] = override_get_db


async def _seed() -> None:
    async with test_sessionmaker() as db:
        repo = Repo(id="r-port", name="portable-test", url="https://example.com/port")
        db.add(repo)

        snap = RepoSnapshot(
            id="s-port",
            repo_id="r-port",
            commit_sha="abc123",
            status=SnapshotStatus.completed,
            file_count=2,
        )
        db.add(snap)
        await db.flush()

        # Symbols
        db.add(Symbol(
            snapshot_id="s-port", kind="class", name="OrderService",
            fq_name="App.OrderService", file_path="Order.cs",
            start_line=1, end_line=50, namespace="App",
            signature="public class OrderService", modifiers="public",
        ))
        db.add(Symbol(
            snapshot_id="s-port", kind="method", name="PlaceOrder",
            fq_name="App.OrderService.PlaceOrder", file_path="Order.cs",
            start_line=10, end_line=25, namespace="App",
            parent_fq_name="App.OrderService",
            signature="public void PlaceOrder(Order o)", modifiers="public",
            return_type="void",
        ))

        # Edge
        db.add(Edge(
            snapshot_id="s-port",
            source_fq_name="App.OrderService.PlaceOrder",
            target_fq_name="App.OrderService",
            edge_type="calls", file_path="Order.cs", line=15,
        ))

        # Summary
        db.add(Summary(
            snapshot_id="s-port", scope_type="symbol",
            scope_id="App.OrderService",
            summary_json='{"purpose": "Handles orders"}',
        ))

        # Doc
        db.add(GeneratedDoc(
            snapshot_id="s-port", doc_type="readme",
            title="Order Service", scope_id="App.OrderService",
            markdown="# Order Service\n\nHandles orders.",
        ))

        # Evaluation
        db.add(Evaluation(
            snapshot_id="s-port", scope="snapshot",
            overall_score=0.85, overall_severity="low",
            checks_json='[{"name":"c1","passed":true}]',
            summary="Good",
        ))

        # Import target repo (no snapshots)
        db.add(Repo(id="r-target", name="target-repo", url="https://example.com/target"))

        await db.commit()


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
# Export
# ===================================================================


class TestExportPortable:
    @pytest.mark.asyncio
    async def test_export_returns_gzip(self, client: AsyncClient):
        resp = await client.get("/repos/r-port/snapshots/s-port/portable")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/gzip"
        # Verify it's valid gzip
        decompressed = gzip.decompress(resp.content)
        data = json.loads(decompressed)
        assert data["schema_version"] == 1

    @pytest.mark.asyncio
    async def test_export_has_content_disposition(self, client: AsyncClient):
        resp = await client.get("/repos/r-port/snapshots/s-port/portable")
        assert "r-port_s-port.eidos" in resp.headers["content-disposition"]

    @pytest.mark.asyncio
    async def test_export_has_size_headers(self, client: AsyncClient):
        resp = await client.get("/repos/r-port/snapshots/s-port/portable")
        assert int(resp.headers["x-eidos-compressed-size"]) > 0
        assert int(resp.headers["x-eidos-uncompressed-size"]) > 0
        # Compressed should be smaller
        assert int(resp.headers["x-eidos-compressed-size"]) < int(
            resp.headers["x-eidos-uncompressed-size"]
        )

    @pytest.mark.asyncio
    async def test_export_contains_all_entities(self, client: AsyncClient):
        resp = await client.get("/repos/r-port/snapshots/s-port/portable")
        data = json.loads(gzip.decompress(resp.content))
        assert len(data["symbols"]) == 2
        assert len(data["edges"]) == 1
        assert len(data["summaries"]) == 1
        assert len(data["docs"]) == 1
        assert len(data["evaluations"]) == 1

    @pytest.mark.asyncio
    async def test_export_uses_compact_keys(self, client: AsyncClient):
        resp = await client.get("/repos/r-port/snapshots/s-port/portable")
        data = json.loads(gzip.decompress(resp.content))
        sym = data["symbols"][0]
        # Compact keys: n, k, fq, fp, sl, el
        assert "n" in sym  # name
        assert "k" in sym  # kind
        assert "fq" in sym  # fq_name
        assert "fp" in sym  # file_path
        assert "sl" in sym  # start_line
        assert "el" in sym  # end_line

    @pytest.mark.asyncio
    async def test_export_compact_edges(self, client: AsyncClient):
        resp = await client.get("/repos/r-port/snapshots/s-port/portable")
        data = json.loads(gzip.decompress(resp.content))
        edge = data["edges"][0]
        assert "s" in edge  # source
        assert "t" in edge  # target
        assert "tp" in edge  # type

    @pytest.mark.asyncio
    async def test_export_metadata(self, client: AsyncClient):
        resp = await client.get("/repos/r-port/snapshots/s-port/portable")
        data = json.loads(gzip.decompress(resp.content))
        meta = data["metadata"]
        assert meta["commit_sha"] == "abc123"
        assert meta["file_count"] == 2
        assert meta["original_snapshot_id"] == "s-port"

    @pytest.mark.asyncio
    async def test_export_is_smaller_than_json(self, client: AsyncClient):
        resp = await client.get("/repos/r-port/snapshots/s-port/portable")
        compressed_size = len(resp.content)
        uncompressed = gzip.decompress(resp.content)
        assert compressed_size < len(uncompressed)

    @pytest.mark.asyncio
    async def test_export_snapshot_not_found(self, client: AsyncClient):
        resp = await client.get("/repos/r-port/snapshots/nonexistent/portable")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_export_omits_empty_optional_fields(self, client: AsyncClient):
        resp = await client.get("/repos/r-port/snapshots/s-port/portable")
        data = json.loads(gzip.decompress(resp.content))
        # The class symbol has no parent_fq_name, so "p" should be absent
        class_sym = next(s for s in data["symbols"] if s["k"] == "class")
        assert "p" not in class_sym  # parent not set


# ===================================================================
# Import
# ===================================================================


class TestImportPortable:
    async def _get_eidos_file(self, client: AsyncClient) -> bytes:
        """Helper: export a .eidos file."""
        resp = await client.get("/repos/r-port/snapshots/s-port/portable")
        return resp.content

    @pytest.mark.asyncio
    async def test_import_creates_snapshot(self, client: AsyncClient):
        eidos_file = await self._get_eidos_file(client)
        resp = await client.post(
            "/repos/r-target/import",
            files={"file": ("test.eidos", eidos_file, "application/gzip")},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["repo_id"] == "r-target"
        assert data["snapshot_id"]
        assert data["symbols_imported"] == 2
        assert data["edges_imported"] == 1
        assert data["summaries_imported"] == 1
        assert data["docs_imported"] == 1
        assert data["evaluations_imported"] == 1

    @pytest.mark.asyncio
    async def test_import_snapshot_is_completed(self, client: AsyncClient):
        eidos_file = await self._get_eidos_file(client)
        resp = await client.post(
            "/repos/r-target/import",
            files={"file": ("test.eidos", eidos_file, "application/gzip")},
        )
        snap_id = resp.json()["snapshot_id"]

        # Verify snapshot status
        async with test_sessionmaker() as db:
            snap = await db.get(RepoSnapshot, snap_id)
            assert snap is not None
            assert snap.status == SnapshotStatus.completed
            assert snap.repo_id == "r-target"
            assert snap.commit_sha == "abc123"

    @pytest.mark.asyncio
    async def test_import_symbols_restored(self, client: AsyncClient):
        eidos_file = await self._get_eidos_file(client)
        resp = await client.post(
            "/repos/r-target/import",
            files={"file": ("test.eidos", eidos_file, "application/gzip")},
        )
        snap_id = resp.json()["snapshot_id"]

        # Check symbols via API
        sym_resp = await client.get(
            f"/repos/r-target/snapshots/{snap_id}/symbols?kind=class"
        )
        assert sym_resp.status_code == 200
        items = sym_resp.json()["items"]
        assert len(items) == 1
        assert items[0]["fq_name"] == "App.OrderService"

    @pytest.mark.asyncio
    async def test_import_edges_restored(self, client: AsyncClient):
        eidos_file = await self._get_eidos_file(client)
        resp = await client.post(
            "/repos/r-target/import",
            files={"file": ("test.eidos", eidos_file, "application/gzip")},
        )
        snap_id = resp.json()["snapshot_id"]

        edge_resp = await client.get(
            f"/repos/r-target/snapshots/{snap_id}/edges?edge_type=calls"
        )
        assert edge_resp.status_code == 200
        assert edge_resp.json()["total"] == 1

    @pytest.mark.asyncio
    async def test_import_repo_not_found(self, client: AsyncClient):
        eidos_file = await self._get_eidos_file(client)
        resp = await client.post(
            "/repos/nonexistent/import",
            files={"file": ("test.eidos", eidos_file, "application/gzip")},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_import_bad_gzip(self, client: AsyncClient):
        resp = await client.post(
            "/repos/r-target/import",
            files={"file": ("bad.eidos", b"not gzip data", "application/gzip")},
        )
        assert resp.status_code == 400
        assert "gzip" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_import_bad_json(self, client: AsyncClient):
        bad_gzip = gzip.compress(b"not json")
        resp = await client.post(
            "/repos/r-target/import",
            files={"file": ("bad.eidos", bad_gzip, "application/gzip")},
        )
        assert resp.status_code == 400
        assert "json" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_import_missing_metadata(self, client: AsyncClient):
        payload = gzip.compress(json.dumps({"schema_version": 1}).encode())
        resp = await client.post(
            "/repos/r-target/import",
            files={"file": ("bad.eidos", payload, "application/gzip")},
        )
        assert resp.status_code == 400
        assert "metadata" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_import_empty_file(self, client: AsyncClient):
        resp = await client.post(
            "/repos/r-target/import",
            files={"file": ("empty.eidos", b"", "application/gzip")},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_import_future_schema_rejected(self, client: AsyncClient):
        payload = gzip.compress(json.dumps({
            "schema_version": 999,
            "metadata": {"commit_sha": "", "file_count": 0},
        }).encode())
        resp = await client.post(
            "/repos/r-target/import",
            files={"file": ("future.eidos", payload, "application/gzip")},
        )
        assert resp.status_code == 400
        assert "upgrade" in resp.json()["detail"].lower()


# ===================================================================
# Round-trip: export -> import -> verify
# ===================================================================


class TestRoundTrip:
    @pytest.mark.asyncio
    async def test_round_trip_preserves_symbols(self, client: AsyncClient):
        # Export from source
        export_resp = await client.get("/repos/r-port/snapshots/s-port/portable")
        eidos_file = export_resp.content

        # Import to target
        import_resp = await client.post(
            "/repos/r-target/import",
            files={"file": ("rt.eidos", eidos_file, "application/gzip")},
        )
        new_snap_id = import_resp.json()["snapshot_id"]

        # Compare symbols
        orig = await client.get("/repos/r-port/snapshots/s-port/symbols")
        restored = await client.get(
            f"/repos/r-target/snapshots/{new_snap_id}/symbols"
        )
        orig_names = sorted(s["fq_name"] for s in orig.json()["items"])
        rest_names = sorted(s["fq_name"] for s in restored.json()["items"])
        assert orig_names == rest_names

    @pytest.mark.asyncio
    async def test_round_trip_preserves_overview(self, client: AsyncClient):
        export_resp = await client.get("/repos/r-port/snapshots/s-port/portable")
        import_resp = await client.post(
            "/repos/r-target/import",
            files={"file": ("rt.eidos", export_resp.content, "application/gzip")},
        )
        new_snap_id = import_resp.json()["snapshot_id"]

        orig_overview = await client.get(
            "/repos/r-port/snapshots/s-port/overview"
        )
        rest_overview = await client.get(
            f"/repos/r-target/snapshots/{new_snap_id}/overview"
        )
        assert orig_overview.json()["total_symbols"] == rest_overview.json()["total_symbols"]
        assert orig_overview.json()["total_edges"] == rest_overview.json()["total_edges"]

    @pytest.mark.asyncio
    async def test_round_trip_preserves_summaries(self, client: AsyncClient):
        export_resp = await client.get("/repos/r-port/snapshots/s-port/portable")
        import_resp = await client.post(
            "/repos/r-target/import",
            files={"file": ("rt.eidos", export_resp.content, "application/gzip")},
        )
        new_snap_id = import_resp.json()["snapshot_id"]

        orig = await client.get(
            "/repos/r-port/snapshots/s-port/summaries?scope_type=symbol"
        )
        restored = await client.get(
            f"/repos/r-target/snapshots/{new_snap_id}/summaries?scope_type=symbol"
        )
        assert orig.json()["total"] == restored.json()["total"]

    @pytest.mark.asyncio
    async def test_round_trip_preserves_docs(self, client: AsyncClient):
        export_resp = await client.get("/repos/r-port/snapshots/s-port/portable")
        import_resp = await client.post(
            "/repos/r-target/import",
            files={"file": ("rt.eidos", export_resp.content, "application/gzip")},
        )
        new_snap_id = import_resp.json()["snapshot_id"]

        orig = await client.get("/repos/r-port/snapshots/s-port/docs")
        restored = await client.get(
            f"/repos/r-target/snapshots/{new_snap_id}/docs"
        )
        assert len(orig.json()) == len(restored.json())
        assert orig.json()[0]["title"] == restored.json()[0]["title"]

    @pytest.mark.asyncio
    async def test_multiple_imports_create_separate_snapshots(self, client: AsyncClient):
        eidos_file = (await client.get("/repos/r-port/snapshots/s-port/portable")).content

        resp1 = await client.post(
            "/repos/r-target/import",
            files={"file": ("a.eidos", eidos_file, "application/gzip")},
        )
        resp2 = await client.post(
            "/repos/r-target/import",
            files={"file": ("b.eidos", eidos_file, "application/gzip")},
        )
        assert resp1.json()["snapshot_id"] != resp2.json()["snapshot_id"]

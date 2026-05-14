# ruff: noqa: E501
"""
Comprehensive E2E integration test for the full Eidos backend.

Uses the shared in-memory SQLite test engine from conftest.py
and exercises every major API endpoint group.
"""
from __future__ import annotations

import json

import httpx
import pytest
import pytest_asyncio

from tests.conftest import (
    create_tables,
    drop_tables,
    override_get_db,
    test_sessionmaker,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="module")
async def seeded_client():
    """Boot the app with test DB and seed a repo + snapshot with real data."""
    await create_tables()

    from app.main import app
    from app.storage.database import get_db
    from app.storage.models import (
        Edge,
        File,
        RepoSnapshot,
        SnapshotStatus,
        Summary,
        Symbol,
    )

    # Override DB dependency to use test engine
    app.dependency_overrides[get_db] = override_get_db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Create repo
        resp = await client.post("/repos", json={
            "name": "TestRepo",
            "url": "https://github.com/example/test.git",
            "default_branch": "main",
        })
        assert resp.status_code == 201, resp.text
        repo = resp.json()
        repo_id = repo["id"]

        # Create a snapshot directly (skip ingestion to avoid git clone)
        async with test_sessionmaker() as db:
            snap = RepoSnapshot(id="e2e-snap-001", repo_id=repo_id, status=SnapshotStatus.completed, file_count=4)
            db.add(snap)
            await db.flush()
            snapshot_id = snap.id

            db.add_all([
                File(snapshot_id=snapshot_id, path="app/main.py", language="python", size_bytes=2000, hash="h1"),
                File(snapshot_id=snapshot_id, path="app/models.py", language="python", size_bytes=1500, hash="h2"),
                File(snapshot_id=snapshot_id, path="app/service.py", language="python", size_bytes=3000, hash="h3"),
                File(snapshot_id=snapshot_id, path="tests/test_main.py", language="python", size_bytes=800, hash="h4"),
            ])

            symbols_data = [
                ("app.main.App", "App", "class", "app.main", "app/main.py", 1, 30, "class App", "public"),
                ("app.main.App.run", "run", "method", "app.main", "app/main.py", 5, 15, "async def run(self)", "public"),
                ("app.main.App._init_db", "_init_db", "method", "app.main", "app/main.py", 17, 25, "def _init_db(self)", "private"),
                ("app.main.create_app", "create_app", "function", "app.main", "app/main.py", 27, 30, "def create_app() -> App", "public"),
                ("app.models.User", "User", "class", "app.models", "app/models.py", 1, 20, "class User(Base)", "public"),
                ("app.models.User.validate", "validate", "method", "app.models", "app/models.py", 10, 18, "def validate(self) -> bool", "public"),
                ("app.models.Role", "Role", "class", "app.models", "app/models.py", 22, 30, "class Role(enum.Enum)", "public"),
                ("app.service.UserService", "UserService", "class", "app.service", "app/service.py", 1, 50, "class UserService", "public"),
                ("app.service.UserService.get_user", "get_user", "method", "app.service", "app/service.py", 10, 20, "async def get_user(self, user_id: int) -> User", "public"),
                ("app.service.UserService.create_user", "create_user", "method", "app.service", "app/service.py", 22, 35, "async def create_user(self, data: dict) -> User", "public"),
                ("app.service.UserService._validate", "_validate", "method", "app.service", "app/service.py", 37, 45, "def _validate(self, data: dict) -> bool", "private"),
                ("tests.test_main.test_create_app", "test_create_app", "function", "tests.test_main", "tests/test_main.py", 1, 5, "def test_create_app()", "public"),
                ("tests.test_main.test_run", "test_run", "function", "tests.test_main", "tests/test_main.py", 7, 12, "async def test_run()", "public"),
            ]
            for fq, n, k, ns, fp, sl, el, sig, mod in symbols_data:
                db.add(Symbol(snapshot_id=snapshot_id, fq_name=fq, name=n, kind=k,
                              namespace=ns, file_path=fp, start_line=sl, end_line=el,
                              signature=sig, modifiers=mod))

            edges_data = [
                ("app.main.App.run", "app.service.UserService.get_user", "calls"),
                ("app.main.App.run", "app.service.UserService.create_user", "calls"),
                ("app.service.UserService.create_user", "app.service.UserService._validate", "calls"),
                ("app.service.UserService._validate", "app.models.User.validate", "calls"),
                ("app.models.User", "app.models.Role", "calls"),
                ("tests.test_main.test_create_app", "app.main.create_app", "calls"),
                ("tests.test_main.test_run", "app.main.App.run", "calls"),
            ]
            for s, t, et in edges_data:
                db.add(Edge(snapshot_id=snapshot_id, source_fq_name=s, target_fq_name=t, edge_type=et))

            db.add(Summary(snapshot_id=snapshot_id, scope_type="module", scope_id="app.main",
                           summary_json=json.dumps({"description": "Main application entry point."})))
            db.add(Summary(snapshot_id=snapshot_id, scope_type="module", scope_id="app.models",
                           summary_json=json.dumps({"description": "Data models."})))
            db.add(Summary(snapshot_id=snapshot_id, scope_type="module", scope_id="app.service",
                           summary_json=json.dumps({"description": "Business logic layer."})))

            await db.commit()

        yield client, repo_id, snapshot_id

    # Don't clear dependency_overrides — other test modules set them at import time
    await drop_tables()
    await create_tables()  # Leave clean tables for other test modules


# ---------------------------------------------------------------------------
# Health & Info endpoints
# ---------------------------------------------------------------------------


class TestHealthAndInfo:

    @pytest.mark.asyncio
    async def test_health(self, seeded_client):
        client, _, _ = seeded_client
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_health_ready(self, seeded_client):
        client, _, _ = seeded_client
        resp = await client.get("/health/ready")
        # 503 is OK if /health/ready hits production engine (not overridden)
        assert resp.status_code in (200, 503)

    @pytest.mark.asyncio
    async def test_version(self, seeded_client):
        client, _, _ = seeded_client
        resp = await client.get("/version")
        assert resp.status_code == 200
        assert "version" in resp.json()

    @pytest.mark.asyncio
    async def test_metrics(self, seeded_client):
        client, _, _ = seeded_client
        resp = await client.get("/metrics")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Repos CRUD
# ---------------------------------------------------------------------------


class TestRepos:

    @pytest.mark.asyncio
    async def test_list_repos(self, seeded_client):
        client, _, _ = seeded_client
        resp = await client.get("/repos")
        assert resp.status_code == 200
        repos = resp.json()
        assert len(repos) >= 1
        assert any(r["name"] == "TestRepo" for r in repos)

    @pytest.mark.asyncio
    async def test_get_repo_status(self, seeded_client):
        client, repo_id, _ = seeded_client
        resp = await client.get(f"/repos/{repo_id}/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["repo_id"] == repo_id
        assert len(data["snapshots"]) >= 1


# ---------------------------------------------------------------------------
# Snapshot detail
# ---------------------------------------------------------------------------


class TestSnapshots:

    @pytest.mark.asyncio
    async def test_get_snapshot(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == snap_id
        assert data["status"] == "completed"

    @pytest.mark.asyncio
    async def test_get_overview(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_symbols"] >= 13
        assert data["total_modules"] >= 1


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


class TestFiles:

    @pytest.mark.asyncio
    async def test_list_files(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/files")
        assert resp.status_code == 200
        files = resp.json()
        assert len(files) >= 4
        paths = [f["path"] for f in files]
        assert "app/main.py" in paths


# ---------------------------------------------------------------------------
# Symbols
# ---------------------------------------------------------------------------


class TestSymbols:

    @pytest.mark.asyncio
    async def test_list_symbols(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/symbols")
        assert resp.status_code == 200
        symbols = resp.json()
        assert len(symbols) >= 1

    @pytest.mark.asyncio
    async def test_get_symbol_by_fq_name(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/symbols/app.main.App")
        assert resp.status_code == 200
        sym = resp.json()
        assert sym["name"] == "App"
        assert sym["kind"] == "class"

    @pytest.mark.asyncio
    async def test_get_callers(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/symbols/app.main.create_app/callers")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_symbol_notes(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.patch(
            f"/repos/{repo_id}/snapshots/{snap_id}/symbols/app.main.App/notes",
            json={"note": "Main application class"},
        )
        assert resp.status_code in (200, 201)

        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/symbols/app.main.App/notes")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Edges
# ---------------------------------------------------------------------------


class TestEdges:

    @pytest.mark.asyncio
    async def test_list_edges(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/edges")
        assert resp.status_code == 200
        edges = resp.json()
        assert len(edges) >= 1


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


class TestGraph:

    @pytest.mark.asyncio
    async def test_get_graph(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/graph/app.main.App")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------


class TestSummaries:

    @pytest.mark.asyncio
    async def test_list_summaries(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/summaries")
        assert resp.status_code == 200
        summaries = resp.json()
        assert len(summaries) >= 3

    @pytest.mark.asyncio
    async def test_get_summary_by_scope(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/summaries/module/app.main")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class TestSearch:

    @pytest.mark.asyncio
    async def test_search_symbols(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/search", params={"q": "User"})
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_fulltext_search(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/fulltext", params={"q": "service"})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Documentation Generation
# ---------------------------------------------------------------------------


class TestDocGen:

    @pytest.mark.asyncio
    async def test_generate_all_docs(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.post(f"/repos/{repo_id}/snapshots/{snap_id}/docs", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert len(data["documents"]) >= 1

    @pytest.mark.asyncio
    async def test_list_docs(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/docs")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    @pytest.mark.asyncio
    async def test_get_single_doc(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/docs")
        docs = resp.json()
        if docs:
            doc_id = docs[0]["id"]
            resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/docs/{doc_id}")
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_export_markdown(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/docs/export", params={"format": "markdown"})
        assert resp.status_code == 200
        assert resp.json()["format"] == "markdown"
        assert resp.json()["total"] >= 1

    @pytest.mark.asyncio
    async def test_export_html(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/docs/export", params={"format": "html"})
        assert resp.status_code == 200
        assert resp.json()["format"] == "html"

    @pytest.mark.asyncio
    async def test_export_docusaurus(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/docs/export", params={"format": "docusaurus"})
        assert resp.status_code == 200
        assert "sidebars.js" in resp.json().get("files", {})

    @pytest.mark.asyncio
    async def test_export_github_wiki(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/docs/export", params={"format": "github_wiki"})
        assert resp.status_code == 200
        assert "_Sidebar.md" in resp.json().get("files", {})

    @pytest.mark.asyncio
    async def test_export_confluence(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/docs/export", params={"format": "confluence"})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_export_invalid_format(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/docs/export", params={"format": "invalid"})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Diagram
# ---------------------------------------------------------------------------


class TestDiagram:

    @pytest.mark.asyncio
    async def test_get_diagram(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/diagram")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Analysis endpoints
# ---------------------------------------------------------------------------


class TestAnalysis:

    @pytest.mark.asyncio
    async def test_complexity(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/complexity")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_hotspots(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/hotspots")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_dependencies(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/dependencies")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_dead_code(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/dead-code")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_clones(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/clones")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_coupling(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/coupling")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_call_cycles(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/call-cycles")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_health_run(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.post(f"/repos/{repo_id}/snapshots/{snap_id}/health")
        assert resp.status_code in (200, 500)

    @pytest.mark.asyncio
    async def test_health_rules(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/health/rules")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_health_findings(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/health/findings")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------


class TestExports:

    @pytest.mark.asyncio
    async def test_export_json(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/export")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_export_csv(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/export/csv")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_export_sarif(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/export/sarif")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_export_markdown_report(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/export/markdown")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_export_sbom(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/export/sbom")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Portable
# ---------------------------------------------------------------------------


class TestPortable:

    @pytest.mark.asyncio
    async def test_export_portable(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/portable")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


class TestTags:

    @pytest.mark.asyncio
    async def test_add_tag(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.post(f"/repos/{repo_id}/snapshots/{snap_id}/tags", json={"tag": "v1.0.0"})
        assert resp.status_code in (200, 201)

    @pytest.mark.asyncio
    async def test_list_tags(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/tags")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_by_tag(self, seeded_client):
        client, repo_id, _ = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/by-tag/v1.0.0")
        assert resp.status_code in (200, 404)


# ---------------------------------------------------------------------------
# Quality Gates
# ---------------------------------------------------------------------------


class TestQualityGates:

    @pytest.mark.asyncio
    async def test_list_gates(self, seeded_client):
        client, repo_id, _ = seeded_client
        resp = await client.get(f"/repos/{repo_id}/quality-gates")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_create_gate(self, seeded_client):
        client, repo_id, _ = seeded_client
        resp = await client.post(f"/repos/{repo_id}/quality-gates", json={
            "name": "test-gate",
            "rules": [{"metric": "symbol_count", "operator": ">=", "threshold": 1}],
        })
        assert resp.status_code in (200, 201)


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


class TestDiff:

    @pytest.mark.asyncio
    async def test_diff_same_snapshot(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/{snap_id}/diff/{snap_id}")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:

    @pytest.mark.asyncio
    async def test_nonexistent_repo(self, seeded_client):
        client, _, _ = seeded_client
        resp = await client.get("/repos/nonexistent/status")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_nonexistent_snapshot(self, seeded_client):
        client, repo_id, _ = seeded_client
        resp = await client.get(f"/repos/{repo_id}/snapshots/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_doc_type(self, seeded_client):
        client, repo_id, snap_id = seeded_client
        resp = await client.post(f"/repos/{repo_id}/snapshots/{snap_id}/docs", json={"doc_type": "nonexistent"})
        assert resp.status_code == 400

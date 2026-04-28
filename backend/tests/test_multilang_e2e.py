"""
=============================================================================
MULTI-LANGUAGE E2E TEST: Eidos vs. 8 Real Open-Source GitHub Repositories
=============================================================================

Tests every supported language parser against a real public repo:

| Language   | Repo                      | Description                        |
|------------|---------------------------|------------------------------------|
| Python     | pallets/markupsafe        | HTML escaping lib (Flask dep)      |
| C#         | jbogard/MediatR           | Mediator pattern for .NET          |
| TypeScript | sindresorhus/p-map        | Promise mapping utility            |
| TSX        | pmndrs/zustand            | React state management             |
| Go         | tmrts/go-patterns         | Design patterns in Go              |
| Rust       | dtolnay/thiserror         | Derive macro for errors            |
| C          | antirez/sds               | Simple Dynamic Strings (Redis)     |
| C++        | gabime/spdlog             | Fast C++ logging library           |

Each repo is cloned, scanned, parsed, and verified through the full
Eidos pipeline. Then we seed the API and test symbols, edges, search,
health, diagrams, export, and portable round-trip.

Usage:
    cd backend
    python -m pytest tests/test_multilang_e2e.py -v --tb=short -s

    # Run just one language:
    python -m pytest tests/test_multilang_e2e.py -k "python" -v -s
"""

from __future__ import annotations

import gzip
import json
import shutil
import tempfile
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.analysis.pipeline import analyze_snapshot_files
from app.core.ingestion import clone_repo, scan_files
from app.main import app
from app.storage.database import get_db
from app.storage.models import (
    Edge as EdgeModel,
)
from app.storage.models import (
    File,
    Repo,
    RepoSnapshot,
    SnapshotStatus,
    Symbol,
)
from tests.conftest import create_tables, drop_tables, override_get_db

# ---------------------------------------------------------------------------
# Override DB for testing
# ---------------------------------------------------------------------------

app.dependency_overrides[get_db] = override_get_db

# ---------------------------------------------------------------------------
# Repo definitions: one per language
# ---------------------------------------------------------------------------

REPOS = [
    {
        "id": "python",
        "name": "markupsafe",
        "url": "https://github.com/pallets/markupsafe",
        "branch": "main",
        "language": "python",
        "expect_classes": True,
        "expect_methods": True,
    },
    {
        "id": "csharp",
        "name": "GuardClauses",
        "url": "https://github.com/ardalis/GuardClauses",
        "branch": "main",
        "language": "csharp",
        "expect_classes": True,
        "expect_methods": True,
    },
    {
        "id": "typescript",
        "name": "p-map",
        "url": "https://github.com/sindresorhus/p-map",
        "branch": "main",
        "language": "typescript",
        "expect_classes": False,
        "expect_methods": True,
    },
    {
        "id": "tsx",
        "name": "zustand",
        "url": "https://github.com/pmndrs/zustand",
        "branch": "main",
        "language": "tsx",
        "expect_classes": False,
        "expect_methods": True,
    },
    {
        "id": "go",
        "name": "go-patterns",
        "url": "https://github.com/tmrts/go-patterns",
        "branch": "master",
        "language": "go",
        "expect_classes": False,
        "expect_methods": True,
    },
    {
        "id": "rust",
        "name": "thiserror",
        "url": "https://github.com/dtolnay/thiserror",
        "branch": "master",
        "language": "rust",
        "expect_classes": False,
        "expect_methods": True,
    },
    {
        "id": "c",
        "name": "sds",
        "url": "https://github.com/antirez/sds",
        "branch": "master",
        "language": "c",
        "expect_classes": False,
        "expect_methods": True,
    },
    {
        "id": "cpp",
        "name": "spdlog",
        "url": "https://github.com/gabime/spdlog",
        "branch": "v1.x",
        "language": "cpp",
        "expect_classes": True,
        "expect_methods": True,
    },
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _clone_one(repo_def: dict) -> dict:
    """Clone a single repo and return parsed data."""
    tmpdir = tempfile.mkdtemp(prefix=f"eidos_{repo_def['id']}_")
    dest = Path(tmpdir) / repo_def["name"]
    try:
        sha = clone_repo(repo_def["url"], repo_def["branch"], dest, None, "")
    except Exception as e:
        shutil.rmtree(tmpdir, ignore_errors=True)
        pytest.skip(f"Cannot clone {repo_def['url']}: {e}")

    files = scan_files(dest)
    graph = analyze_snapshot_files(dest, files)

    return {
        "tmpdir": tmpdir,
        "path": dest,
        "sha": sha,
        "files": files,
        "graph": graph,
        "def": repo_def,
    }


# Module-scope: clone all repos once
_cached_repos: dict[str, dict] = {}


def _get_repo(repo_def: dict) -> dict:
    """Get or create cached clone for a repo."""
    rid = repo_def["id"]
    if rid not in _cached_repos:
        _cached_repos[rid] = _clone_one(repo_def)
    return _cached_repos[rid]


def pytest_sessionfinish(session, exitstatus):
    """Cleanup all cloned repos at end of session."""
    for data in _cached_repos.values():
        shutil.rmtree(data["tmpdir"], ignore_errors=True)


# ---------------------------------------------------------------------------
# Phase 1: Offline parsing tests (parameterized per language)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("repo_def", REPOS, ids=[r["id"] for r in REPOS])
class TestOfflineParsing:
    """Verify that each language parser works on real code."""

    def test_clone_and_scan(self, repo_def: dict):
        """Clone succeeds and finds source files in the target language."""
        data = _get_repo(repo_def)
        lang = repo_def["language"]

        # Should find files in the target language
        lang_files = [f for f in data["files"] if f["language"] == lang]
        all_count = len(data["files"])
        print(f"\n  [{lang}] {repo_def['name']}: {all_count} total files, "
              f"{len(lang_files)} {lang} files, SHA={data['sha'][:8]}")
        assert len(lang_files) > 0, f"No {lang} files found in {repo_def['name']}"

    def test_symbols_found(self, repo_def: dict):
        """Parser finds symbols (classes, functions, methods, etc.)."""
        data = _get_repo(repo_def)
        graph = data["graph"]
        lang = repo_def["language"]

        assert len(graph.symbols) > 0, f"No symbols found for {lang}"

        # Count by kind
        kinds: dict[str, int] = {}
        for sym in graph.symbols.values():
            kinds[sym.kind.value] = kinds.get(sym.kind.value, 0) + 1

        print(f"\n  [{lang}] Symbols: {len(graph.symbols)}")
        for kind, count in sorted(kinds.items()):
            print(f"    {kind}: {count}")

    def test_edges_found(self, repo_def: dict):
        """Graph builder finds relationships between symbols."""
        data = _get_repo(repo_def)
        graph = data["graph"]
        lang = repo_def["language"]

        # Some tiny repos may not have edges -- that's OK
        edge_count = len(graph.edges)
        print(f"\n  [{lang}] Edges: {edge_count}")
        if edge_count > 0:
            types: dict[str, int] = {}
            for e in graph.edges:
                types[e.edge_type.value] = types.get(e.edge_type.value, 0) + 1
            for etype, count in sorted(types.items()):
                print(f"    {etype}: {count}")

    def test_symbols_have_valid_data(self, repo_def: dict):
        """Every symbol has name, fq_name, file_path, and valid lines."""
        data = _get_repo(repo_def)
        for sym in data["graph"].symbols.values():
            assert sym.name, f"Empty name: {sym}"
            assert sym.fq_name, f"Empty fq_name: {sym}"
            assert sym.file_path, f"Empty file_path: {sym}"
            assert sym.start_line >= 1, f"Bad start_line: {sym}"
            assert sym.end_line >= sym.start_line, f"end < start: {sym}"

    def test_classes_if_expected(self, repo_def: dict):
        """Languages with OOP should find class symbols."""
        if not repo_def["expect_classes"]:
            pytest.skip(f"{repo_def['language']} may not have classes")
        data = _get_repo(repo_def)
        classes = [
            s for s in data["graph"].symbols.values()
            if s.kind.value in ("class", "interface", "struct", "enum")
        ]
        print(f"\n  [{repo_def['language']}] Class-like symbols: {len(classes)}")
        for c in classes[:10]:
            print(f"    {c.kind.value}: {c.fq_name}")
        assert len(classes) > 0

    def test_methods_if_expected(self, repo_def: dict):
        """Should find methods or functions."""
        if not repo_def["expect_methods"]:
            pytest.skip(f"{repo_def['language']} may not have methods")
        data = _get_repo(repo_def)
        methods = [
            s for s in data["graph"].symbols.values()
            if s.kind.value in ("method", "function", "constructor")
        ]
        print(f"\n  [{repo_def['language']}] Methods/functions: {len(methods)}")
        for m in methods[:5]:
            sig = m.signature[:60] if m.signature else "(no sig)"
            print(f"    {m.fq_name}: {sig}")
        assert len(methods) > 0


# ---------------------------------------------------------------------------
# Phase 2: API tests (parameterized per language)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("repo_def", REPOS, ids=[r["id"] for r in REPOS])
class TestAPIWithRealData:
    """Seed real parsed data into the DB and test all API endpoints."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup(self, repo_def):
        """Create fresh tables and seed real data for this language."""
        await drop_tables()
        await create_tables()

        data = _get_repo(repo_def)
        lang = repo_def["id"]
        self.repo_id = f"r-{lang}"
        self.snapshot_id = f"s-{lang}"

        # Seed via the same session the API uses
        async for db in override_get_db():
            db.add(Repo(
                id=self.repo_id, name=repo_def["name"], url=repo_def["url"],
            ))
            db.add(RepoSnapshot(
                id=self.snapshot_id, repo_id=self.repo_id,
                commit_sha=data["sha"],
                status=SnapshotStatus.completed,
                file_count=len(data["files"]),
            ))
            for f in data["files"]:
                db.add(File(
                    snapshot_id=self.snapshot_id, path=f["path"],
                    language=f["language"], hash=f["hash"],
                    size_bytes=f["size_bytes"],
                ))
            for sym in data["graph"].symbols.values():
                db.add(Symbol(
                    snapshot_id=self.snapshot_id,
                    kind=sym.kind.value, name=sym.name,
                    fq_name=sym.fq_name, file_path=sym.file_path,
                    start_line=sym.start_line, end_line=sym.end_line,
                    namespace=sym.namespace or "",
                    parent_fq_name=sym.parent_fq_name or "",
                    signature=sym.signature or "",
                    modifiers=",".join(sym.modifiers) if sym.modifiers else "",
                    return_type=sym.return_type or "",
                ))
            for edge in data["graph"].edges:
                db.add(EdgeModel(
                    snapshot_id=self.snapshot_id,
                    source_fq_name=edge.source_fq_name,
                    target_fq_name=edge.target_fq_name,
                    edge_type=edge.edge_type.value,
                    file_path=edge.file_path or "",
                    line=edge.line,
                ))
            await db.commit()

        yield
        await drop_tables()

    @pytest_asyncio.fixture
    async def client(self):
        with patch("app.api.repos.run_ingestion", new_callable=AsyncMock):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as ac:
                yield ac

    @pytest.mark.asyncio
    async def test_symbols_api(self, repo_def, client):
        """GET /symbols returns real symbols from the parsed repo."""
        resp = await client.get(
            f"/repos/{self.repo_id}/snapshots/{self.snapshot_id}/symbols"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) > 0
        print(f"\n  [{repo_def['id']}] API symbols: {data['total']}")
        assert data["total"] > 0

    @pytest.mark.asyncio
    async def test_edges_api(self, repo_def, client):
        """GET /edges returns relationships."""
        resp = await client.get(
            f"/repos/{self.repo_id}/snapshots/{self.snapshot_id}/edges"
        )
        assert resp.status_code == 200
        data = resp.json()
        print(f"\n  [{repo_def['id']}] API edges: {data['total']}")

    @pytest.mark.asyncio
    async def test_overview_api(self, repo_def, client):
        """GET /overview returns correct stats."""
        resp = await client.get(
            f"/repos/{self.repo_id}/snapshots/{self.snapshot_id}/overview"
        )
        assert resp.status_code == 200
        data = resp.json()
        print(f"\n  [{repo_def['id']}] Overview: "
              f"symbols={data['total_symbols']}, "
              f"edges={data['total_edges']}")
        assert data["total_symbols"] > 0

    @pytest.mark.asyncio
    async def test_search_api(self, repo_def, client):
        """GET /search finds symbols by name."""
        # Use first symbol name as query
        sym_resp = await client.get(
            f"/repos/{self.repo_id}/snapshots/{self.snapshot_id}/symbols",
            params={"limit": 1},
        )
        first_sym = sym_resp.json()["items"][0]
        query = first_sym["name"][:10]

        resp = await client.get(
            f"/repos/{self.repo_id}/snapshots/{self.snapshot_id}/search",
            params={"q": query},
        )
        assert resp.status_code == 200
        data = resp.json()
        print(f"\n  [{repo_def['id']}] Search '{query}': "
              f"{data['total']} results")
        assert data["total"] > 0

    @pytest.mark.asyncio
    async def test_fulltext_search_api(self, repo_def, client):
        """GET /fulltext finds symbols via ILIKE fallback."""
        sym_resp = await client.get(
            f"/repos/{self.repo_id}/snapshots/{self.snapshot_id}/symbols",
            params={"limit": 1},
        )
        first_sym = sym_resp.json()["items"][0]
        query = first_sym["name"][:8]

        resp = await client.get(
            f"/repos/{self.repo_id}/snapshots/{self.snapshot_id}/fulltext",
            params={"q": query},
        )
        assert resp.status_code == 200
        print(f"\n  [{repo_def['id']}] Fulltext '{query}': "
              f"{resp.json()['total']} results")

    @pytest.mark.asyncio
    async def test_health_api(self, repo_def, client):
        """POST /health runs code health rules on real data."""
        resp = await client.post(
            f"/repos/{self.repo_id}/snapshots/{self.snapshot_id}/health"
        )
        assert resp.status_code == 200
        data = resp.json()
        score = data.get("overall_score", 0)
        findings = data.get("findings", [])
        print(f"\n  [{repo_def['id']}] Health: score={score}/100, "
              f"findings={len(findings)}")
        assert 0 <= score <= 100

    @pytest.mark.asyncio
    async def test_diagram_api(self, repo_def, client):
        """GET /diagram generates a Mermaid diagram."""
        resp = await client.get(
            f"/repos/{self.repo_id}/snapshots/{self.snapshot_id}/diagram",
            params={"diagram_type": "class"},
        )
        assert resp.status_code == 200
        data = resp.json()
        diagram = data.get("mermaid", data.get("diagram", ""))
        print(f"\n  [{repo_def['id']}] Diagram: {len(diagram)} chars")

    @pytest.mark.asyncio
    async def test_export_json_api(self, repo_def, client):
        """GET /export returns all analysis data."""
        resp = await client.get(
            f"/repos/{self.repo_id}/snapshots/{self.snapshot_id}/export"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["symbols"]) > 0
        print(f"\n  [{repo_def['id']}] Export: "
              f"{len(data['symbols'])} symbols, "
              f"{len(data['edges'])} edges")

    @pytest.mark.asyncio
    async def test_portable_round_trip(self, repo_def, client):
        """Export .eidos, import back, verify counts match."""
        # Export
        resp = await client.get(
            f"/repos/{self.repo_id}/snapshots/{self.snapshot_id}/portable"
        )
        assert resp.status_code == 200
        eidos_bytes = resp.content

        # Verify it's valid
        payload = json.loads(gzip.decompress(eidos_bytes))
        orig_syms = len(payload["symbols"])
        orig_edges = len(payload["edges"])

        # Import
        resp2 = await client.post(
            f"/repos/{self.repo_id}/import",
            files={"file": ("test.eidos", BytesIO(eidos_bytes),
                            "application/gzip")},
        )
        assert resp2.status_code == 201
        imported = resp2.json()

        # Verify counts match
        assert imported["symbols_imported"] == orig_syms
        assert imported["edges_imported"] == orig_edges
        print(f"\n  [{repo_def['id']}] Portable round-trip: "
              f"{orig_syms} symbols, {orig_edges} edges")

    @pytest.mark.asyncio
    async def test_ask_question(self, repo_def, client):
        """POST /ask works (no LLM, deterministic answer)."""
        resp = await client.post(
            f"/repos/{self.repo_id}/snapshots/{self.snapshot_id}/ask",
            json={"question": "What does this code do?"},
        )
        assert resp.status_code == 200
        data = resp.json()
        print(f"\n  [{repo_def['id']}] Ask: confidence="
              f"{data.get('confidence', 'N/A')}")

    @pytest.mark.asyncio
    async def test_generate_docs(self, repo_def, client):
        """POST /docs generates documentation."""
        resp = await client.post(
            f"/repos/{self.repo_id}/snapshots/{self.snapshot_id}/docs"
        )
        assert resp.status_code in (200, 201)
        data = resp.json()
        doc_count = data.get("total_docs", len(data.get("docs", [])))
        print(f"\n  [{repo_def['id']}] Docs: {doc_count} generated")

    @pytest.mark.asyncio
    async def test_metrics_tracked(self, repo_def, client):
        """GET /metrics includes counters from our API calls."""
        resp = await client.get("/metrics")
        assert resp.status_code == 200
        assert "eidos_requests_total" in resp.text

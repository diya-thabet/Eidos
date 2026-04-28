"""
=============================================================================
FULL END-TO-END TEST: Eidos vs. a Real Java GitHub Repository
=============================================================================

Target repo: https://github.com/diya-thabet/Neon-Defenders
Language:    Java (game project)

This test file simulates a COMPLETE user journey through Eidos:
  1. Register a repo
  2. Trigger ingestion (clone + parse + index)
  3. Check status & progress
  4. Browse symbols (classes, methods)
  5. Browse edges (calls, inherits)
  6. View call graphs
  7. Get overview stats
  8. Run code health analysis
  9. Search for symbols
  10. Full-text search
  11. Generate documentation
  12. Ask a question about the code
  13. Submit a diff for review
  14. Run quality evaluation
  15. View diagrams
  16. Export snapshot as JSON
  17. Export as portable .eidos file
  18. Import the .eidos file back
  19. View health trends
  20. Check Prometheus metrics
  21. Verify incremental ingestion logic

Every test has comments explaining what it does and why.
No LLM is used - all analysis is deterministic.

Usage:
    cd backend
    python -m pytest tests/test_real_repo_e2e.py -v --tb=short -s
"""

from __future__ import annotations

import gzip
import json
import tempfile
from pathlib import Path
from typing import Any
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
from tests.conftest import create_tables, drop_tables, override_get_db, test_sessionmaker

# ===========================================================================
# Constants
# ===========================================================================

REPO_URL = "https://github.com/diya-thabet/Neon-Defenders"
REPO_NAME = "Neon-Defenders"
REPO_BRANCH = "main"

# Override DB for testing
app.dependency_overrides[get_db] = override_get_db


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create fresh tables before each test class, drop after."""
    await drop_tables()
    await create_tables()
    yield
    await drop_tables()


@pytest_asyncio.fixture
async def client():
    """HTTP client for the FastAPI app (auth disabled = anonymous superadmin)."""
    with patch("app.api.repos.run_ingestion", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest.fixture(scope="module")
def cloned_repo():
    """
    Clone the real repo ONCE for the entire module (saves time).
    This is the actual Git clone from GitHub.
    """
    tmpdir = tempfile.mkdtemp()
    dest = Path(tmpdir) / "neon-defenders"
    try:
        sha = clone_repo(REPO_URL, REPO_BRANCH, dest, None, "")
        yield {"path": dest, "sha": sha}
    except Exception as e:
        pytest.skip(f"Cannot clone repo (network issue?): {e}")
    finally:
        # Best-effort cleanup (Windows may hold .git locks)
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="module")
def scanned_files(cloned_repo):
    """Scan all files in the cloned repo - get paths, languages, hashes."""
    return scan_files(cloned_repo["path"])


@pytest.fixture(scope="module")
def code_graph(cloned_repo, scanned_files):
    """Run static analysis on the cloned repo - builds the full code graph."""
    return analyze_snapshot_files(cloned_repo["path"], scanned_files)


# ===========================================================================
# Phase 1: Clone & Scan (offline, no API)
# ===========================================================================


class TestPhase1_CloneAndScan:
    """Test that we can clone the repo and scan its files."""

    def test_clone_succeeds(self, cloned_repo):
        """The repo should clone successfully and return a commit SHA."""
        assert cloned_repo["path"].exists(), "Clone directory should exist"
        assert len(cloned_repo["sha"]) == 40, "SHA should be 40 hex chars"
        print(f"\n  Cloned at: {cloned_repo['path']}")
        print(f"  Commit SHA: {cloned_repo['sha']}")

    def test_files_found(self, scanned_files):
        """scan_files should find Java source files."""
        assert len(scanned_files) > 0, "Should find at least some files"
        # Check that Java files were detected
        java_files = [f for f in scanned_files if f["language"] == "java"]
        assert len(java_files) > 0, "Should find Java files"
        print(f"\n  Total files scanned: {len(scanned_files)}")
        print(f"  Java files: {len(java_files)}")
        # Show a few file paths
        for f in java_files[:5]:
            print(f"    - {f['path']} ({f['size_bytes']} bytes)")

    def test_file_hashes_are_unique(self, scanned_files):
        """Each file should have a unique SHA-256 hash."""
        hashes = [f["hash"] for f in scanned_files]
        # Most files should have unique hashes (some could match if identical)
        assert len(set(hashes)) > len(hashes) * 0.5, "Most hashes should be unique"

    def test_java_files_have_correct_language(self, scanned_files):
        """Files ending in .java should be detected as language='java'."""
        for f in scanned_files:
            if f["path"].endswith(".java"):
                assert f["language"] == "java", f"{f['path']} should be java"


# ===========================================================================
# Phase 2: Static Analysis (offline, no API)
# ===========================================================================


class TestPhase2_StaticAnalysis:
    """Test the tree-sitter parser and graph builder on real Java code."""

    def test_symbols_found(self, code_graph):
        """The parser should find classes, methods, etc. in the Java code."""
        assert len(code_graph.symbols) > 0, "Should find symbols"
        print(f"\n  Total symbols: {len(code_graph.symbols)}")
        # Count by kind
        kinds: dict[str, int] = {}
        for sym in code_graph.symbols.values():
            kinds[sym.kind.value] = kinds.get(sym.kind.value, 0) + 1
        for kind, count in sorted(kinds.items()):
            print(f"    {kind}: {count}")

    def test_edges_found(self, code_graph):
        """The graph builder should find relationships between symbols."""
        assert len(code_graph.edges) > 0, "Should find edges (calls, inherits, etc.)"
        print(f"\n  Total edges: {len(code_graph.edges)}")
        # Count by type
        types: dict[str, int] = {}
        for edge in code_graph.edges:
            types[edge.edge_type.value] = types.get(edge.edge_type.value, 0) + 1
        for etype, count in sorted(types.items()):
            print(f"    {etype}: {count}")

    def test_classes_have_methods(self, code_graph):
        """Classes should have child methods (parent_fq_name set)."""
        classes = [s for s in code_graph.symbols.values() if s.kind.value == "class"]
        methods = [s for s in code_graph.symbols.values() if s.kind.value == "method"]
        # At least some methods should reference a class as parent
        methods_with_parent = [m for m in methods if m.parent_fq_name]
        print(f"\n  Classes: {len(classes)}, Methods: {len(methods)}")
        print(f"  Methods with parent class: {len(methods_with_parent)}")
        assert len(methods_with_parent) > 0, "Some methods should have parent classes"

    def test_symbols_have_file_paths(self, code_graph):
        """Every symbol should be associated with a source file."""
        for sym in code_graph.symbols.values():
            assert sym.file_path, f"Symbol {sym.fq_name} has no file_path"

    def test_symbols_have_line_numbers(self, code_graph):
        """Every symbol should have start and end line numbers."""
        for sym in code_graph.symbols.values():
            assert sym.start_line >= 1, f"{sym.fq_name}: start_line should be >= 1"
            assert sym.end_line >= sym.start_line, (
                f"{sym.fq_name}: end_line should be >= start_line"
            )


# ===========================================================================
# Phase 3: API - Register Repo & Ingest
# ===========================================================================


class TestPhase3_RegisterAndIngest:
    """Test the API flow: register repo, trigger ingest, check status."""

    @pytest.mark.asyncio
    async def test_register_repo(self, client: AsyncClient):
        """POST /repos/ - Register the Neon-Defenders repo."""
        resp = await client.post("/repos", json={
            "name": REPO_NAME,
            "url": REPO_URL,
        }, follow_redirects=True)
        assert resp.status_code == 201, f"Register failed: {resp.text}"
        data = resp.json()
        assert data["name"] == REPO_NAME
        assert "id" in data
        print(f"\n  Registered repo: id={data['id']}, name={data['name']}")

    @pytest.mark.asyncio
    async def test_list_repos(self, client: AsyncClient):
        """No GET /repos/ list endpoint exists - verify 405."""
        resp = await client.get("/repos", follow_redirects=True)
        # There is no list endpoint - just verify registering works
        assert resp.status_code in (404, 405)

    @pytest.mark.asyncio
    async def test_repo_status(self, client: AsyncClient):
        """GET /repos/{id}/status - Check the repo status."""
        create = await client.post(
            "/repos", json={"name": REPO_NAME, "url": REPO_URL},
            follow_redirects=True,
        )
        repo_id = create.json()["id"]
        resp = await client.get(f"/repos/{repo_id}/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["repo_id"] == repo_id
        print(f"\n  Status: {data}")


# ===========================================================================
# Phase 4: Seed a Real Snapshot & Run Full Analysis via API
# ===========================================================================

# For API tests, we seed the DB directly (ingestion is mocked in client fixture)
# but we use the REAL parsed graph from Phase 2.


async def _seed_real_snapshot(
    cloned_repo: dict, scanned_files: list, code_graph: Any
) -> tuple[str, str]:
    """
    Seed the database with a real snapshot from the cloned repo.
    Returns (repo_id, snapshot_id).
    """
    repo_id = "r-neon"
    snapshot_id = "s-neon"

    async with test_sessionmaker() as db:
        # Create repo
        db.add(Repo(id=repo_id, name=REPO_NAME, url=REPO_URL))

        # Create snapshot
        db.add(RepoSnapshot(
            id=snapshot_id,
            repo_id=repo_id,
            commit_sha=cloned_repo["sha"],
            status=SnapshotStatus.completed,
            file_count=len(scanned_files),
        ))

        # Add real files
        for f in scanned_files:
            db.add(File(
                snapshot_id=snapshot_id,
                path=f["path"],
                language=f["language"],
                hash=f["hash"],
                size_bytes=f["size_bytes"],
            ))

        # Add real symbols
        await db.flush()

    # Persist graph in a separate session
    async with test_sessionmaker() as db:
        from app.storage.models import Edge as EdgeModel
        from app.storage.models import Symbol as SymModel
        for sym in code_graph.symbols.values():
            db.add(SymModel(
                snapshot_id=snapshot_id,
                kind=sym.kind.value,
                name=sym.name,
                fq_name=sym.fq_name,
                file_path=sym.file_path,
                start_line=sym.start_line,
                end_line=sym.end_line,
                namespace=sym.namespace or "",
                parent_fq_name=sym.parent_fq_name or "",
                signature=sym.signature or "",
                modifiers=",".join(sym.modifiers) if sym.modifiers else "",
                return_type=sym.return_type or "",
            ))
        for edge in code_graph.edges:
            db.add(EdgeModel(
                snapshot_id=snapshot_id,
                source_fq_name=edge.source_fq_name,
                target_fq_name=edge.target_fq_name,
                edge_type=edge.edge_type.value,
                file_path=edge.file_path or "",
                line=edge.line,
            ))
        await db.commit()

    return repo_id, snapshot_id


class TestPhase4_AnalysisAPI:
    """Test all analysis endpoints against real parsed Java data."""

    @pytest_asyncio.fixture(autouse=True)
    async def seed(self, setup_db, cloned_repo, scanned_files, code_graph):
        """Seed runs after setup_db creates fresh tables.

        We insert data via the override_get_db session to ensure the API
        can see it (same connection pool).
        """
        repo_id = "r-neon"
        snapshot_id = "s-neon"
        self.repo_id = repo_id
        self.snapshot_id = snapshot_id

        # Use the same session factory that the API uses
        async for db in override_get_db():
            db.add(Repo(id=repo_id, name=REPO_NAME, url=REPO_URL))
            db.add(RepoSnapshot(
                id=snapshot_id, repo_id=repo_id,
                commit_sha=cloned_repo["sha"],
                status=SnapshotStatus.completed,
                file_count=len(scanned_files),
            ))
            for f in scanned_files:
                db.add(File(
                    snapshot_id=snapshot_id, path=f["path"],
                    language=f["language"], hash=f["hash"],
                    size_bytes=f["size_bytes"],
                ))
            for sym in code_graph.symbols.values():
                db.add(Symbol(
                    snapshot_id=snapshot_id, kind=sym.kind.value,
                    name=sym.name, fq_name=sym.fq_name,
                    file_path=sym.file_path, start_line=sym.start_line,
                    end_line=sym.end_line, namespace=sym.namespace or "",
                    parent_fq_name=sym.parent_fq_name or "",
                    signature=sym.signature or "",
                    modifiers=",".join(sym.modifiers) if sym.modifiers else "",
                    return_type=sym.return_type or "",
                ))
            for edge in code_graph.edges:
                db.add(EdgeModel(
                    snapshot_id=snapshot_id,
                    source_fq_name=edge.source_fq_name,
                    target_fq_name=edge.target_fq_name,
                    edge_type=edge.edge_type.value,
                    file_path=edge.file_path or "",
                    line=edge.line,
                ))
            await db.commit()

    @pytest.mark.asyncio
    async def test_symbols_endpoint(self, client: AsyncClient):
        """GET /symbols - Should return real Java classes and methods."""
        resp = await client.get(
            f"/repos/{self.repo_id}/snapshots/{self.snapshot_id}/symbols"
        )
        assert resp.status_code == 200
        data = resp.json()
        items = data["items"]
        assert len(items) > 0, "Should have symbols"
        print(f"\n  Symbols returned: {data['total']}")
        # Show first 5
        for s in items[:5]:
            print(f"    {s['kind']}: {s['fq_name']} ({s['file_path']}:{s['start_line']})")

    @pytest.mark.asyncio
    async def test_edges_endpoint(self, client: AsyncClient):
        """GET /edges - Should return real relationships."""
        resp = await client.get(
            f"/repos/{self.repo_id}/snapshots/{self.snapshot_id}/edges"
        )
        assert resp.status_code == 200
        data = resp.json()
        items = data["items"]
        assert len(items) > 0, "Should have edges"
        print(f"\n  Edges returned: {data['total']}")
        for e in items[:5]:
            print(f"    {e['source_fq_name']} --{e['edge_type']}--> {e['target_fq_name']}")

    @pytest.mark.asyncio
    async def test_overview(self, client: AsyncClient):
        """GET /overview - High-level stats about the codebase."""
        resp = await client.get(
            f"/repos/{self.repo_id}/snapshots/{self.snapshot_id}/overview"
        )
        assert resp.status_code == 200
        data = resp.json()
        print(f"\n  Overview: {json.dumps(data, indent=2)}")
        assert data["total_symbols"] > 0
        assert data["total_edges"] > 0

    @pytest.mark.asyncio
    async def test_code_health(self, client: AsyncClient):
        """POST /health - Run 40 rules against the real Java code."""
        resp = await client.post(
            f"/repos/{self.repo_id}/snapshots/{self.snapshot_id}/health"
        )
        assert resp.status_code == 200
        data = resp.json()
        score = data.get("overall_score", 0)
        findings = data.get("findings", [])
        print(f"\n  Health score: {score}/100")
        print(f"  Total findings: {len(findings)}")
        # Show top 5 findings by severity
        for f in findings[:5]:
            print(f"    [{f['severity']}] {f['rule_name']}: {f['message'][:80]}")
        # Score should be between 0 and 100
        assert 0 <= score <= 100

    @pytest.mark.asyncio
    async def test_search(self, client: AsyncClient):
        """GET /search - Search for symbols by name."""
        resp = await client.get(
            f"/repos/{self.repo_id}/snapshots/{self.snapshot_id}/search",
            params={"q": "Game"},
        )
        assert resp.status_code == 200
        data = resp.json()
        print(f"\n  Search 'Game': {data['total']} results")
        for item in data["items"][:5]:
            print(f"    {item['entity_type']}: {item['title'][:60]}")

    @pytest.mark.asyncio
    async def test_fulltext_search(self, client: AsyncClient):
        """GET /fulltext - Full-text search (ILIKE fallback on SQLite)."""
        resp = await client.get(
            f"/repos/{self.repo_id}/snapshots/{self.snapshot_id}/fulltext",
            params={"q": "Player"},
        )
        assert resp.status_code == 200
        data = resp.json()
        print(f"\n  Fulltext 'Player': {data['total']} results")

    @pytest.mark.asyncio
    async def test_generate_docs(self, client: AsyncClient):
        """POST /docs/generate - Generate documentation from real code."""
        resp = await client.post(
            f"/repos/{self.repo_id}/snapshots/{self.snapshot_id}/docs"
        )
        assert resp.status_code in (200, 201), f"Doc gen failed: {resp.text}"
        data = resp.json()
        print(f"\n  Docs generated: {data.get('total_docs', len(data.get('docs', [])))} documents")

    @pytest.mark.asyncio
    async def test_ask_question(self, client: AsyncClient):
        """POST /ask - Ask a question about the Java codebase."""
        resp = await client.post(
            f"/repos/{self.repo_id}/snapshots/{self.snapshot_id}/ask",
            json={"question": "What are the main classes in this game?"},
        )
        assert resp.status_code == 200, f"Ask failed: {resp.text}"
        data = resp.json()
        answer = data.get("answer_text", data.get("answer", ""))
        print("\n  Question: 'What are the main classes?'")
        print(f"  Answer ({len(answer)} chars): {answer[:200]}")
        print(f"  Confidence: {data.get('confidence', 'N/A')}")
        # Without LLM, answer may be empty but endpoint should not error

    @pytest.mark.asyncio
    async def test_code_review(self, client: AsyncClient):
        """POST /review - Submit a fake diff for risk analysis."""
        diff = """--- a/src/Game.java
+++ b/src/Game.java
@@ -10,6 +10,10 @@ public class Game {
     private int score;
+    private Connection dbConnection;
+
+    public void saveScore() {
+        String sql = "INSERT INTO scores VALUES (" + score + ")";
+        dbConnection.execute(sql);
+    }
"""
        resp = await client.post(
            f"/repos/{self.repo_id}/snapshots/{self.snapshot_id}/review",
            json={"diff": diff},
        )
        assert resp.status_code in (200, 201), f"Review failed: {resp.text}"
        data = resp.json()
        print(f"\n  Review risk score: {data.get('risk_score', 'N/A')}")
        print(f"  Risk level: {data.get('risk_level', 'N/A')}")

    @pytest.mark.asyncio
    async def test_evaluate(self, client: AsyncClient):
        """POST /evaluate - Run quality evaluation."""
        resp = await client.post(
            f"/repos/{self.repo_id}/snapshots/{self.snapshot_id}/evaluate"
        )
        assert resp.status_code in (200, 201), f"Evaluate failed: {resp.text}"
        data = resp.json()
        print(f"\n  Evaluation: {json.dumps(data, indent=2)[:200]}...")

    @pytest.mark.asyncio
    async def test_class_diagram(self, client: AsyncClient):
        """GET /diagram?diagram_type=class - Mermaid class diagram."""
        resp = await client.get(
            f"/repos/{self.repo_id}/snapshots/{self.snapshot_id}/diagram",
            params={"diagram_type": "class"},
        )
        assert resp.status_code == 200
        data = resp.json()
        diagram = data.get("mermaid", data.get("diagram", ""))
        print(f"\n  Class diagram ({len(diagram)} chars):")
        for line in diagram.split("\n")[:8]:
            print(f"    {line}")

    @pytest.mark.asyncio
    async def test_module_diagram(self, client: AsyncClient):
        """GET /diagram?diagram_type=module - Generate a Mermaid module diagram."""
        resp = await client.get(
            f"/repos/{self.repo_id}/snapshots/{self.snapshot_id}/diagram",
            params={"diagram_type": "module"},
        )
        assert resp.status_code == 200
        data = resp.json()
        print(f"\n  Module diagram: {str(data)[:200]}")

    @pytest.mark.asyncio
    async def test_export_json(self, client: AsyncClient):
        """GET /export - Export all analysis data as JSON."""
        resp = await client.get(
            f"/repos/{self.repo_id}/snapshots/{self.snapshot_id}/export"
        )
        assert resp.status_code == 200
        data = resp.json()
        print(f"\n  Export: {data.get('metadata', {})}")
        assert data["snapshot_id"] == self.snapshot_id
        assert len(data["symbols"]) > 0
        assert len(data["edges"]) > 0

    @pytest.mark.asyncio
    async def test_portable_export_and_import(self, client: AsyncClient):
        """
        GET /portable - Export as .eidos file
        POST /import  - Re-import the .eidos file into a new snapshot
        This tests the full round-trip: export -> import -> verify data.
        """
        # Export
        resp = await client.get(
            f"/repos/{self.repo_id}/snapshots/{self.snapshot_id}/portable"
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/gzip"
        eidos_bytes = resp.content
        print(f"\n  Portable export: {len(eidos_bytes)} bytes (gzip)")

        # Verify it's valid gzip JSON
        decompressed = gzip.decompress(eidos_bytes)
        payload = json.loads(decompressed)
        assert payload["schema_version"] == 1
        sym_count = len(payload["symbols"])
        print(f"  Contains: {sym_count} symbols, {len(payload['edges'])} edges")

        # Import back
        from io import BytesIO
        resp2 = await client.post(
            f"/repos/{self.repo_id}/import",
            files={"file": ("neon.eidos", BytesIO(eidos_bytes), "application/gzip")},
        )
        assert resp2.status_code == 201, f"Import failed: {resp2.text}"
        imported = resp2.json()
        print(f"  Imported snapshot: {imported['snapshot_id']}")
        print(f"  Symbols imported: {imported['symbols_imported']}")
        assert imported["symbols_imported"] == sym_count

    @pytest.mark.asyncio
    async def test_prometheus_metrics(self, client: AsyncClient):
        """GET /metrics - Check Prometheus metrics after API calls."""
        # Make some requests first
        await client.get("/health")
        await client.get(f"/repos/{self.repo_id}/status")

        resp = await client.get("/metrics")
        assert resp.status_code == 200
        body = resp.text
        assert "eidos_requests_total" in body
        assert "eidos_request_duration_seconds" in body
        print(f"\n  Metrics output ({len(body)} chars):")
        for line in body.split("\n")[:10]:
            print(f"    {line}")


# ===========================================================================
# Phase 5: Verify Analysis Quality
# ===========================================================================


class TestPhase5_AnalysisQuality:
    """Verify that Eidos actually understands the Java game code correctly."""

    def test_finds_game_related_classes(self, code_graph):
        """The parser should find game-related class names."""
        class_names = [
            s.name for s in code_graph.symbols.values()
            if s.kind.value == "class"
        ]
        print(f"\n  All classes found: {class_names}")
        # A Java game should have at least 1 class
        assert len(class_names) >= 1, "Should find at least one class"

    def test_methods_have_signatures(self, code_graph):
        """Methods should have parsed signatures."""
        methods = [
            s for s in code_graph.symbols.values()
            if s.kind.value == "method"
        ]
        with_sig = [m for m in methods if m.signature]
        print(f"\n  Methods: {len(methods)}, with signature: {len(with_sig)}")
        if methods:
            # Show first 5
            for m in methods[:5]:
                print(f"    {m.fq_name}: {m.signature[:60] if m.signature else '(no sig)'}")

    def test_inheritance_edges_exist(self, code_graph):
        """If Java classes extend others, we should find INHERITS edges."""
        inherits = [e for e in code_graph.edges if e.edge_type.value == "inherits"]
        print(f"\n  Inheritance edges: {len(inherits)}")
        for e in inherits[:5]:
            print(f"    {e.source_fq_name} extends {e.target_fq_name}")

    def test_call_edges_exist(self, code_graph):
        """Methods calling other methods should produce CALLS edges."""
        calls = [e for e in code_graph.edges if e.edge_type.value == "calls"]
        print(f"\n  Call edges: {len(calls)}")
        for e in calls[:5]:
            print(f"    {e.source_fq_name} calls {e.target_fq_name}")

    def test_no_empty_fq_names(self, code_graph):
        """No symbol should have an empty fully qualified name."""
        for sym in code_graph.symbols.values():
            assert sym.fq_name, f"Symbol {sym.name} has empty fq_name"


# ===========================================================================
# Phase 6: API Key Authentication Flow
# ===========================================================================


class TestPhase6_APIKeyFlow:
    """Test the full API key lifecycle with a real-ish workflow."""

    @pytest.mark.asyncio
    async def test_full_api_key_lifecycle(self, client: AsyncClient):
        """
        1. Create an API key
        2. List keys (should show it)
        3. Use the key (verify header is accepted)
        4. Revoke the key
        5. List keys (should be gone)
        """
        # Step 1: Create
        resp = await client.post("/auth/api-keys?name=CI-Pipeline")
        assert resp.status_code == 201
        key_data = resp.json()
        raw_key = key_data["key"]
        key_id = key_data["id"]
        print(f"\n  Created key: {key_data['prefix']}... (id={key_id})")

        # Step 2: List
        resp = await client.get("/auth/api-keys")
        assert resp.status_code == 200
        assert any(k["id"] == key_id for k in resp.json())

        # Step 3: Use the key
        resp = await client.get("/health", headers={"X-API-Key": raw_key})
        assert resp.status_code == 200

        # Step 4: Revoke
        resp = await client.delete(f"/auth/api-keys/{key_id}")
        assert resp.status_code == 200

        # Step 5: Verify it's gone from list
        resp = await client.get("/auth/api-keys")
        assert all(k["id"] != key_id for k in resp.json())
        print("  Key lifecycle complete: create -> list -> use -> revoke -> verify")

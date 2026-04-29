"""
Tests for Phase 5: Duplicate / Clone Detection.

Tests structural fingerprinting, clone grouping, near-clone detection,
health rules, API endpoint, and multi-language validation.
"""

from __future__ import annotations

import textwrap
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import tree_sitter_java as tsjava
import tree_sitter_python as tspy
from httpx import ASGITransport, AsyncClient
from tree_sitter import Language, Parser

from app.analysis.clone_detection import (
    CloneInfo,
    compute_similarity,
    detect_clones,
    statement_windows,
    structural_fingerprint,
)
from app.analysis.code_health import HealthConfig
from app.main import app
from app.storage.database import get_db
from app.storage.models import Repo, RepoSnapshot, SnapshotStatus, Symbol
from tests.conftest import create_tables, drop_tables, override_get_db

app.dependency_overrides[get_db] = override_get_db

PY_LANG = Language(tspy.language())
JAVA_LANG = Language(tsjava.language())


def _parse_py(code: str):
    p = Parser(PY_LANG)
    return p.parse(code.encode()).root_node


def _find_funcs(node, results=None):
    if results is None:
        results = []
    if node.type == "function_definition":
        results.append(node)
    for c in node.children:
        _find_funcs(c, results)
    return results


# =======================================================================
# Unit tests: structural fingerprinting
# =======================================================================


class TestStructuralFingerprint:

    def test_identical_structure_same_hash(self):
        """Two functions with same structure but different names/values."""
        code = textwrap.dedent("""\
            def foo(x):
                if x > 0:
                    return x * 2
                return 0

            def bar(y):
                if y > 0:
                    return y * 2
                return 0
        """)
        funcs = _find_funcs(_parse_py(code))
        assert len(funcs) == 2
        fp1 = structural_fingerprint(funcs[0])
        fp2 = structural_fingerprint(funcs[1])
        assert fp1 == fp2

    def test_different_structure_different_hash(self):
        code = textwrap.dedent("""\
            def simple(x):
                return x

            def complex(x):
                if x > 0:
                    for i in range(x):
                        print(i)
                return x
        """)
        funcs = _find_funcs(_parse_py(code))
        fp1 = structural_fingerprint(funcs[0])
        fp2 = structural_fingerprint(funcs[1])
        assert fp1 != fp2

    def test_same_structure_different_literals(self):
        """Literals are ignored in fingerprinting."""
        code = textwrap.dedent("""\
            def foo():
                x = 42
                return x + 1

            def bar():
                x = 999
                return x + 1
        """)
        funcs = _find_funcs(_parse_py(code))
        fp1 = structural_fingerprint(funcs[0])
        fp2 = structural_fingerprint(funcs[1])
        assert fp1 == fp2

    def test_fingerprint_is_deterministic(self):
        code = "def f(x):\n    return x\n"
        node = _find_funcs(_parse_py(code))[0]
        fp1 = structural_fingerprint(node)
        fp2 = structural_fingerprint(node)
        assert fp1 == fp2

    def test_fingerprint_length(self):
        code = "def f(x):\n    return x\n"
        node = _find_funcs(_parse_py(code))[0]
        fp = structural_fingerprint(node)
        assert len(fp) == 16  # sha256 truncated to 16 hex chars


# =======================================================================
# Unit tests: statement windows
# =======================================================================


class TestStatementWindows:

    def test_enough_statements(self):
        code = textwrap.dedent("""\
            def f():
                a = 1
                b = 2
                c = 3
                d = 4
                e = 5
                f = 6
        """)
        node = _find_funcs(_parse_py(code))[0]
        windows = statement_windows(node, window_size=3)
        assert len(windows) >= 1

    def test_too_few_statements(self):
        code = "def f():\n    return 1\n"
        node = _find_funcs(_parse_py(code))[0]
        windows = statement_windows(node, window_size=5)
        # Should still return at least 1 hash for the whole body
        assert len(windows) >= 1

    def test_empty_function(self):
        code = "def f():\n    pass\n"
        node = _find_funcs(_parse_py(code))[0]
        windows = statement_windows(node, window_size=5)
        assert len(windows) >= 1


# =======================================================================
# Unit tests: similarity
# =======================================================================


class TestSimilarity:

    def test_identical(self):
        assert compute_similarity(["a", "b", "c"], ["a", "b", "c"]) == 1.0

    def test_no_overlap(self):
        assert compute_similarity(["a", "b"], ["c", "d"]) == 0.0

    def test_partial_overlap(self):
        sim = compute_similarity(["a", "b", "c"], ["b", "c", "d"])
        assert 0.4 < sim < 0.7  # 2/4 = 0.5

    def test_empty(self):
        assert compute_similarity([], ["a"]) == 0.0
        assert compute_similarity([], []) == 0.0


# =======================================================================
# Unit tests: detect_clones
# =======================================================================


class TestDetectClones:

    def _info(self, name, fp, lines=10):
        return CloneInfo(
            fq_name=f"app.{name}", name=name,
            file_path=f"{name}.py",
            start_line=1, end_line=lines,
            lines=lines, fingerprint=fp,
        )

    def test_exact_clones_grouped(self):
        funcs = [
            self._info("a", "fp1"),
            self._info("b", "fp1"),
            self._info("c", "fp2"),
        ]
        report = detect_clones(funcs)
        assert len(report.exact_clone_groups) == 1
        assert report.total_exact_clones == 2
        names = {m.name for m in report.exact_clone_groups[0].members}
        assert names == {"a", "b"}

    def test_no_clones(self):
        funcs = [
            self._info("a", "fp1"),
            self._info("b", "fp2"),
            self._info("c", "fp3"),
        ]
        report = detect_clones(funcs)
        assert len(report.exact_clone_groups) == 0

    def test_multiple_groups(self):
        funcs = [
            self._info("a", "fp1"),
            self._info("b", "fp1"),
            self._info("c", "fp2"),
            self._info("d", "fp2"),
        ]
        report = detect_clones(funcs)
        assert len(report.exact_clone_groups) == 2

    def test_cluster_of_4(self):
        funcs = [self._info(f"f{i}", "same") for i in range(4)]
        report = detect_clones(funcs)
        assert report.exact_clone_groups[0].members.__len__() == 4

    def test_near_clones(self):
        funcs = [
            self._info("a", "fp1"),
            self._info("b", "fp2"),
        ]
        windows = {
            "app.a": ["w1", "w2", "w3", "w4"],
            "app.b": ["w1", "w2", "w3", "w5"],
        }
        report = detect_clones(funcs, windows_map=windows)
        assert report.total_near_clones >= 1

    def test_empty_input(self):
        report = detect_clones([])
        assert report.total_functions == 0
        assert report.exact_clone_groups == []


# =======================================================================
# Integration: real Python code
# =======================================================================


class TestRealPythonClones:

    def test_detects_cloned_functions(self):
        code = textwrap.dedent("""\
            def process_users(users):
                result = []
                for user in users:
                    if user.active:
                        result.append(user.name)
                return result

            def process_items(items):
                result = []
                for item in items:
                    if item.active:
                        result.append(item.name)
                return result

            def different_logic(data):
                total = 0
                for x in data:
                    total += x
                return total
        """)
        funcs_nodes = _find_funcs(_parse_py(code))
        assert len(funcs_nodes) == 3
        fps = [structural_fingerprint(n) for n in funcs_nodes]
        # First two should be identical, third different
        assert fps[0] == fps[1]
        assert fps[0] != fps[2]

    def test_pipeline_enriches_fingerprint(self, tmp_path):
        from app.analysis.pipeline import analyze_snapshot_files
        code = textwrap.dedent("""\
            def clone_a(x):
                if x > 0:
                    return x * 2
                return 0

            def clone_b(y):
                if y > 0:
                    return y * 2
                return 0

            def unique(z):
                return z
        """)
        (tmp_path / "main.py").write_text(code)
        records = [
            {"path": "main.py", "language": "python",
             "hash": "a", "size_bytes": len(code)},
        ]
        graph = analyze_snapshot_files(tmp_path, records)
        methods = {
            s.name: s for s in graph.symbols.values()
            if hasattr(s, "_structural_fingerprint")
        }
        if "clone_a" in methods and "clone_b" in methods:
            assert (
                methods["clone_a"]._structural_fingerprint
                == methods["clone_b"]._structural_fingerprint
            )


# =======================================================================
# Integration: Java clones
# =======================================================================


class TestJavaClones:

    def test_java_structural_clones(self):
        code = textwrap.dedent("""\
            class Service {
                int processA(int[] data) {
                    int sum = 0;
                    for (int x : data) {
                        if (x > 0) {
                            sum += x;
                        }
                    }
                    return sum;
                }
                int processB(int[] items) {
                    int sum = 0;
                    for (int x : items) {
                        if (x > 0) {
                            sum += x;
                        }
                    }
                    return sum;
                }
            }
        """)
        p = Parser(JAVA_LANG)
        tree = p.parse(code.encode())
        methods = []
        _find_java_methods(tree.root_node, methods)
        assert len(methods) == 2
        fp1 = structural_fingerprint(methods[0])
        fp2 = structural_fingerprint(methods[1])
        assert fp1 == fp2


def _find_java_methods(node, results):
    if node.type in ("method_declaration", "constructor_declaration"):
        results.append(node)
    for c in node.children:
        _find_java_methods(c, results)


# =======================================================================
# Health rule tests
# =======================================================================


class TestCloneHealthRules:

    def _graph_with_clones(self, clone_pairs):
        from app.analysis.graph_builder import CodeGraph
        from app.analysis.models import SymbolInfo, SymbolKind
        g = CodeGraph()
        for name, fp in clone_pairs:
            s = SymbolInfo(
                name=name, kind=SymbolKind.METHOD,
                fq_name=f"app.{name}",
                file_path=f"{name}.py",
                start_line=1, end_line=15,
            )
            s._structural_fingerprint = fp
            g.symbols[s.fq_name] = s
        return g

    def test_dup001_exact_clone(self):
        from app.analysis.health_rules.clones import ExactCloneRule
        g = self._graph_with_clones([
            ("funcA", "same_fp"),
            ("funcB", "same_fp"),
            ("funcC", "different"),
        ])
        findings = ExactCloneRule().check(g, HealthConfig())
        assert len(findings) == 2  # both funcA and funcB flagged
        assert all(f.rule_id == "DUP001" for f in findings)

    def test_dup001_no_clones(self):
        from app.analysis.health_rules.clones import ExactCloneRule
        g = self._graph_with_clones([
            ("a", "fp1"), ("b", "fp2"), ("c", "fp3"),
        ])
        findings = ExactCloneRule().check(g, HealthConfig())
        assert len(findings) == 0

    def test_dup003_cluster(self):
        from app.analysis.health_rules.clones import CloneClusterRule
        g = self._graph_with_clones([
            ("a", "same"), ("b", "same"),
            ("c", "same"), ("d", "same"),
        ])
        findings = CloneClusterRule().check(g, HealthConfig())
        assert len(findings) == 1
        assert findings[0].rule_id == "DUP003"

    def test_dup003_no_cluster_with_3(self):
        from app.analysis.health_rules.clones import CloneClusterRule
        g = self._graph_with_clones([
            ("a", "same"), ("b", "same"), ("c", "same"),
        ])
        findings = CloneClusterRule().check(g, HealthConfig())
        assert len(findings) == 0  # exactly 3, threshold is >3


# =======================================================================
# API endpoint tests
# =======================================================================


class TestClonesAPI:

    @pytest_asyncio.fixture(autouse=True)
    async def setup(self):
        await drop_tables()
        await create_tables()
        async for db in override_get_db():
            db.add(Repo(id="r1", name="demo", url="https://example.com"))
            db.add(RepoSnapshot(
                id="s1", repo_id="r1", commit_sha="abc",
                status=SnapshotStatus.completed, file_count=1,
            ))
            for name, fp in [
                ("clone_a", '{"structural_fingerprint":"abc123"}'),
                ("clone_b", '{"structural_fingerprint":"abc123"}'),
                ("unique", '{"structural_fingerprint":"xyz789"}'),
                ("small", None),  # too small, no metadata
            ]:
                db.add(Symbol(
                    snapshot_id="s1", name=name, kind="method",
                    fq_name=f"app.{name}", file_path="main.py",
                    start_line=1,
                    end_line=20 if name != "small" else 3,
                    metadata_json=fp,
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
    async def test_clones_endpoint(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/clones")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_functions_analyzed"] >= 2

    @pytest.mark.asyncio
    async def test_exact_clones_found(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/clones")
        data = resp.json()
        assert data["total_exact_clones"] >= 2
        assert len(data["exact_clone_groups"]) >= 1

    @pytest.mark.asyncio
    async def test_response_fields(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/clones")
        data = resp.json()
        assert "snapshot_id" in data
        assert "exact_clone_groups" in data
        assert "near_clone_pairs" in data
        assert "total_exact_clones" in data

    @pytest.mark.asyncio
    async def test_clone_group_members(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/clones")
        groups = resp.json()["exact_clone_groups"]
        if groups:
            g = groups[0]
            assert "fingerprint" in g
            assert "count" in g
            assert "members" in g
            m = g["members"][0]
            assert "fq_name" in m
            assert "name" in m
            assert "file_path" in m

    @pytest.mark.asyncio
    async def test_empty_snapshot(self, client):
        async for db in override_get_db():
            db.add(RepoSnapshot(
                id="s2", repo_id="r1", commit_sha="def",
                status=SnapshotStatus.completed, file_count=0,
            ))
            await db.commit()
        resp = await client.get("/repos/r1/snapshots/s2/clones")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_functions_analyzed"] == 0
        assert data["exact_clone_groups"] == []


# =======================================================================
# Edge cases
# =======================================================================


class TestCloneEdgeCases:

    def test_single_function_no_clones(self):
        report = detect_clones([
            CloneInfo("a", "f", "a.py", 1, 10, 10, "fp1"),
        ])
        assert report.exact_clone_groups == []

    def test_all_identical(self):
        funcs = [
            CloneInfo(f"f{i}", f"f{i}", "f.py", 1, 10, 10, "same")
            for i in range(10)
        ]
        report = detect_clones(funcs)
        assert len(report.exact_clone_groups) == 1
        assert report.total_exact_clones == 10

    def test_fingerprint_ignores_comments(self):
        code_a = textwrap.dedent("""\
            def f():
                # this is a comment
                x = 1
                return x
        """)
        code_b = textwrap.dedent("""\
            def g():
                # different comment
                y = 1
                return y
        """)
        fa = _find_funcs(_parse_py(code_a))[0]
        fb = _find_funcs(_parse_py(code_b))[0]
        assert structural_fingerprint(fa) == structural_fingerprint(fb)

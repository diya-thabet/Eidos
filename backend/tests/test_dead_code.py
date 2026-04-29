"""
Tests for Phase 4: Dead Code Detection.

Tests the reachability BFS, dead code classifier, health rules,
and the API endpoint.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.analysis.code_health import HealthConfig  # noqa: F401 - resolve circular
from app.analysis.dead_code import (
    analyze_dead_code,
)
from app.analysis.graph_builder import CodeGraph
from app.analysis.models import (
    EdgeInfo,
    EdgeType,
    SymbolInfo,
    SymbolKind,
)
from app.main import app
from app.storage.database import get_db
from app.storage.models import (
    Edge,
    Repo,
    RepoSnapshot,
    SnapshotStatus,
    Symbol,
)
from tests.conftest import create_tables, drop_tables, override_get_db

app.dependency_overrides[get_db] = override_get_db


# -----------------------------------------------------------------------
# Helpers: build test graphs
# -----------------------------------------------------------------------


def _sym(name: str, kind: SymbolKind = SymbolKind.METHOD,
         ns: str = "app", parent: str | None = None,
         mods: str = "public") -> SymbolInfo:
    return SymbolInfo(
        name=name, kind=kind,
        fq_name=f"{ns}.{name}",
        file_path=f"{ns}/{name}.py",
        start_line=1, end_line=10,
        namespace=ns,
        parent_fq_name=parent,
        modifiers=[mods] if mods else [],
    )


def _edge(src: str, tgt: str,
          etype: EdgeType = EdgeType.CALLS) -> EdgeInfo:
    return EdgeInfo(
        source_fq_name=src,
        target_fq_name=tgt,
        edge_type=etype,
        file_path="test.py",
        line=1,
    )


def _graph(symbols: list[SymbolInfo],
           edges: list[EdgeInfo] | None = None) -> CodeGraph:
    g = CodeGraph()
    for s in symbols:
        g.symbols[s.fq_name] = s
    if edges:
        g.edges = edges
    g.finalize()
    return g


# =======================================================================
# Unit tests: BFS reachability
# =======================================================================


class TestReachability:

    def test_single_entry_point(self):
        """main -> helper: both reachable."""
        syms = [
            _sym("main"),
            _sym("helper", mods="private"),
        ]
        edges = [_edge("app.main", "app.helper")]
        g = _graph(syms, edges)
        report = analyze_dead_code(g)
        assert report.reachable_count >= 2
        assert report.unreachable_count == 0

    def test_disconnected_function(self):
        """main exists but orphan is not connected."""
        syms = [
            _sym("main"),
            _sym("orphan", mods="private"),
        ]
        g = _graph(syms)
        report = analyze_dead_code(g)
        assert len(report.unreachable_functions) >= 1
        names = {f.name for f in report.unreachable_functions}
        assert "orphan" in names

    def test_chain_reachability(self):
        """main -> a -> b -> c: all reachable."""
        syms = [_sym("main"), _sym("a", mods=""), _sym("b", mods=""),
                _sym("c", mods="")]
        edges = [
            _edge("app.main", "app.a"),
            _edge("app.a", "app.b"),
            _edge("app.b", "app.c"),
        ]
        g = _graph(syms, edges)
        report = analyze_dead_code(g)
        assert report.unreachable_count == 0

    def test_deep_dead_chain(self):
        """a -> b -> c but nothing calls a; all three are dead."""
        syms = [
            _sym("main"),
            _sym("a", mods="private"),
            _sym("b", mods="private"),
            _sym("c", mods="private"),
        ]
        edges = [
            _edge("app.a", "app.b"),
            _edge("app.b", "app.c"),
        ]
        g = _graph(syms, edges)
        report = analyze_dead_code(g)
        dead_names = {f.name for f in report.unreachable_functions}
        assert "a" in dead_names
        assert "b" in dead_names
        assert "c" in dead_names

    def test_class_members_reachable_via_contains(self):
        """Top-level class -> method via contains: method is reachable."""
        cls = _sym("MyClass", kind=SymbolKind.CLASS)
        method = _sym("do_work", parent="app.MyClass", mods="private")
        edges = [_edge("app.MyClass", "app.do_work", EdgeType.CONTAINS)]
        g = _graph([cls, method], edges)
        report = analyze_dead_code(g)
        assert report.unreachable_count == 0

    def test_constructor_is_always_root(self):
        ctor = _sym("__init__", kind=SymbolKind.CONSTRUCTOR, mods="private")
        g = _graph([ctor])
        report = analyze_dead_code(g)
        assert report.unreachable_count == 0

    def test_test_functions_are_roots(self):
        test_fn = _sym("test_something", mods="private")
        g = _graph([test_fn])
        report = analyze_dead_code(g)
        assert report.unreachable_count == 0

    def test_inherits_makes_parent_reachable(self):
        """Child inherits Parent: if Child is root, Parent is reachable."""
        parent = _sym("Base", kind=SymbolKind.CLASS, mods="private")
        child = _sym("Derived", kind=SymbolKind.CLASS)
        edges = [_edge("app.Derived", "app.Base", EdgeType.INHERITS)]
        g = _graph([parent, child], edges)
        report = analyze_dead_code(g)
        assert report.unreachable_count == 0


# =======================================================================
# Unit tests: unreachable classes
# =======================================================================


class TestUnreachableClasses:

    def test_orphan_class_detected(self):
        """Inner class with no references is unreachable."""
        main = _sym("main")
        inner = _sym("OrphanHelper", kind=SymbolKind.CLASS,
                     mods="private", ns="orphan")
        g = _graph([main, inner])
        report = analyze_dead_code(g)
        # Top-level classes with 'public' are roots, but this is private
        dead_names = {c.name for c in report.unreachable_classes}
        assert "OrphanHelper" in dead_names


# =======================================================================
# Unit tests: dead modules
# =======================================================================


class TestDeadModules:

    def test_dead_module(self):
        """Module where no symbol is reachable."""
        main = _sym("main", ns="core")
        dead1 = _sym("unused1", ns="legacy", mods="private")
        dead2 = _sym("unused2", ns="legacy", mods="private")
        g = _graph([main, dead1, dead2])
        report = analyze_dead_code(g)
        dead_mods = {m.module for m in report.unreachable_modules}
        assert "legacy" in dead_mods

    def test_live_module_not_reported(self):
        main = _sym("main", ns="core")
        helper = _sym("helper", ns="core", mods="private")
        edges = [_edge("core.main", "core.helper")]
        g = _graph([main, helper], edges)
        report = analyze_dead_code(g)
        dead_mods = {m.module for m in report.unreachable_modules}
        assert "core" not in dead_mods


# =======================================================================
# Unit tests: dead imports
# =======================================================================


class TestDeadImports:

    def test_dead_import_detected(self):
        """Import of an unreachable symbol is a dead import."""
        main = _sym("main")
        dead = _sym("unused_util", mods="private")
        edges = [
            _edge("app.main", "app.unused_util", EdgeType.IMPORTS),
        ]
        g = _graph([main, dead], edges)
        report = analyze_dead_code(g)
        # unused_util is imported but nothing calls it,
        # and it's private so not a root
        dead_targets = {i.target for i in report.dead_imports}
        assert "app.unused_util" in dead_targets

    def test_live_import_not_reported(self):
        main = _sym("main")
        util = _sym("util", mods="private")
        edges = [
            _edge("app.main", "app.util", EdgeType.IMPORTS),
            _edge("app.main", "app.util", EdgeType.CALLS),
        ]
        g = _graph([main, util], edges)
        report = analyze_dead_code(g)
        dead_targets = {i.target for i in report.dead_imports}
        assert "app.util" not in dead_targets


# =======================================================================
# Health rule tests
# =======================================================================


class TestDeadCodeHealthRules:

    def _run_rule(self, rule_cls, symbols, edges=None):
        g = _graph(symbols, edges)
        return rule_cls().check(g, HealthConfig())

    def test_dc001_unreachable_function(self):
        from app.analysis.health_rules.dead_code import (
            UnreachableFunctionRule,
        )
        findings = self._run_rule(
            UnreachableFunctionRule,
            [_sym("main"), _sym("dead_func", mods="private")],
        )
        assert any(f.rule_id == "DC001" for f in findings)

    def test_dc001_no_fire_reachable(self):
        from app.analysis.health_rules.dead_code import (
            UnreachableFunctionRule,
        )
        findings = self._run_rule(
            UnreachableFunctionRule,
            [_sym("main"), _sym("helper", mods="private")],
            [_edge("app.main", "app.helper")],
        )
        dc001 = [f for f in findings if f.rule_id == "DC001"]
        assert len(dc001) == 0

    def test_dc002_unreachable_class(self):
        from app.analysis.health_rules.dead_code import (
            UnreachableClassRule,
        )
        findings = self._run_rule(
            UnreachableClassRule,
            [
                _sym("main"),
                _sym("Dead", kind=SymbolKind.CLASS,
                     mods="private", ns="dead"),
            ],
        )
        assert any(f.rule_id == "DC002" for f in findings)

    def test_dc003_dead_module(self):
        from app.analysis.health_rules.dead_code import DeadModuleRule
        findings = self._run_rule(
            DeadModuleRule,
            [
                _sym("main", ns="core"),
                _sym("x", ns="legacy", mods="private"),
                _sym("y", ns="legacy", mods="private"),
            ],
        )
        assert any(f.rule_id == "DC003" for f in findings)

    def test_dc004_dead_import(self):
        from app.analysis.health_rules.dead_code import DeadImportRule
        findings = self._run_rule(
            DeadImportRule,
            [_sym("main"), _sym("unused", mods="private")],
            [_edge("app.main", "app.unused", EdgeType.IMPORTS)],
        )
        assert any(f.rule_id == "DC004" for f in findings)


# =======================================================================
# API endpoint tests
# =======================================================================


class TestDeadCodeAPI:

    @pytest_asyncio.fixture(autouse=True)
    async def setup(self):
        await drop_tables()
        await create_tables()
        async for db in override_get_db():
            db.add(Repo(id="r1", name="demo", url="https://example.com"))
            db.add(RepoSnapshot(
                id="s1", repo_id="r1", commit_sha="abc",
                status=SnapshotStatus.completed, file_count=2,
            ))
            # Create a graph: main -> helper, orphan is disconnected
            db.add(Symbol(
                snapshot_id="s1", name="main", kind="method",
                fq_name="app.main", file_path="app/main.py",
                start_line=1, end_line=10, namespace="app",
                modifiers="public",
            ))
            db.add(Symbol(
                snapshot_id="s1", name="helper", kind="method",
                fq_name="app.helper", file_path="app/helper.py",
                start_line=1, end_line=5, namespace="app",
                modifiers="private",
            ))
            db.add(Symbol(
                snapshot_id="s1", name="orphan", kind="method",
                fq_name="dead.orphan", file_path="dead/orphan.py",
                start_line=1, end_line=5, namespace="dead",
                modifiers="private",
            ))
            # main calls helper
            db.add(Edge(
                snapshot_id="s1",
                source_fq_name="app.main",
                target_fq_name="app.helper",
                edge_type="calls",
                file_path="app/main.py", line=5,
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
    async def test_dead_code_endpoint(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/dead-code")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_symbols"] == 3
        assert data["entry_point_count"] >= 1

    @pytest.mark.asyncio
    async def test_orphan_detected(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/dead-code")
        data = resp.json()
        dead_names = {f["name"] for f in data["unreachable_functions"]}
        assert "orphan" in dead_names

    @pytest.mark.asyncio
    async def test_helper_reachable(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/dead-code")
        data = resp.json()
        dead_names = {f["fq_name"] for f in data["unreachable_functions"]}
        assert "app.helper" not in dead_names

    @pytest.mark.asyncio
    async def test_response_fields(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/dead-code")
        data = resp.json()
        assert "total_symbols" in data
        assert "reachable_count" in data
        assert "unreachable_count" in data
        assert "entry_point_count" in data
        assert "unreachable_functions" in data
        assert "unreachable_classes" in data
        assert "unreachable_modules" in data
        assert "dead_imports" in data

    @pytest.mark.asyncio
    async def test_dead_module_detected(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/dead-code")
        data = resp.json()
        dead_mods = {m["module"] for m in data["unreachable_modules"]}
        assert "dead" in dead_mods

    @pytest.mark.asyncio
    async def test_empty_snapshot(self, client):
        async for db in override_get_db():
            db.add(RepoSnapshot(
                id="s2", repo_id="r1", commit_sha="def",
                status=SnapshotStatus.completed, file_count=0,
            ))
            await db.commit()
        resp = await client.get("/repos/r1/snapshots/s2/dead-code")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_symbols"] == 0
        assert data["unreachable_count"] == 0


# =======================================================================
# Edge case tests
# =======================================================================


class TestDeadCodeEdgeCases:

    def test_empty_graph(self):
        g = _graph([])
        report = analyze_dead_code(g)
        assert report.total_symbols == 0
        assert report.reachable_count == 0
        assert report.unreachable_count == 0

    def test_single_symbol(self):
        g = _graph([_sym("main")])
        report = analyze_dead_code(g)
        assert report.reachable_count == 1
        assert report.unreachable_count == 0

    def test_cycle_all_reachable(self):
        """Cycle: a -> b -> c -> a. If a is root, all reachable."""
        syms = [_sym("a"), _sym("b", mods=""), _sym("c", mods="")]
        edges = [
            _edge("app.a", "app.b"),
            _edge("app.b", "app.c"),
            _edge("app.c", "app.a"),
        ]
        g = _graph(syms, edges)
        report = analyze_dead_code(g)
        assert report.unreachable_count == 0

    def test_large_graph_performance(self):
        """Ensure BFS handles 1000+ symbols without issue."""
        syms = [_sym(f"f{i}", mods="private") for i in range(1000)]
        syms.append(_sym("main"))
        edges = [
            _edge("app.main", "app.f0"),
        ]
        for i in range(999):
            edges.append(_edge(f"app.f{i}", f"app.f{i+1}"))
        g = _graph(syms, edges)
        report = analyze_dead_code(g)
        assert report.reachable_count >= 1001
        assert report.unreachable_count == 0

    def test_public_methods_are_roots(self):
        """Public methods should be considered reachable."""
        pub = _sym("api_endpoint", mods="public")
        g = _graph([pub])
        report = analyze_dead_code(g)
        assert report.unreachable_count == 0

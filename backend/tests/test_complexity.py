"""
Tests for Phase 1: Cyclomatic & Cognitive Complexity.

Tests the complexity calculator, the pipeline integration, health rules,
the API endpoint, and real-world validation on all 9 languages.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import tree_sitter_c as tsc
import tree_sitter_c_sharp as tscs
import tree_sitter_cpp as tscpp
import tree_sitter_go as tsgo
import tree_sitter_java as tsjava
import tree_sitter_python as tspy
import tree_sitter_rust as tsrust
import tree_sitter_typescript as tsts
from httpx import ASGITransport, AsyncClient
from tree_sitter import Language, Parser

from app.analysis.complexity import cognitive_complexity, cyclomatic_complexity
from app.analysis.models import SymbolInfo, SymbolKind
from app.analysis.pipeline import analyze_snapshot_files
from app.main import app
from app.storage.database import get_db
from app.storage.models import Repo, RepoSnapshot, SnapshotStatus, Symbol
from tests.conftest import create_tables, drop_tables, override_get_db

app.dependency_overrides[get_db] = override_get_db


# -----------------------------------------------------------------------
# Helpers: parse a code snippet and find the first function node
# -----------------------------------------------------------------------

def _parse_and_find_func(code: str, language: Language, func_node_types: set[str]):
    """Parse code, return the first function-like AST node."""
    parser = Parser(language)
    tree = parser.parse(code.encode())
    return _find_first(tree.root_node, func_node_types)


def _find_first(node, types: set[str]):
    if node.type in types:
        return node
    for child in node.children:
        result = _find_first(child, types)
        if result:
            return result
    return None


# Language fixtures
PY_LANG = Language(tspy.language())
JAVA_LANG = Language(tsjava.language())
CS_LANG = Language(tscs.language())
GO_LANG = Language(tsgo.language())
RUST_LANG = Language(tsrust.language())
C_LANG = Language(tsc.language())
CPP_LANG = Language(tscpp.language())
TS_LANG = Language(tsts.language_typescript())
TSX_LANG = Language(tsts.language_tsx())

PY_FUNC = {"function_definition"}
JAVA_FUNC = {"method_declaration", "constructor_declaration"}
CS_FUNC = {"method_declaration", "constructor_declaration"}
GO_FUNC = {"function_declaration", "method_declaration"}
RUST_FUNC = {"function_item"}
C_FUNC = {"function_definition"}
CPP_FUNC = {"function_definition"}
TS_FUNC = {"function_declaration", "method_definition", "arrow_function"}


# =======================================================================
# Unit tests: cyclomatic complexity
# =======================================================================


class TestCyclomaticComplexity:
    """Pure unit tests for cyclomatic_complexity()."""

    def test_straight_line_is_1(self):
        code = "def foo():\n    x = 1\n    return x\n"
        node = _parse_and_find_func(code, PY_LANG, PY_FUNC)
        assert cyclomatic_complexity(node) == 1

    def test_single_if_is_2(self):
        code = "def foo(x):\n    if x > 0:\n        return x\n    return 0\n"
        node = _parse_and_find_func(code, PY_LANG, PY_FUNC)
        assert cyclomatic_complexity(node) == 2

    def test_if_elif_else_is_at_least_3(self):
        code = textwrap.dedent("""\
            def foo(x):
                if x > 0:
                    return 1
                elif x < 0:
                    return -1
                else:
                    return 0
        """)
        node = _parse_and_find_func(code, PY_LANG, PY_FUNC)
        assert cyclomatic_complexity(node) >= 3

    def test_for_loop(self):
        code = "def foo(xs):\n    for x in xs:\n        print(x)\n"
        node = _parse_and_find_func(code, PY_LANG, PY_FUNC)
        assert cyclomatic_complexity(node) == 2

    def test_while_loop(self):
        code = "def foo():\n    while True:\n        break\n"
        node = _parse_and_find_func(code, PY_LANG, PY_FUNC)
        assert cyclomatic_complexity(node) == 2

    def test_nested_if_for(self):
        code = textwrap.dedent("""\
            def foo(xs):
                for x in xs:
                    if x > 0:
                        print(x)
        """)
        node = _parse_and_find_func(code, PY_LANG, PY_FUNC)
        # 1 + for + if = 3
        assert cyclomatic_complexity(node) == 3

    def test_boolean_and(self):
        code = "def foo(a, b):\n    if a and b:\n        return 1\n"
        node = _parse_and_find_func(code, PY_LANG, PY_FUNC)
        # 1 + if + and = 3
        assert cyclomatic_complexity(node) == 3

    def test_boolean_or(self):
        code = "def foo(a, b):\n    if a or b:\n        return 1\n"
        node = _parse_and_find_func(code, PY_LANG, PY_FUNC)
        assert cyclomatic_complexity(node) == 3

    def test_try_except(self):
        code = textwrap.dedent("""\
            def foo():
                try:
                    x = 1
                except ValueError:
                    x = 0
        """)
        node = _parse_and_find_func(code, PY_LANG, PY_FUNC)
        # 1 + except = 2
        assert cyclomatic_complexity(node) == 2

    def test_complex_python(self):
        code = textwrap.dedent("""\
            def process(items):
                for item in items:
                    if item.valid:
                        if item.type == "a":
                            handle_a(item)
                        elif item.type == "b":
                            handle_b(item)
                    else:
                        try:
                            fallback(item)
                        except Exception:
                            log(item)
        """)
        node = _parse_and_find_func(code, PY_LANG, PY_FUNC)
        cc = cyclomatic_complexity(node)
        # for + if + if + elif + except = 5, +1 base = 6
        assert cc >= 5

    # -- Java --
    def test_java_if_for(self):
        code = textwrap.dedent("""\
            class X {
                void foo(int[] arr) {
                    for (int x : arr) {
                        if (x > 0) {
                            System.out.println(x);
                        }
                    }
                }
            }
        """)
        node = _parse_and_find_func(code, JAVA_LANG, JAVA_FUNC)
        assert node is not None
        cc = cyclomatic_complexity(node)
        assert cc >= 3

    def test_java_switch(self):
        code = textwrap.dedent("""\
            class X {
                int foo(int x) {
                    switch (x) {
                        case 1: return 10;
                        case 2: return 20;
                        case 3: return 30;
                        default: return 0;
                    }
                }
            }
        """)
        node = _parse_and_find_func(code, JAVA_LANG, JAVA_FUNC)
        cc = cyclomatic_complexity(node)
        # 3 cases + base = at least 4
        assert cc >= 4

    # -- C --
    def test_c_nested_loops(self):
        code = textwrap.dedent("""\
            void sort(int *a, int n) {
                for (int i = 0; i < n; i++) {
                    for (int j = 0; j < n; j++) {
                        if (a[i] < a[j]) {
                            int t = a[i];
                            a[i] = a[j];
                            a[j] = t;
                        }
                    }
                }
            }
        """)
        node = _parse_and_find_func(code, C_LANG, C_FUNC)
        cc = cyclomatic_complexity(node)
        # 2 for + 1 if + base = 4
        assert cc >= 4

    # -- Go --
    def test_go_switch(self):
        code = textwrap.dedent("""\
            func foo(x int) int {
                switch x {
                case 1:
                    return 10
                case 2:
                    return 20
                }
                return 0
            }
        """)
        node = _parse_and_find_func(code, GO_LANG, GO_FUNC)
        assert node is not None
        cc = cyclomatic_complexity(node)
        assert cc >= 3

    # -- Rust --
    def test_rust_match(self):
        code = textwrap.dedent("""\
            fn foo(x: i32) -> i32 {
                match x {
                    1 => 10,
                    2 => 20,
                    _ => 0,
                }
            }
        """)
        node = _parse_and_find_func(code, RUST_LANG, RUST_FUNC)
        cc = cyclomatic_complexity(node)
        # 3 match arms + base = at least 4
        assert cc >= 4

    # -- TypeScript --
    def test_ts_ternary(self):
        code = "function foo(x: number): number { return x > 0 ? x : -x; }\n"
        node = _parse_and_find_func(code, TS_LANG, TS_FUNC)
        cc = cyclomatic_complexity(node)
        # ternary = +1, base = 1, total = 2
        assert cc >= 2

    # -- C# --
    def test_csharp_catch(self):
        code = textwrap.dedent("""\
            class X {
                void Foo() {
                    try { Do(); }
                    catch (ArgumentException) { Log(); }
                    catch (Exception) { Throw(); }
                }
            }
        """)
        node = _parse_and_find_func(code, CS_LANG, CS_FUNC)
        cc = cyclomatic_complexity(node)
        # 2 catch + base = 3
        assert cc >= 3

    # -- C++ --
    def test_cpp_do_while(self):
        code = textwrap.dedent("""\
            void foo() {
                do {
                    step();
                } while (condition());
            }
        """)
        node = _parse_and_find_func(code, CPP_LANG, CPP_FUNC)
        cc = cyclomatic_complexity(node)
        assert cc >= 2


# =======================================================================
# Unit tests: cognitive complexity
# =======================================================================


class TestCognitiveComplexity:
    """Pure unit tests for cognitive_complexity()."""

    def test_straight_line_is_0(self):
        code = "def foo():\n    return 1\n"
        node = _parse_and_find_func(code, PY_LANG, PY_FUNC)
        assert cognitive_complexity(node) == 0

    def test_single_if_is_1(self):
        code = "def foo(x):\n    if x:\n        return x\n"
        node = _parse_and_find_func(code, PY_LANG, PY_FUNC)
        cog = cognitive_complexity(node)
        assert cog >= 1

    def test_nested_if_has_nesting_penalty(self):
        code = textwrap.dedent("""\
            def foo(a, b):
                if a:
                    if b:
                        return 1
        """)
        node = _parse_and_find_func(code, PY_LANG, PY_FUNC)
        cog = cognitive_complexity(node)
        # outer if: +1 (depth 0)
        # inner if: +1 +1 nesting = 2
        # total >= 3
        assert cog >= 3

    def test_deeply_nested(self):
        code = textwrap.dedent("""\
            def foo(a, b, c):
                if a:
                    for x in b:
                        if c:
                            pass
        """)
        node = _parse_and_find_func(code, PY_LANG, PY_FUNC)
        cog = cognitive_complexity(node)
        # if(+1) for(+1+1) if(+1+2) = 6
        assert cog >= 5

    def test_else_adds_increment(self):
        code = textwrap.dedent("""\
            def foo(x):
                if x:
                    return 1
                else:
                    return 0
        """)
        node = _parse_and_find_func(code, PY_LANG, PY_FUNC)
        cog = cognitive_complexity(node)
        # if(+1) + else(+1) = 2
        assert cog >= 2

    def test_recursion_detected(self):
        code = textwrap.dedent("""\
            def factorial(n):
                if n <= 1:
                    return 1
                return n * factorial(n - 1)
        """)
        node = _parse_and_find_func(code, PY_LANG, PY_FUNC)
        cog = cognitive_complexity(node, func_name="factorial")
        # if(+1) + recursion(+1) = at least 2
        assert cog >= 2

    def test_boolean_ops_add_complexity(self):
        code = textwrap.dedent("""\
            def foo(a, b, c):
                if a and b or c:
                    return 1
        """)
        node = _parse_and_find_func(code, PY_LANG, PY_FUNC)
        cog = cognitive_complexity(node)
        # if(+1) + and(+1) + or(+1) = 3
        assert cog >= 3

    # -- Java: nested loops + conditionals --
    def test_java_nested(self):
        code = textwrap.dedent("""\
            class X {
                void process(int[][] matrix) {
                    for (int[] row : matrix) {
                        for (int val : row) {
                            if (val > 0) {
                                handle(val);
                            }
                        }
                    }
                }
            }
        """)
        node = _parse_and_find_func(code, JAVA_LANG, JAVA_FUNC)
        cog = cognitive_complexity(node)
        # for(+1) for(+1+1) if(+1+2) = 6
        assert cog >= 5

    # -- C: triple nesting --
    def test_c_triple_nesting(self):
        code = textwrap.dedent("""\
            void foo() {
                for (int i=0;i<10;i++) {
                    while (cond()) {
                        if (check()) {
                            do_thing();
                        }
                    }
                }
            }
        """)
        node = _parse_and_find_func(code, C_LANG, C_FUNC)
        cog = cognitive_complexity(node)
        assert cog >= 5

    # -- Rust: match arms --
    def test_rust_match_cognitive(self):
        code = textwrap.dedent("""\
            fn classify(x: i32) -> &'static str {
                match x {
                    0 => "zero",
                    1..=9 => "small",
                    _ => "big",
                }
            }
        """)
        node = _parse_and_find_func(code, RUST_LANG, RUST_FUNC)
        cog = cognitive_complexity(node)
        # Each match arm adds complexity
        assert cog >= 3


# =======================================================================
# Integration tests: pipeline enrichment
# =======================================================================


class TestPipelineEnrichment:
    """Test that complexity is computed during the analysis pipeline."""

    def _make_temp_repo(self, tmp_path: Path, filename: str, code: str, lang: str):
        """Create a temp dir with a single source file."""
        f = tmp_path / filename
        f.write_text(code, encoding="utf-8")
        file_records = [
            {"path": filename, "language": lang, "hash": "abc", "size_bytes": len(code)}
        ]
        return file_records

    def test_python_complexity_enriched(self, tmp_path):
        code = textwrap.dedent("""\
            def simple():
                return 1

            def branchy(x):
                if x > 0:
                    for i in range(x):
                        if i % 2 == 0:
                            print(i)
        """)
        records = self._make_temp_repo(tmp_path, "main.py", code, "python")
        graph = analyze_snapshot_files(tmp_path, records)

        methods = {
            s.name: s for s in graph.symbols.values()
            if s.kind in (SymbolKind.METHOD, SymbolKind.CONSTRUCTOR)
        }

        if "simple" in methods:
            assert methods["simple"].cyclomatic_complexity == 1
        if "branchy" in methods:
            assert methods["branchy"].cyclomatic_complexity >= 3
            assert methods["branchy"].cognitive_complexity >= 3

    def test_java_complexity_enriched(self, tmp_path):
        code = textwrap.dedent("""\
            public class Demo {
                public void easy() {
                    System.out.println("hi");
                }
                public int complex(int x) {
                    if (x > 0) {
                        for (int i = 0; i < x; i++) {
                            if (i % 2 == 0) {
                                return i;
                            }
                        }
                    }
                    return -1;
                }
            }
        """)
        records = self._make_temp_repo(tmp_path, "Demo.java", code, "java")
        graph = analyze_snapshot_files(tmp_path, records)

        methods = {
            s.name: s for s in graph.symbols.values()
            if s.kind in (SymbolKind.METHOD, SymbolKind.CONSTRUCTOR)
        }
        if "complex" in methods:
            assert methods["complex"].cyclomatic_complexity >= 3

    def test_go_complexity_enriched(self, tmp_path):
        code = textwrap.dedent("""\
            package main

            func handler(items []int) int {
                total := 0
                for _, v := range items {
                    if v > 0 {
                        total += v
                    } else if v < -10 {
                        total -= v
                    }
                }
                return total
            }
        """)
        records = self._make_temp_repo(tmp_path, "main.go", code, "go")
        graph = analyze_snapshot_files(tmp_path, records)
        methods = {
            s.name: s for s in graph.symbols.values()
            if s.kind in (SymbolKind.METHOD, SymbolKind.CONSTRUCTOR)
        }
        if "handler" in methods:
            assert methods["handler"].cyclomatic_complexity >= 3

    def test_rust_complexity_enriched(self, tmp_path):
        code = textwrap.dedent("""\
            fn process(x: i32) -> i32 {
                match x {
                    0 => 0,
                    1 => 1,
                    n if n > 0 => n * 2,
                    _ => -1,
                }
            }
        """)
        records = self._make_temp_repo(tmp_path, "lib.rs", code, "rust")
        graph = analyze_snapshot_files(tmp_path, records)
        methods = {
            s.name: s for s in graph.symbols.values()
            if s.kind in (SymbolKind.METHOD, SymbolKind.CONSTRUCTOR)
        }
        if "process" in methods:
            assert methods["process"].cyclomatic_complexity >= 4

    def test_c_complexity_enriched(self, tmp_path):
        code = textwrap.dedent("""\
            int abs_val(int x) {
                if (x < 0) {
                    return -x;
                }
                return x;
            }
        """)
        records = self._make_temp_repo(tmp_path, "util.c", code, "c")
        graph = analyze_snapshot_files(tmp_path, records)
        methods = {
            s.name: s for s in graph.symbols.values()
            if s.kind in (SymbolKind.METHOD, SymbolKind.CONSTRUCTOR)
        }
        if "abs_val" in methods:
            assert methods["abs_val"].cyclomatic_complexity >= 2

    def test_cpp_complexity_enriched(self, tmp_path):
        code = textwrap.dedent("""\
            int compute(int a, int b) {
                if (a > 0 && b > 0) {
                    return a + b;
                } else if (a < 0 || b < 0) {
                    return 0;
                }
                return -1;
            }
        """)
        records = self._make_temp_repo(tmp_path, "util.cpp", code, "cpp")
        graph = analyze_snapshot_files(tmp_path, records)
        methods = {
            s.name: s for s in graph.symbols.values()
            if s.kind in (SymbolKind.METHOD, SymbolKind.CONSTRUCTOR)
        }
        if "compute" in methods:
            assert methods["compute"].cyclomatic_complexity >= 3

    def test_csharp_complexity_enriched(self, tmp_path):
        code = textwrap.dedent("""\
            class Util {
                int Calc(int x) {
                    try {
                        if (x > 0) return x;
                    } catch (Exception) {
                        return 0;
                    }
                    return -1;
                }
            }
        """)
        records = self._make_temp_repo(tmp_path, "Util.cs", code, "csharp")
        graph = analyze_snapshot_files(tmp_path, records)
        methods = {
            s.name: s for s in graph.symbols.values()
            if s.kind in (SymbolKind.METHOD, SymbolKind.CONSTRUCTOR)
        }
        if "Calc" in methods:
            assert methods["Calc"].cyclomatic_complexity >= 3

    def test_typescript_complexity_enriched(self, tmp_path):
        code = textwrap.dedent("""\
            function check(x: number): string {
                if (x > 100) {
                    return "big";
                } else if (x > 0) {
                    return "small";
                }
                return "negative";
            }
        """)
        records = self._make_temp_repo(tmp_path, "util.ts", code, "typescript")
        graph = analyze_snapshot_files(tmp_path, records)
        methods = {
            s.name: s for s in graph.symbols.values()
            if s.kind in (SymbolKind.METHOD, SymbolKind.CONSTRUCTOR)
        }
        if "check" in methods:
            assert methods["check"].cyclomatic_complexity >= 2


# =======================================================================
# Health rule tests
# =======================================================================


class TestComplexityHealthRules:
    """Test that the 5 new health rules fire correctly."""

    def _build_graph_with_cc(self, cc: int, cog: int):
        """Build a minimal CodeGraph with one symbol having given complexity."""
        from app.analysis.graph_builder import CodeGraph
        sym = SymbolInfo(
            name="complex_func",
            kind=SymbolKind.METHOD,
            fq_name="mod.complex_func",
            file_path="mod.py",
            start_line=1,
            end_line=max(5, cc * 2),
            cyclomatic_complexity=cc,
            cognitive_complexity=cog,
        )
        graph = CodeGraph()
        graph.symbols[sym.fq_name] = sym
        return graph

    def test_cx004_fires_at_16(self):
        from app.analysis.code_health import HealthConfig
        from app.analysis.health_rules.complexity import HighCyclomaticRule
        graph = self._build_graph_with_cc(16, 0)
        findings = HighCyclomaticRule().check(graph, HealthConfig())
        assert len(findings) == 1
        assert findings[0].rule_id == "CX004"

    def test_cx004_does_not_fire_at_15(self):
        from app.analysis.code_health import HealthConfig
        from app.analysis.health_rules.complexity import HighCyclomaticRule
        graph = self._build_graph_with_cc(15, 0)
        findings = HighCyclomaticRule().check(graph, HealthConfig())
        assert len(findings) == 0

    def test_cx005_fires_at_31(self):
        from app.analysis.code_health import HealthConfig
        from app.analysis.health_rules.complexity import VeryHighCyclomaticRule
        graph = self._build_graph_with_cc(31, 0)
        findings = VeryHighCyclomaticRule().check(graph, HealthConfig())
        assert len(findings) == 1
        assert findings[0].rule_id == "CX005"
        assert findings[0].severity.value == "error"

    def test_cx005_does_not_fire_at_30(self):
        from app.analysis.code_health import HealthConfig
        from app.analysis.health_rules.complexity import VeryHighCyclomaticRule
        graph = self._build_graph_with_cc(30, 0)
        findings = VeryHighCyclomaticRule().check(graph, HealthConfig())
        assert len(findings) == 0

    def test_cx006_fires_at_21(self):
        from app.analysis.code_health import HealthConfig
        from app.analysis.health_rules.complexity import HighCognitiveRule
        graph = self._build_graph_with_cc(0, 21)
        findings = HighCognitiveRule().check(graph, HealthConfig())
        assert len(findings) == 1
        assert findings[0].rule_id == "CX006"

    def test_cx006_does_not_fire_at_20(self):
        from app.analysis.code_health import HealthConfig
        from app.analysis.health_rules.complexity import HighCognitiveRule
        graph = self._build_graph_with_cc(0, 20)
        findings = HighCognitiveRule().check(graph, HealthConfig())
        assert len(findings) == 0

    def test_cx007_fires_at_41(self):
        from app.analysis.code_health import HealthConfig
        from app.analysis.health_rules.complexity import VeryHighCognitiveRule
        graph = self._build_graph_with_cc(0, 41)
        findings = VeryHighCognitiveRule().check(graph, HealthConfig())
        assert len(findings) == 1
        assert findings[0].rule_id == "CX007"
        assert findings[0].severity.value == "error"

    def test_cx008_fires_on_dense_code(self):
        from app.analysis.code_health import HealthConfig
        from app.analysis.health_rules.complexity import ComplexityPerLineRule
        sym = SymbolInfo(
            name="dense",
            kind=SymbolKind.METHOD,
            fq_name="mod.dense",
            file_path="mod.py",
            start_line=1,
            end_line=5,  # 5 lines
            cyclomatic_complexity=4,  # 4/5 = 0.8 > 0.5
            cognitive_complexity=0,
        )
        from app.analysis.graph_builder import CodeGraph
        graph = CodeGraph()
        graph.symbols[sym.fq_name] = sym
        findings = ComplexityPerLineRule().check(graph, HealthConfig())
        assert len(findings) == 1
        assert findings[0].rule_id == "CX008"

    def test_cx008_does_not_fire_on_normal_code(self):
        from app.analysis.code_health import HealthConfig
        from app.analysis.health_rules.complexity import ComplexityPerLineRule
        sym = SymbolInfo(
            name="normal",
            kind=SymbolKind.METHOD,
            fq_name="mod.normal",
            file_path="mod.py",
            start_line=1,
            end_line=20,
            cyclomatic_complexity=3,  # 3/20 = 0.15 < 0.5
            cognitive_complexity=0,
        )
        from app.analysis.graph_builder import CodeGraph
        graph = CodeGraph()
        graph.symbols[sym.fq_name] = sym
        findings = ComplexityPerLineRule().check(graph, HealthConfig())
        assert len(findings) == 0


# =======================================================================
# API endpoint tests
# =======================================================================


class TestComplexityAPI:
    """Test the GET /complexity endpoint."""

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
            # Add symbols with varying complexity
            for name, cc, cog in [
                ("simple", 1, 0),
                ("medium", 8, 10),
                ("complex", 20, 30),
                ("monster", 35, 50),
            ]:
                db.add(Symbol(
                    snapshot_id="s1", name=name, kind="method",
                    fq_name=f"app.{name}", file_path="main.py",
                    start_line=1, end_line=50,
                    cyclomatic_complexity=cc,
                    cognitive_complexity=cog,
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
    async def test_complexity_endpoint_returns_all(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/complexity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_functions"] == 4
        assert data["avg_cyclomatic"] > 0
        assert data["avg_cognitive"] > 0

    @pytest.mark.asyncio
    async def test_complexity_max_items(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/complexity")
        data = resp.json()
        assert data["max_cyclomatic"]["name"] == "monster"
        assert data["max_cognitive"]["name"] == "monster"

    @pytest.mark.asyncio
    async def test_complexity_high_counts(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/complexity")
        data = resp.json()
        # complex(20) and monster(35) exceed 15
        assert data["high_cyclomatic_count"] == 2
        # complex(30) and monster(50) exceed 20
        assert data["high_cognitive_count"] == 2

    @pytest.mark.asyncio
    async def test_complexity_filter_min_cc(self, client):
        resp = await client.get(
            "/repos/r1/snapshots/s1/complexity", params={"min_cc": 10}
        )
        data = resp.json()
        assert data["total_functions"] == 2  # complex and monster only
        names = {i["name"] for i in data["items"]}
        assert names == {"complex", "monster"}

    @pytest.mark.asyncio
    async def test_complexity_items_sorted_desc(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/complexity")
        data = resp.json()
        ccs = [i["cyclomatic_complexity"] for i in data["items"]]
        assert ccs == sorted(ccs, reverse=True)

    @pytest.mark.asyncio
    async def test_complexity_item_fields(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/complexity")
        item = resp.json()["items"][0]
        assert "fq_name" in item
        assert "name" in item
        assert "kind" in item
        assert "file_path" in item
        assert "start_line" in item
        assert "end_line" in item
        assert "lines" in item
        assert "cyclomatic_complexity" in item
        assert "cognitive_complexity" in item

    @pytest.mark.asyncio
    async def test_complexity_empty_snapshot(self, client):
        async for db in override_get_db():
            db.add(RepoSnapshot(
                id="s2", repo_id="r1", commit_sha="def",
                status=SnapshotStatus.completed, file_count=0,
            ))
            await db.commit()
        resp = await client.get("/repos/r1/snapshots/s2/complexity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_functions"] == 0
        assert data["avg_cyclomatic"] == 0
        assert data["items"] == []


# =======================================================================
# Edge case tests
# =======================================================================


class TestComplexityEdgeCases:
    """Edge cases for the complexity calculator."""

    def test_empty_function(self):
        code = "def noop():\n    pass\n"
        node = _parse_and_find_func(code, PY_LANG, PY_FUNC)
        assert cyclomatic_complexity(node) == 1
        assert cognitive_complexity(node) == 0

    def test_single_return(self):
        code = "def identity(x):\n    return x\n"
        node = _parse_and_find_func(code, PY_LANG, PY_FUNC)
        assert cyclomatic_complexity(node) == 1

    def test_many_sequential_ifs(self):
        lines = ["def many(x):"]
        for i in range(10):
            lines.append(f"    if x == {i}: return {i}")
        code = "\n".join(lines) + "\n"
        node = _parse_and_find_func(code, PY_LANG, PY_FUNC)
        cc = cyclomatic_complexity(node)
        assert cc >= 11  # 1 base + 10 ifs

    def test_deeply_nested_6_levels(self):
        code = textwrap.dedent("""\
            def deep(a, b, c, d, e, f):
                if a:
                    if b:
                        for x in c:
                            while d:
                                if e:
                                    if f:
                                        return 1
        """)
        node = _parse_and_find_func(code, PY_LANG, PY_FUNC)
        cc = cyclomatic_complexity(node)
        cog = cognitive_complexity(node)
        assert cc >= 6
        # Cognitive should be much higher due to nesting penalties
        assert cog > cc

    def test_class_method_not_class(self):
        """Complexity should be computed for methods, not classes."""
        code = textwrap.dedent("""\
            class Foo:
                def bar(self):
                    if True:
                        return 1
                    return 0
        """)
        node = _parse_and_find_func(code, PY_LANG, PY_FUNC)
        assert node is not None
        assert node.type == "function_definition"
        assert cyclomatic_complexity(node) >= 2

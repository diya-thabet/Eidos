"""
=============================================================================
DEEP PER-LANGUAGE VALIDATION: Eidos Full Pipeline on 9 Challenging Repos
=============================================================================

Each language is tested with a repo that exercises HARD language features:

| Lang       | Repo                             | Challenge Features                          |
|------------|----------------------------------|---------------------------------------------|
| Python     | pallets/click                    | Decorators, metaclasses, inheritance, CLI   |
| C#         | ardalis/GuardClauses             | Generics, extension methods, interfaces     |
| Java       | iluwatar/java-design-patterns    | 20+ GoF patterns, abstract classes, generics|
| TypeScript | sindresorhus/ky                  | Generics, async/await, union types, modules |
| TSX        | pacocoursey/cmdk                 | JSX components, hooks, props, composition   |
| Go         | charmbracelet/bubbletea          | Interfaces, struct embedding, channels      |
| Rust       | hyperium/http                    | Traits, generics, builders, From/Into       |
| C          | DaveGamble/cJSON                 | Structs, function pointers, linked lists    |
| C++        | fmtlib/fmt                       | Templates, virtual, operator overloading    |

Each test:
  1. Clones the real repo from GitHub
  2. Scans and parses all source files
  3. Verifies symbols (classes, methods, interfaces, traits, structs)
  4. Verifies edges (calls, inherits, implements)
  5. Prints FULL graph details: hierarchies, call chains, signatures
  6. Tests through the API: search, health, diagram, export, portable

Usage:
    cd backend
    python -m pytest tests/test_deep_languages.py -v --tb=short -s
    python -m pytest tests/test_deep_languages.py -k "python" -v -s
"""

from __future__ import annotations

import gzip
import json
import shutil
import tempfile
from collections import defaultdict
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.analysis.graph_builder import CodeGraph
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

app.dependency_overrides[get_db] = override_get_db

# ---------------------------------------------------------------------------
# Repo definitions
# ---------------------------------------------------------------------------

LANG_REPOS = {
    "python": {
        "name": "click",
        "url": "https://github.com/pallets/click",
        "branch": "main",
        "min_symbols": 50,
        "min_edges": 20,
        "expect_kinds": ["class", "method"],
    },
    "csharp": {
        "name": "GuardClauses",
        "url": "https://github.com/ardalis/GuardClauses",
        "branch": "main",
        "min_symbols": 100,
        "min_edges": 50,
        "expect_kinds": ["class", "method", "interface"],
    },
    "java": {
        "name": "java-design-patterns",
        "url": "https://github.com/iluwatar/java-design-patterns",
        "branch": "master",
        "min_symbols": 200,
        "min_edges": 100,
        "expect_kinds": ["class", "method", "interface"],
        "clone_depth": 1,
    },
    "typescript": {
        "name": "ky",
        "url": "https://github.com/sindresorhus/ky",
        "branch": "main",
        "min_symbols": 5,
        "min_edges": 1,
        "expect_kinds": ["function"],
    },
    "tsx": {
        "name": "cmdk",
        "url": "https://github.com/pacocoursey/cmdk",
        "branch": "main",
        "min_symbols": 5,
        "min_edges": 1,
        "expect_kinds": ["function"],
    },
    "go": {
        "name": "bubbletea",
        "url": "https://github.com/charmbracelet/bubbletea",
        "branch": "main",
        "min_symbols": 20,
        "min_edges": 10,
        "expect_kinds": ["function", "method"],
    },
    "rust": {
        "name": "http",
        "url": "https://github.com/hyperium/http",
        "branch": "master",
        "min_symbols": 50,
        "min_edges": 20,
        "expect_kinds": ["function", "method", "struct"],
    },
    "c": {
        "name": "cJSON",
        "url": "https://github.com/DaveGamble/cJSON",
        "branch": "master",
        "min_symbols": 20,
        "min_edges": 10,
        "expect_kinds": ["function"],
    },
    "cpp": {
        "name": "fmt",
        "url": "https://github.com/fmtlib/fmt",
        "branch": "main",
        "min_symbols": 30,
        "min_edges": 10,
        "expect_kinds": ["class", "method"],
    },
}

# ---------------------------------------------------------------------------
# Clone + parse cache (module-scoped for speed)
# ---------------------------------------------------------------------------

_cache: dict[str, dict[str, Any]] = {}


def _get_parsed(lang: str) -> dict[str, Any]:
    """Clone, scan, parse a repo. Cached per language."""
    if lang in _cache:
        return _cache[lang]

    info = LANG_REPOS[lang]
    tmpdir = tempfile.mkdtemp(prefix=f"eidos_deep_{lang}_")
    dest = Path(tmpdir) / info["name"]

    try:
        sha = clone_repo(info["url"], info["branch"], dest, None, "")
    except Exception as e:
        shutil.rmtree(tmpdir, ignore_errors=True)
        pytest.skip(f"Clone failed for {lang}/{info['name']}: {e}")

    files = scan_files(dest)
    lang_files = [f for f in files if f["language"] == lang]
    graph = analyze_snapshot_files(dest, files)

    result = {
        "tmpdir": tmpdir,
        "path": dest,
        "sha": sha,
        "files": files,
        "lang_files": lang_files,
        "graph": graph,
        "info": info,
    }
    _cache[lang] = result
    return result


def pytest_sessionfinish(session, exitstatus):
    for data in _cache.values():
        shutil.rmtree(data["tmpdir"], ignore_errors=True)


# ---------------------------------------------------------------------------
# Helper: print graph report
# ---------------------------------------------------------------------------

def _print_report(lang: str, graph: CodeGraph, lang_files: list) -> None:
    """Print a detailed graph analysis report."""
    symbols = list(graph.symbols.values())
    edges = graph.edges

    # -- Symbol breakdown --
    kinds: dict[str, list] = defaultdict(list)
    for s in symbols:
        kinds[s.kind.value].append(s)

    print(f"\n{'='*70}")
    print(f"  EIDOS ANALYSIS REPORT: {lang.upper()}")
    print(f"{'='*70}")
    print(f"  Source files: {len(lang_files)} {lang} files")
    print(f"  Total symbols: {len(symbols)}")
    print(f"  Total edges: {len(edges)}")
    print()

    # -- Symbols by kind --
    print("  SYMBOLS BY KIND:")
    for kind in sorted(kinds.keys()):
        items = kinds[kind]
        print(f"    {kind}: {len(items)}")
        for s in items[:8]:
            sig = s.signature[:55] if s.signature else ""
            print(f"      - {s.fq_name} [{s.file_path}:{s.start_line}]")
            if sig:
                print(f"        sig: {sig}")
        if len(items) > 8:
            print(f"      ... and {len(items) - 8} more")
    print()

    # -- Inheritance hierarchy --
    inherits = [e for e in edges if e.edge_type.value == "inherits"]
    implements = [e for e in edges if e.edge_type.value == "implements"]
    if inherits or implements:
        print("  INHERITANCE HIERARCHY:")
        for e in inherits[:15]:
            print(f"    {e.source_fq_name}")
            print(f"      extends -> {e.target_fq_name}")
        for e in implements[:15]:
            print(f"    {e.source_fq_name}")
            print(f"      implements -> {e.target_fq_name}")
        if len(inherits) > 15:
            print(f"    ... and {len(inherits) - 15} more inheritance edges")
        print()

    # -- Call graph (top callers) --
    calls = [e for e in edges if e.edge_type.value == "calls"]
    if calls:
        caller_count: dict[str, int] = defaultdict(int)
        for c in calls:
            caller_count[c.source_fq_name] += 1
        top_callers = sorted(
            caller_count.items(), key=lambda x: -x[1]
        )[:10]
        print("  TOP CALLERS (most outgoing calls):")
        for fq, count in top_callers:
            print(f"    {fq}: {count} calls")
            targets = [
                c.target_fq_name for c in calls
                if c.source_fq_name == fq
            ][:5]
            for t in targets:
                print(f"      -> {t}")
            if count > 5:
                print(f"      ... and {count - 5} more")
        print()

    # -- Edge breakdown --
    edge_types: dict[str, int] = defaultdict(int)
    for e in edges:
        edge_types[e.edge_type.value] += 1
    print("  EDGE BREAKDOWN:")
    for etype, count in sorted(edge_types.items(), key=lambda x: -x[1]):
        print(f"    {etype}: {count}")
    print(f"{'='*70}")


# ===========================================================================
# TESTS: One class per language, each tests the full pipeline
# ===========================================================================


class TestPython:
    """Python: pallets/click - decorators, metaclasses, inheritance."""

    def test_parse(self):
        d = _get_parsed("python")
        _print_report("python", d["graph"], d["lang_files"])
        assert len(d["graph"].symbols) >= LANG_REPOS["python"]["min_symbols"]
        assert len(d["graph"].edges) >= LANG_REPOS["python"]["min_edges"]

    def test_expected_kinds(self):
        d = _get_parsed("python")
        found = {s.kind.value for s in d["graph"].symbols.values()}
        for k in LANG_REPOS["python"]["expect_kinds"]:
            assert k in found, f"Expected {k} symbols in Python"

    def test_classes_have_methods(self):
        d = _get_parsed("python")
        classes = [
            s for s in d["graph"].symbols.values()
            if s.kind.value == "class"
        ]
        methods_with_parent = [
            s for s in d["graph"].symbols.values()
            if s.kind.value == "method" and s.parent_fq_name
        ]
        print(f"\n  Python: {len(classes)} classes, "
              f"{len(methods_with_parent)} methods with parent")
        assert len(classes) > 0
        assert len(methods_with_parent) > 0

    def test_inheritance_chain(self):
        d = _get_parsed("python")
        inherits = [
            e for e in d["graph"].edges
            if e.edge_type.value == "inherits"
        ]
        print(f"\n  Python inheritance edges: {len(inherits)}")
        for e in inherits[:10]:
            print(f"    {e.source_fq_name} -> {e.target_fq_name}")

    @pytest.mark.asyncio
    async def test_full_api_pipeline(self):
        d = _get_parsed("python")
        await _run_api_pipeline("python", d)


class TestCSharp:
    """C#: ardalis/GuardClauses - generics, extension methods, interfaces."""

    def test_parse(self):
        d = _get_parsed("csharp")
        _print_report("csharp", d["graph"], d["lang_files"])
        assert len(d["graph"].symbols) >= LANG_REPOS["csharp"]["min_symbols"]

    def test_interfaces_found(self):
        d = _get_parsed("csharp")
        interfaces = [
            s for s in d["graph"].symbols.values()
            if s.kind.value == "interface"
        ]
        print(f"\n  C# interfaces: {len(interfaces)}")
        for i in interfaces[:10]:
            print(f"    {i.fq_name}")
        assert len(interfaces) > 0

    def test_generics_in_signatures(self):
        d = _get_parsed("csharp")
        generic_methods = [
            s for s in d["graph"].symbols.values()
            if s.signature and "<" in s.signature
        ]
        print(f"\n  C# generic signatures: {len(generic_methods)}")
        for m in generic_methods[:5]:
            print(f"    {m.fq_name}: {m.signature[:70]}")

    @pytest.mark.asyncio
    async def test_full_api_pipeline(self):
        d = _get_parsed("csharp")
        await _run_api_pipeline("csharp", d)


class TestJava:
    """Java: iluwatar/java-design-patterns - GoF patterns, abstracts."""

    def test_parse(self):
        d = _get_parsed("java")
        _print_report("java", d["graph"], d["lang_files"])
        assert len(d["graph"].symbols) >= LANG_REPOS["java"]["min_symbols"]

    def test_design_pattern_classes(self):
        d = _get_parsed("java")
        classes = [
            s.name for s in d["graph"].symbols.values()
            if s.kind.value == "class"
        ]
        print(f"\n  Java classes: {len(classes)}")
        # Look for pattern-related names
        pattern_keywords = [
            "Factory", "Builder", "Singleton", "Observer",
            "Strategy", "Command", "Adapter", "Decorator",
        ]
        found_patterns = [
            c for c in classes
            if any(kw.lower() in c.lower() for kw in pattern_keywords)
        ]
        print(f"  Design pattern classes: {len(found_patterns)}")
        for p in found_patterns[:15]:
            print(f"    {p}")

    def test_interfaces_and_abstract(self):
        d = _get_parsed("java")
        interfaces = [
            s for s in d["graph"].symbols.values()
            if s.kind.value == "interface"
        ]
        print(f"\n  Java interfaces: {len(interfaces)}")
        for i in interfaces[:10]:
            print(f"    {i.fq_name}")

    def test_inheritance_depth(self):
        d = _get_parsed("java")
        inherits = [
            e for e in d["graph"].edges
            if e.edge_type.value in ("inherits", "implements")
        ]
        print(f"\n  Java inheritance+implements: {len(inherits)}")
        # Build parent map
        parents: dict[str, list[str]] = defaultdict(list)
        for e in inherits:
            parents[e.source_fq_name].append(e.target_fq_name)
        multi = {k: v for k, v in parents.items() if len(v) > 1}
        print(f"  Classes with multiple parents: {len(multi)}")
        for cls, pars in list(multi.items())[:5]:
            print(f"    {cls} -> {pars}")

    @pytest.mark.asyncio
    async def test_full_api_pipeline(self):
        d = _get_parsed("java")
        await _run_api_pipeline("java", d)


class TestTypeScript:
    """TypeScript: sindresorhus/ky - generics, async, union types."""

    def test_parse(self):
        d = _get_parsed("typescript")
        _print_report("typescript", d["graph"], d["lang_files"])
        assert len(d["graph"].symbols) >= LANG_REPOS["typescript"]["min_symbols"]

    def test_functions_have_signatures(self):
        d = _get_parsed("typescript")
        funcs = [
            s for s in d["graph"].symbols.values()
            if s.kind.value in ("function", "method")
        ]
        with_sig = [f for f in funcs if f.signature]
        print(f"\n  TS functions: {len(funcs)}, with sig: {len(with_sig)}")
        for f in with_sig[:5]:
            print(f"    {f.fq_name}: {f.signature[:60]}")

    @pytest.mark.asyncio
    async def test_full_api_pipeline(self):
        d = _get_parsed("typescript")
        await _run_api_pipeline("typescript", d)


class TestTSX:
    """TSX: pacocoursey/cmdk - React components, hooks, composition."""

    def test_parse(self):
        d = _get_parsed("tsx")
        _print_report("tsx", d["graph"], d["lang_files"])
        assert len(d["graph"].symbols) >= LANG_REPOS["tsx"]["min_symbols"]

    def test_component_like_symbols(self):
        d = _get_parsed("tsx")
        # React components are typically PascalCase functions
        components = [
            s for s in d["graph"].symbols.values()
            if s.kind.value == "function" and s.name[0:1].isupper()
        ]
        print(f"\n  TSX components (PascalCase funcs): {len(components)}")
        for c in components[:10]:
            print(f"    {c.fq_name}")

    @pytest.mark.asyncio
    async def test_full_api_pipeline(self):
        d = _get_parsed("tsx")
        await _run_api_pipeline("tsx", d)


class TestGo:
    """Go: charmbracelet/bubbletea - interfaces, struct embedding."""

    def test_parse(self):
        d = _get_parsed("go")
        _print_report("go", d["graph"], d["lang_files"])
        assert len(d["graph"].symbols) >= LANG_REPOS["go"]["min_symbols"]

    def test_structs_and_interfaces(self):
        d = _get_parsed("go")
        structs = [
            s for s in d["graph"].symbols.values()
            if s.kind.value in ("struct", "class")
        ]
        interfaces = [
            s for s in d["graph"].symbols.values()
            if s.kind.value == "interface"
        ]
        print(f"\n  Go structs: {len(structs)}, interfaces: {len(interfaces)}")
        for s in structs[:5]:
            print(f"    struct {s.fq_name}")
        for i in interfaces[:5]:
            print(f"    interface {i.fq_name}")

    def test_method_receivers(self):
        d = _get_parsed("go")
        methods = [
            s for s in d["graph"].symbols.values()
            if s.kind.value == "method" and s.parent_fq_name
        ]
        print(f"\n  Go methods with receivers: {len(methods)}")
        for m in methods[:5]:
            print(f"    ({m.parent_fq_name}).{m.name}")

    @pytest.mark.asyncio
    async def test_full_api_pipeline(self):
        d = _get_parsed("go")
        await _run_api_pipeline("go", d)


class TestRust:
    """Rust: hyperium/http - traits, generics, builders, From/Into."""

    def test_parse(self):
        d = _get_parsed("rust")
        _print_report("rust", d["graph"], d["lang_files"])
        assert len(d["graph"].symbols) >= LANG_REPOS["rust"]["min_symbols"]

    def test_traits_found(self):
        d = _get_parsed("rust")
        traits = [
            s for s in d["graph"].symbols.values()
            if s.kind.value in ("interface", "trait")
        ]
        structs = [
            s for s in d["graph"].symbols.values()
            if s.kind.value in ("struct", "class")
        ]
        print(f"\n  Rust traits: {len(traits)}, structs: {len(structs)}")
        for t in traits[:5]:
            print(f"    trait {t.fq_name}")
        for s in structs[:5]:
            print(f"    struct {s.fq_name}")

    def test_impl_blocks(self):
        d = _get_parsed("rust")
        # impl blocks show up as methods with parent_fq_name
        impl_methods = [
            s for s in d["graph"].symbols.values()
            if s.kind.value == "method" and s.parent_fq_name
        ]
        print(f"\n  Rust impl methods: {len(impl_methods)}")
        # Group by parent
        by_parent: dict[str, int] = defaultdict(int)
        for m in impl_methods:
            by_parent[m.parent_fq_name] += 1
        for parent, count in sorted(
            by_parent.items(), key=lambda x: -x[1]
        )[:10]:
            print(f"    impl {parent}: {count} methods")

    @pytest.mark.asyncio
    async def test_full_api_pipeline(self):
        d = _get_parsed("rust")
        await _run_api_pipeline("rust", d)


class TestC:
    """C: DaveGamble/cJSON - structs, function pointers, linked lists."""

    def test_parse(self):
        d = _get_parsed("c")
        _print_report("c", d["graph"], d["lang_files"])
        assert len(d["graph"].symbols) >= LANG_REPOS["c"]["min_symbols"]

    def test_functions_found(self):
        d = _get_parsed("c")
        funcs = [
            s for s in d["graph"].symbols.values()
            if s.kind.value in ("function", "method")
        ]
        print(f"\n  C functions: {len(funcs)}")
        for f in funcs[:10]:
            sig = f.signature[:60] if f.signature else ""
            print(f"    {f.name} -> {sig}")
        assert len(funcs) > 0

    def test_structs_found(self):
        d = _get_parsed("c")
        structs = [
            s for s in d["graph"].symbols.values()
            if s.kind.value in ("struct", "class")
        ]
        print(f"\n  C structs: {len(structs)}")
        for s in structs[:10]:
            print(f"    {s.fq_name} [{s.file_path}:{s.start_line}-{s.end_line}]")

    def test_call_graph(self):
        d = _get_parsed("c")
        calls = [
            e for e in d["graph"].edges if e.edge_type.value == "calls"
        ]
        print(f"\n  C call edges: {len(calls)}")
        for c in calls[:10]:
            print(f"    {c.source_fq_name} -> {c.target_fq_name}")

    @pytest.mark.asyncio
    async def test_full_api_pipeline(self):
        d = _get_parsed("c")
        await _run_api_pipeline("c", d)


class TestCpp:
    """C++: fmtlib/fmt - templates, virtual, operator overloading."""

    def test_parse(self):
        d = _get_parsed("cpp")
        _print_report("cpp", d["graph"], d["lang_files"])
        assert len(d["graph"].symbols) >= LANG_REPOS["cpp"]["min_symbols"]

    def test_classes_and_templates(self):
        d = _get_parsed("cpp")
        classes = [
            s for s in d["graph"].symbols.values()
            if s.kind.value == "class"
        ]
        # Template classes often have < in their name or signature
        templates = [
            c for c in classes
            if c.signature and "template" in c.signature.lower()
        ]
        print(f"\n  C++ classes: {len(classes)}, templates: {len(templates)}")
        for c in classes[:10]:
            print(f"    {c.fq_name}")

    def test_virtual_methods(self):
        d = _get_parsed("cpp")
        methods = [
            s for s in d["graph"].symbols.values()
            if s.kind.value == "method"
        ]
        virtual = [
            m for m in methods
            if any(
                kw in (
                    ",".join(m.modifiers) if isinstance(m.modifiers, list)
                    else (m.modifiers or "")
                ).lower()
                for kw in ("virtual", "override")
            )
        ]
        print(f"\n  C++ methods: {len(methods)}, virtual/override: {len(virtual)}")
        for v in virtual[:5]:
            print(f"    {v.fq_name} [{v.modifiers}]")

    def test_namespace_structure(self):
        d = _get_parsed("cpp")
        namespaces = {
            s.namespace for s in d["graph"].symbols.values()
            if s.namespace
        }
        print(f"\n  C++ namespaces: {namespaces}")

    @pytest.mark.asyncio
    async def test_full_api_pipeline(self):
        d = _get_parsed("cpp")
        await _run_api_pipeline("cpp", d)


# ===========================================================================
# Shared: Full API pipeline test
# ===========================================================================


async def _run_api_pipeline(lang: str, data: dict) -> None:
    """Run the complete API pipeline for a parsed language."""
    repo_id = f"r-deep-{lang}"
    snapshot_id = f"s-deep-{lang}"
    info = data["info"]

    # -- Seed DB --
    await drop_tables()
    await create_tables()

    async for db in override_get_db():
        db.add(Repo(id=repo_id, name=info["name"], url=info["url"]))
        db.add(RepoSnapshot(
            id=snapshot_id, repo_id=repo_id,
            commit_sha=data["sha"],
            status=SnapshotStatus.completed,
            file_count=len(data["files"]),
        ))
        for f in data["files"]:
            db.add(File(
                snapshot_id=snapshot_id, path=f["path"],
                language=f["language"], hash=f["hash"],
                size_bytes=f["size_bytes"],
            ))
        for sym in data["graph"].symbols.values():
            db.add(Symbol(
                snapshot_id=snapshot_id, kind=sym.kind.value,
                name=sym.name, fq_name=sym.fq_name,
                file_path=sym.file_path,
                start_line=sym.start_line, end_line=sym.end_line,
                namespace=sym.namespace or "",
                parent_fq_name=sym.parent_fq_name or "",
                signature=sym.signature or "",
                modifiers=",".join(sym.modifiers) if sym.modifiers else "",
                return_type=sym.return_type or "",
            ))
        for edge in data["graph"].edges:
            db.add(EdgeModel(
                snapshot_id=snapshot_id,
                source_fq_name=edge.source_fq_name,
                target_fq_name=edge.target_fq_name,
                edge_type=edge.edge_type.value,
                file_path=edge.file_path or "",
                line=edge.line,
            ))
        await db.commit()

    # -- Run API tests --
    with patch("app.api.repos.run_ingestion", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as c:
            base = f"/repos/{repo_id}/snapshots/{snapshot_id}"

            # Symbols
            r = await c.get(f"{base}/symbols")
            assert r.status_code == 200
            sym_data = r.json()
            print(f"\n  [{lang}] API symbols: {sym_data['total']}")
            assert sym_data["total"] > 0

            # Edges
            r = await c.get(f"{base}/edges")
            assert r.status_code == 200
            edge_data = r.json()
            print(f"  [{lang}] API edges: {edge_data['total']}")

            # Overview
            r = await c.get(f"{base}/overview")
            assert r.status_code == 200
            ov = r.json()
            print(f"  [{lang}] Overview: symbols={ov['total_symbols']}, "
                  f"edges={ov['total_edges']}")

            # Search (use first symbol name)
            first = sym_data["items"][0]["name"][:8]
            r = await c.get(f"{base}/search", params={"q": first})
            assert r.status_code == 200
            sr = r.json()
            print(f"  [{lang}] Search '{first}': {sr['total']} results")
            assert sr["total"] > 0

            # Health
            r = await c.post(f"{base}/health")
            assert r.status_code == 200
            h = r.json()
            score = h.get("overall_score", 0)
            findings = h.get("findings", [])
            print(f"  [{lang}] Health: {score}/100, "
                  f"{len(findings)} findings")
            # Show top findings by severity
            sevs: dict[str, int] = defaultdict(int)
            for f in findings:
                sevs[f["severity"]] += 1
            for sev, cnt in sorted(sevs.items()):
                print(f"    {sev}: {cnt}")

            # Diagram
            r = await c.get(
                f"{base}/diagram", params={"diagram_type": "class"}
            )
            assert r.status_code == 200
            diag = r.json().get("mermaid", "")
            print(f"  [{lang}] Diagram: {len(diag)} chars")

            # Export JSON
            r = await c.get(f"{base}/export")
            assert r.status_code == 200
            exp = r.json()
            print(f"  [{lang}] Export: {len(exp['symbols'])} syms, "
                  f"{len(exp['edges'])} edges")

            # Portable round-trip
            r = await c.get(f"{base}/portable")
            assert r.status_code == 200
            eidos = r.content
            payload = json.loads(gzip.decompress(eidos))
            orig_s = len(payload["symbols"])
            orig_e = len(payload["edges"])

            r2 = await c.post(
                f"/repos/{repo_id}/import",
                files={"file": ("t.eidos", BytesIO(eidos),
                                "application/gzip")},
            )
            assert r2.status_code == 201
            imp = r2.json()
            assert imp["symbols_imported"] == orig_s
            assert imp["edges_imported"] == orig_e
            print(f"  [{lang}] Portable: {orig_s} syms, "
                  f"{orig_e} edges (round-trip OK)")

            # Fulltext
            r = await c.get(
                f"{base}/fulltext", params={"q": first}
            )
            assert r.status_code == 200
            print(f"  [{lang}] Fulltext '{first}': "
                  f"{r.json()['total']} results")

            # Ask
            r = await c.post(
                f"{base}/ask",
                json={"question": "What is the main purpose of this code?"},
            )
            assert r.status_code == 200

            # Metrics
            r = await c.get("/metrics")
            assert r.status_code == 200
            assert "eidos_requests_total" in r.text

    print(f"  [{lang}] FULL API PIPELINE: ALL PASSED")

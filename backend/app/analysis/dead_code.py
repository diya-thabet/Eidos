"""
Dead code detection via graph reachability analysis.

Goes beyond simple fan-in == 0 by doing BFS from entry points
to find deeply unreachable code, orphan classes, and dead modules.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from app.analysis.entry_points import detect_entry_points
from app.analysis.graph_builder import CodeGraph
from app.analysis.models import EdgeType, SymbolKind

logger = logging.getLogger(__name__)

_ENTRY_NAMES = frozenset({
    "main", "Main", "run", "start", "execute", "handle",
    "setup", "configure", "init", "__init__", "__main__",
    "app", "create_app", "Application",
})


@dataclass
class DeadCodeReport:
    """Complete dead code analysis result."""

    total_symbols: int = 0
    reachable_count: int = 0
    unreachable_count: int = 0
    entry_point_count: int = 0

    unreachable_functions: list[DeadSymbol] = field(default_factory=list)
    unreachable_classes: list[DeadSymbol] = field(default_factory=list)
    unreachable_modules: list[DeadModule] = field(default_factory=list)
    dead_imports: list[DeadImport] = field(default_factory=list)


@dataclass
class DeadSymbol:
    """A symbol that is unreachable from any entry point."""

    fq_name: str
    name: str
    kind: str
    file_path: str
    start_line: int
    end_line: int


@dataclass
class DeadModule:
    """A module with no reachable symbols."""

    module: str
    file_count: int
    symbol_count: int
    files: list[str]


@dataclass
class DeadImport:
    """An import where the target is unreachable."""

    source_file: str
    target: str
    line: int


def analyze_dead_code(graph: CodeGraph) -> DeadCodeReport:
    """Run full dead code analysis on a code graph."""
    report = DeadCodeReport(total_symbols=len(graph.symbols))

    roots = _collect_roots(graph)
    report.entry_point_count = len(roots)

    reachable = _bfs_reachable(graph, roots)
    report.reachable_count = len(reachable)

    all_fqs = set(graph.symbols.keys())
    unreachable = all_fqs - reachable

    for fq in sorted(unreachable):
        sym = graph.symbols[fq]
        kind_str = sym.kind.value if isinstance(sym.kind, SymbolKind) else str(sym.kind)
        ds = DeadSymbol(
            fq_name=sym.fq_name,
            name=sym.name,
            kind=kind_str,
            file_path=sym.file_path,
            start_line=sym.start_line,
            end_line=sym.end_line,
        )
        if sym.kind in (SymbolKind.METHOD, SymbolKind.CONSTRUCTOR):
            report.unreachable_functions.append(ds)
        elif sym.kind in (
            SymbolKind.CLASS, SymbolKind.INTERFACE,
            SymbolKind.STRUCT, SymbolKind.ENUM,
        ):
            report.unreachable_classes.append(ds)

    report.unreachable_count = len(unreachable)
    report.unreachable_modules = _find_dead_modules(graph, reachable)
    report.dead_imports = _find_dead_imports(graph, reachable)

    return report


def _collect_roots(graph: CodeGraph) -> set[str]:
    """Collect all symbols that serve as entry points."""
    roots: set[str] = set()

    try:
        for ep in detect_entry_points(graph):
            roots.add(ep.symbol_fq_name)
    except Exception:
        pass

    for sym in graph.symbols.values():
        if sym.name in _ENTRY_NAMES:
            roots.add(sym.fq_name)
        if sym.kind == SymbolKind.CONSTRUCTOR:
            roots.add(sym.fq_name)
        # Top-level classes with public modifier are roots
        if sym.kind in (
            SymbolKind.CLASS, SymbolKind.INTERFACE,
            SymbolKind.STRUCT,
        ) and sym.parent_fq_name is None:
            mods_str = (
                sym.modifiers if isinstance(sym.modifiers, str)
                else ",".join(sym.modifiers)
            )
            if "public" in mods_str or "export" in mods_str:
                roots.add(sym.fq_name)
        if sym.name.startswith("test") or sym.name.startswith("Test"):
            roots.add(sym.fq_name)
        if any(
            m in (
                sym.modifiers if isinstance(sym.modifiers, str)
                else ",".join(sym.modifiers)
            )
            for m in ("public", "export", "api")
        ):
            roots.add(sym.fq_name)

    return roots


def _bfs_reachable(graph: CodeGraph, roots: set[str]) -> set[str]:
    """BFS from roots following non-import edges."""
    visited: set[str] = set(roots)
    queue: deque[str] = deque(roots)

    forward: dict[str, list[str]] = {}
    for edge in graph.edges:
        if edge.edge_type == EdgeType.IMPORTS:
            continue
        forward.setdefault(edge.source_fq_name, []).append(
            edge.target_fq_name,
        )
        if edge.edge_type in (EdgeType.INHERITS, EdgeType.IMPLEMENTS):
            forward.setdefault(edge.source_fq_name, []).append(
                edge.target_fq_name,
            )

    while queue:
        current = queue.popleft()
        for neighbor in forward.get(current, []):
            if neighbor not in visited and neighbor in graph.symbols:
                visited.add(neighbor)
                queue.append(neighbor)

    return visited


def _find_dead_modules(
    graph: CodeGraph, reachable: set[str],
) -> list[DeadModule]:
    """Find modules where no symbol is reachable."""
    module_data: dict[str, dict[str, Any]] = {}
    for sym in graph.symbols.values():
        mod = sym.namespace or _folder_module(sym.file_path)
        if mod not in module_data:
            module_data[mod] = {
                "total": 0, "reachable": 0,
                "files": set(),
            }
        module_data[mod]["total"] += 1
        module_data[mod]["files"].add(sym.file_path)
        if sym.fq_name in reachable:
            module_data[mod]["reachable"] += 1

    dead: list[DeadModule] = []
    for mod, data in sorted(module_data.items()):
        if data["reachable"] == 0 and data["total"] > 0:
            dead.append(DeadModule(
                module=mod,
                file_count=len(data["files"]),
                symbol_count=data["total"],
                files=sorted(data["files"]),
            ))
    return dead


def _find_dead_imports(
    graph: CodeGraph, reachable: set[str],
) -> list[DeadImport]:
    """Find imports where the target is unreachable."""
    dead: list[DeadImport] = []
    for edge in graph.edges:
        if edge.edge_type != EdgeType.IMPORTS:
            continue
        target = edge.target_fq_name
        if target in graph.symbols and target not in reachable:
            dead.append(DeadImport(
                source_file=edge.file_path,
                target=target,
                line=edge.line,
            ))
    return dead


def _folder_module(file_path: str) -> str:
    """Extract module name from file path."""
    parts = file_path.replace("\\", "/").rsplit("/", 1)
    return parts[0] if len(parts) > 1 else ""

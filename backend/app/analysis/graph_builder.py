"""
Graph builder: constructs call graph and module dependency graph
from extracted file analyses.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field

from app.analysis.models import (
    EdgeInfo,
    EdgeType,
    FileAnalysis,
    ModuleInfo,
    SymbolInfo,
    SymbolKind,
)

logger = logging.getLogger(__name__)


@dataclass
class CodeGraph:
    """
    Complete code graph for a snapshot.

    Provides lookup methods for navigating symbols, edges, modules,
    and computing graph neighborhoods.
    """
    symbols: dict[str, SymbolInfo] = field(default_factory=dict)       # fq_name -> SymbolInfo
    edges: list[EdgeInfo] = field(default_factory=list)
    modules: dict[str, ModuleInfo] = field(default_factory=dict)       # namespace -> ModuleInfo
    files: dict[str, FileAnalysis] = field(default_factory=dict)       # path -> FileAnalysis

    # Adjacency lists (built by finalize())
    _callers: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    _callees: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    _children: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))

    def add_file_analysis(self, analysis: FileAnalysis) -> None:
        """Merge a single file's analysis results into the graph."""
        self.files[analysis.path] = analysis
        for sym in analysis.symbols:
            self.symbols[sym.fq_name] = sym
        self.edges.extend(analysis.edges)

    def finalize(self) -> None:
        """Build adjacency lists and module graph after all files are added."""
        self._callers = defaultdict(list)
        self._callees = defaultdict(list)
        self._children = defaultdict(list)

        for edge in self.edges:
            if edge.edge_type == EdgeType.CALLS:
                self._callees[edge.source_fq_name].append(edge.target_fq_name)
                self._callers[edge.target_fq_name].append(edge.source_fq_name)
            elif edge.edge_type == EdgeType.CONTAINS:
                self._children[edge.source_fq_name].append(edge.target_fq_name)

        self._build_modules()

    def get_callers(self, fq_name: str) -> list[str]:
        """Return symbols that call the given symbol."""
        return list(self._callers.get(fq_name, []))

    def get_callees(self, fq_name: str) -> list[str]:
        """Return symbols that the given symbol calls."""
        return list(self._callees.get(fq_name, []))

    def get_children(self, fq_name: str) -> list[str]:
        """Return child symbols (members of a class)."""
        return list(self._children.get(fq_name, []))

    def get_neighborhood(self, fq_name: str, depth: int = 2) -> set[str]:
        """
        BFS expansion from a symbol up to `depth` hops via call edges.
        Returns set of reachable symbol fq_names.
        """
        visited: set[str] = {fq_name}
        frontier: set[str] = {fq_name}
        for _ in range(depth):
            next_frontier: set[str] = set()
            for sym in frontier:
                for neighbor in self.get_callers(sym) + self.get_callees(sym):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        next_frontier.add(neighbor)
            frontier = next_frontier
            if not frontier:
                break
        return visited

    def get_symbols_by_kind(self, kind: SymbolKind) -> list[SymbolInfo]:
        """Return all symbols of a given kind."""
        return [s for s in self.symbols.values() if s.kind == kind]

    def get_symbols_in_file(self, file_path: str) -> list[SymbolInfo]:
        """Return all symbols declared in a given file."""
        return [s for s in self.symbols.values() if s.file_path == file_path]

    def fan_in(self, fq_name: str) -> int:
        """Number of distinct callers."""
        return len(set(self._callers.get(fq_name, [])))

    def fan_out(self, fq_name: str) -> int:
        """Number of distinct callees."""
        return len(set(self._callees.get(fq_name, [])))

    def _build_modules(self) -> None:
        """Group symbols and files into namespace-based modules."""
        ns_files: dict[str, set[str]] = defaultdict(set)
        ns_symbols: dict[str, list[str]] = defaultdict(list)
        ns_deps: dict[str, set[str]] = defaultdict(set)

        for path, fa in self.files.items():
            ns = fa.namespace or _folder_module(path)
            ns_files[ns].add(path)
            for directive in fa.using_directives:
                if directive != ns:
                    ns_deps[ns].add(directive)

        for sym in self.symbols.values():
            ns = sym.namespace or _folder_module(sym.file_path)
            ns_symbols[ns].append(sym.fq_name)

        all_namespaces = set(ns_files.keys()) | set(ns_symbols.keys())
        for ns in all_namespaces:
            self.modules[ns] = ModuleInfo(
                name=ns,
                file_count=len(ns_files.get(ns, set())),
                symbol_count=len(ns_symbols.get(ns, [])),
                files=sorted(ns_files.get(ns, set())),
                dependencies=sorted(ns_deps.get(ns, set())),
            )


def build_graph(analyses: list[FileAnalysis]) -> CodeGraph:
    """
    Build a complete code graph from a list of file analyses.

    This is the main entry point for constructing the graph after
    parsing all C# files in a snapshot.
    """
    graph = CodeGraph()
    for analysis in analyses:
        graph.add_file_analysis(analysis)
    graph.finalize()
    logger.info(
        "Graph built: %d symbols, %d edges, %d modules",
        len(graph.symbols), len(graph.edges), len(graph.modules),
    )
    return graph


def _folder_module(file_path: str) -> str:
    """Derive a module name from file path when no namespace is declared."""
    parts = file_path.replace("\\", "/").split("/")
    if len(parts) > 1:
        return "/".join(parts[:-1])
    return "<root>"

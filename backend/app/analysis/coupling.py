"""
Module coupling and cohesion metrics via pure graph analysis.

Computes quantitative metrics for each module (namespace / directory):
- Afferent coupling (Ca): modules that depend ON this module
- Efferent coupling (Ce): modules this module depends ON
- Instability: Ce / (Ca + Ce)  -- 0 = stable, 1 = unstable
- Abstractness: abstract_types / total_types
- Distance from main sequence: |A + I - 1|
- Cohesion (H): ratio of intra-module edges to total possible

Also computes a module dependency graph for cycle detection.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field

from app.analysis.graph_builder import CodeGraph
from app.analysis.models import SymbolKind

logger = logging.getLogger(__name__)


@dataclass
class ModuleMetrics:
    """Quantitative metrics for a single module."""

    name: str
    file_count: int = 0
    symbol_count: int = 0
    class_count: int = 0
    abstract_count: int = 0  # interfaces + abstract classes
    method_count: int = 0

    # Coupling
    afferent_coupling: int = 0   # Ca: incoming deps
    efferent_coupling: int = 0   # Ce: outgoing deps
    instability: float = 0.0     # Ce / (Ca + Ce)
    abstractness: float = 0.0    # abstract / total classes
    distance: float = 0.0        # |A + I - 1|

    # Cohesion
    intra_edges: int = 0         # edges within the module
    inter_edges: int = 0         # edges crossing module boundary
    cohesion: float = 0.0        # intra / (intra + inter)

    # Dependencies
    depends_on: list[str] = field(default_factory=list)
    depended_by: list[str] = field(default_factory=list)


@dataclass
class CouplingReport:
    """Complete module coupling & cohesion report."""

    total_modules: int = 0
    modules: list[ModuleMetrics] = field(default_factory=list)
    dependency_cycles: list[list[str]] = field(default_factory=list)
    avg_instability: float = 0.0
    avg_cohesion: float = 0.0
    avg_distance: float = 0.0


def analyze_coupling(graph: CodeGraph) -> CouplingReport:
    """Compute module-level coupling and cohesion metrics."""
    sym_to_mod = _assign_modules(graph)
    mod_data = _count_module_symbols(graph, sym_to_mod)
    _apply_file_counts(graph, mod_data)
    afferent, efferent, intra, inter = _compute_edge_metrics(
        graph, sym_to_mod,
    )
    _compute_derived_metrics(mod_data, afferent, efferent, intra, inter)
    cycles = _detect_cycles(efferent)

    modules = sorted(mod_data.values(), key=lambda x: x.name)
    n = len(modules)
    return CouplingReport(
        total_modules=n,
        modules=modules,
        dependency_cycles=cycles,
        avg_instability=round(
            sum(m.instability for m in modules) / n if n else 0.0, 3,
        ),
        avg_cohesion=round(
            sum(m.cohesion for m in modules) / n if n else 0.0, 3,
        ),
        avg_distance=round(
            sum(m.distance for m in modules) / n if n else 0.0, 3,
        ),
    )


def _assign_modules(graph: CodeGraph) -> dict[str, str]:
    """Map every symbol fq_name to its module name."""
    result: dict[str, str] = {}
    for sym in graph.symbols.values():
        mod = sym.namespace or _folder_module(sym.file_path)
        result[sym.fq_name] = mod
    return result


def _count_module_symbols(
    graph: CodeGraph, sym_to_mod: dict[str, str],
) -> dict[str, ModuleMetrics]:
    """Count symbols per module."""
    mod_data: dict[str, ModuleMetrics] = {}
    for sym in graph.symbols.values():
        mod = sym_to_mod.get(sym.fq_name, "")
        if not mod:
            continue
        if mod not in mod_data:
            mod_data[mod] = ModuleMetrics(name=mod)
        m = mod_data[mod]
        m.symbol_count += 1
        if sym.kind in (SymbolKind.METHOD, SymbolKind.CONSTRUCTOR):
            m.method_count += 1
        if sym.kind in (
            SymbolKind.CLASS, SymbolKind.STRUCT,
            SymbolKind.ENUM, SymbolKind.RECORD,
        ):
            m.class_count += 1
        if sym.kind == SymbolKind.INTERFACE:
            m.abstract_count += 1
            m.class_count += 1
        if "abstract" in (
            sym.modifiers if isinstance(sym.modifiers, str)
            else ",".join(sym.modifiers)
        ):
            m.abstract_count += 1
    return mod_data


def _apply_file_counts(
    graph: CodeGraph, mod_data: dict[str, ModuleMetrics],
) -> None:
    """Apply file counts from graph.modules."""
    for gm in graph.modules.values():
        if gm.name in mod_data:
            mod_data[gm.name].file_count = gm.file_count


def _compute_edge_metrics(
    graph: CodeGraph, sym_to_mod: dict[str, str],
) -> tuple[
    dict[str, set[str]], dict[str, set[str]],
    dict[str, int], dict[str, int],
]:
    """Compute afferent, efferent, intra, and inter edge counts."""
    afferent: dict[str, set[str]] = defaultdict(set)
    efferent: dict[str, set[str]] = defaultdict(set)
    intra: dict[str, int] = defaultdict(int)
    inter: dict[str, int] = defaultdict(int)

    for edge in graph.edges:
        src_mod = sym_to_mod.get(edge.source_fq_name, "")
        tgt_mod = sym_to_mod.get(edge.target_fq_name, "")
        if not src_mod or not tgt_mod:
            continue
        if src_mod == tgt_mod:
            intra[src_mod] += 1
        else:
            inter[src_mod] += 1
            inter[tgt_mod] += 1
            efferent[src_mod].add(tgt_mod)
            afferent[tgt_mod].add(src_mod)
    return afferent, efferent, intra, inter


def _compute_derived_metrics(
    mod_data: dict[str, ModuleMetrics],
    afferent: dict[str, set[str]],
    efferent: dict[str, set[str]],
    intra: dict[str, int],
    inter: dict[str, int],
) -> None:
    """Compute instability, abstractness, distance, cohesion."""
    for mod, m in mod_data.items():
        m.afferent_coupling = len(afferent.get(mod, set()))
        m.efferent_coupling = len(efferent.get(mod, set()))
        total_coupling = m.afferent_coupling + m.efferent_coupling
        m.instability = (
            m.efferent_coupling / total_coupling
            if total_coupling > 0 else 0.0
        )
        m.abstractness = (
            m.abstract_count / m.class_count
            if m.class_count > 0 else 0.0
        )
        m.distance = abs(m.abstractness + m.instability - 1.0)
        total_edges = intra.get(mod, 0) + inter.get(mod, 0)
        m.intra_edges = intra.get(mod, 0)
        m.inter_edges = inter.get(mod, 0)
        m.cohesion = m.intra_edges / total_edges if total_edges > 0 else 0.0
        m.depends_on = sorted(efferent.get(mod, set()))
        m.depended_by = sorted(afferent.get(mod, set()))


def _folder_module(file_path: str) -> str:
    parts = file_path.replace("\\", "/").rsplit("/", 1)
    return parts[0] if len(parts) > 1 else ""


def _detect_cycles(
    efferent: dict[str, set[str]],
) -> list[list[str]]:
    """Find all cycles in the module dependency graph (DFS)."""
    visited: set[str] = set()
    on_stack: set[str] = set()
    cycles: list[list[str]] = []
    path: list[str] = []

    def dfs(node: str) -> None:
        if node in on_stack:
            # Found cycle: extract from path
            idx = path.index(node)
            cycle = path[idx:] + [node]
            # Normalize: start from smallest element
            mn = min(cycle[:-1])
            mi = cycle.index(mn)
            normalized = cycle[mi:-1] + cycle[:mi] + [mn]
            if normalized not in cycles:
                cycles.append(normalized)
            return
        if node in visited:
            return
        visited.add(node)
        on_stack.add(node)
        path.append(node)
        for dep in efferent.get(node, set()):
            dfs(dep)
        path.pop()
        on_stack.discard(node)

    for node in efferent:
        if node not in visited:
            dfs(node)

    return cycles

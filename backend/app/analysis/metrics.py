"""
Basic code metrics for symbols.

Computes lightweight complexity indicators that help prioritize
which code is worth deeper analysis.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.analysis.graph_builder import CodeGraph
from app.analysis.models import SymbolInfo, SymbolKind


@dataclass
class SymbolMetrics:
    """Computed metrics for a single symbol."""
    fq_name: str
    kind: str
    lines_of_code: int
    fan_in: int    # how many callers
    fan_out: int   # how many callees
    child_count: int  # members for classes, 0 for methods
    is_public: bool
    is_static: bool


def compute_metrics(graph: CodeGraph) -> list[SymbolMetrics]:
    """
    Compute metrics for all symbols in the graph.

    Returns a list of SymbolMetrics sorted by lines_of_code descending
    (largest symbols first, useful for identifying complex areas).
    """
    results: list[SymbolMetrics] = []
    for sym in graph.symbols.values():
        loc = sym.end_line - sym.start_line + 1
        metrics = SymbolMetrics(
            fq_name=sym.fq_name,
            kind=sym.kind.value,
            lines_of_code=loc,
            fan_in=graph.fan_in(sym.fq_name),
            fan_out=graph.fan_out(sym.fq_name),
            child_count=len(graph.get_children(sym.fq_name)),
            is_public="public" in sym.modifiers,
            is_static="static" in sym.modifiers,
        )
        results.append(metrics)

    results.sort(key=lambda m: m.lines_of_code, reverse=True)
    return results


def find_hotspots(graph: CodeGraph, min_fan_in: int = 3, min_loc: int = 50) -> list[SymbolMetrics]:
    """
    Identify potential hotspot symbols: large methods with high fan-in.

    These are symbols that are called by many others AND are large,
    making them high-risk for regressions.
    """
    all_metrics = compute_metrics(graph)
    return [
        m for m in all_metrics
        if m.fan_in >= min_fan_in and m.lines_of_code >= min_loc
    ]

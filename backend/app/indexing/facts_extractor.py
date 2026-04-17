"""
Deterministic facts extractor.

Builds structured fact dictionaries from the CodeGraph **without** any LLM
call.  These facts form the ground-truth input that a summariser (human or
AI) can later narrate.
"""

from __future__ import annotations

import logging
from typing import Any

from app.analysis.graph_builder import CodeGraph
from app.analysis.models import SymbolKind
from app.indexing.summary_schema import (
    Citation,
    Confidence,
    FileSummary,
    ModuleSummary,
    SymbolSummary,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_symbol_facts(graph: CodeGraph) -> list[SymbolSummary]:
    """
    Build a deterministic ``SymbolSummary`` for every symbol in *graph*.

    No AI is involved -- the ``purpose`` field is synthesised from the
    symbol's signature, kind, modifiers and relationships.
    """
    summaries: list[SymbolSummary] = []
    for sym in graph.symbols.values():
        purpose = _build_purpose(sym, graph)
        inputs = list(sym.parameters) if sym.parameters else []
        outputs = [sym.return_type] if sym.return_type else []

        side_effects = _infer_side_effects(sym, graph)
        assumptions = _infer_assumptions(sym, graph)
        risks = _infer_risks(sym, graph)

        citations = [
            Citation(
                file_path=sym.file_path,
                symbol_fq_name=sym.fq_name,
                start_line=sym.start_line,
                end_line=sym.end_line,
            )
        ]

        confidence = _assess_confidence(sym, graph)

        summaries.append(
            SymbolSummary(
                fq_name=sym.fq_name,
                kind=sym.kind.value,
                purpose=purpose,
                inputs=inputs,
                outputs=outputs,
                side_effects=side_effects,
                assumptions=assumptions,
                risks=risks,
                citations=citations,
                confidence=confidence,
            )
        )

    logger.info("Extracted facts for %d symbols", len(summaries))
    return summaries


def extract_module_facts(graph: CodeGraph) -> list[ModuleSummary]:
    """
    Build a deterministic ``ModuleSummary`` for every module (namespace)
    in *graph*.
    """
    summaries: list[ModuleSummary] = []
    for mod in graph.modules.values():
        key_classes = [
            sym.fq_name
            for sym in graph.symbols.values()
            if sym.namespace == mod.name and sym.kind in (SymbolKind.CLASS, SymbolKind.INTERFACE)
        ]

        purpose = (
            f"Module '{mod.name}' contains {mod.symbol_count} symbols"
            f" across {mod.file_count} files."
        )
        if mod.dependencies:
            deps = ", ".join(mod.dependencies[:5])
            purpose += f" Depends on: {deps}."

        citations = [
            Citation(file_path=f, symbol_fq_name="", start_line=0, end_line=0) for f in mod.files
        ]

        summaries.append(
            ModuleSummary(
                name=mod.name,
                purpose=purpose,
                responsibilities=[f"Defines {len(key_classes)} types"],
                key_classes=key_classes,
                dependencies=mod.dependencies,
                entry_points=[],
                citations=citations,
                confidence=Confidence.HIGH if mod.symbol_count > 0 else Confidence.LOW,
            )
        )

    logger.info("Extracted facts for %d modules", len(summaries))
    return summaries


def extract_file_facts(graph: CodeGraph) -> list[FileSummary]:
    """
    Build a deterministic ``FileSummary`` for every analysed file.
    """
    summaries: list[FileSummary] = []
    for path, fa in graph.files.items():
        symbols_in_file = [sym.fq_name for sym in graph.symbols.values() if sym.file_path == path]

        type_names = [
            sym.name
            for sym in graph.symbols.values()
            if sym.file_path == path
            and sym.kind in (SymbolKind.CLASS, SymbolKind.INTERFACE, SymbolKind.STRUCT)
        ]

        purpose = f"Defines {', '.join(type_names)}." if type_names else "Utility file."
        if fa.namespace:
            purpose = f"[{fa.namespace}] {purpose}"

        summaries.append(
            FileSummary(
                path=path,
                purpose=purpose,
                symbols=symbols_in_file,
                namespace=fa.namespace,
                imports=fa.using_directives,
                citations=[Citation(file_path=path)],
                confidence=Confidence.HIGH if symbols_in_file else Confidence.LOW,
            )
        )

    logger.info("Extracted facts for %d files", len(summaries))
    return summaries


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_purpose(sym: Any, graph: CodeGraph) -> str:
    """Synthesise a purpose string from structural facts."""
    kind = sym.kind.value
    name = sym.name

    if sym.kind == SymbolKind.CLASS:
        child_count = len(graph.get_children(sym.fq_name))
        base = f"Class '{name}' with {child_count} members."
        if sym.base_types:
            base += f" Implements/extends: {', '.join(sym.base_types)}."
        return base

    if sym.kind == SymbolKind.INTERFACE:
        return f"Interface '{name}' defining a contract."

    if sym.kind == SymbolKind.METHOD:
        callees = graph.get_callees(sym.fq_name)
        callers = graph.get_callers(sym.fq_name)
        parts = [f"Method '{name}'"]
        if sym.return_type:
            parts.append(f"returns {sym.return_type}")
        if sym.parameters:
            parts.append(f"takes {len(sym.parameters)} parameter(s)")
        if callees:
            parts.append(f"calls {len(callees)} other symbol(s)")
        if callers:
            parts.append(f"called by {len(callers)} symbol(s)")
        return ", ".join(parts) + "."

    if sym.kind == SymbolKind.CONSTRUCTOR:
        return f"Constructor for '{sym.parent_fq_name or name}'."

    if sym.kind == SymbolKind.PROPERTY:
        return f"Property '{name}' of type {sym.return_type or 'unknown'}."

    if sym.kind == SymbolKind.FIELD:
        return f"Field '{name}'."

    if sym.kind == SymbolKind.ENUM:
        return f"Enum '{name}'."

    return f"{kind.title()} '{name}'."


def _infer_side_effects(sym: Any, graph: CodeGraph) -> list[str]:
    """Flag potential side effects from callees."""
    effects: list[str] = []
    if sym.kind not in (SymbolKind.METHOD, SymbolKind.CONSTRUCTOR):
        return effects

    callees = graph.get_callees(sym.fq_name)
    for target in callees:
        lower = target.lower()
        if any(
            kw in lower
            for kw in ("write", "save", "delete", "remove", "send", "post", "update", "insert")
        ):
            effects.append(f"Calls '{target}' which may perform writes/mutations.")
        if any(kw in lower for kw in ("log", "print", "trace", "console")):
            effects.append(f"Calls '{target}' (logging/output).")
    return effects


def _infer_assumptions(sym: Any, graph: CodeGraph) -> list[str]:
    """Flag implicit assumptions."""
    assumptions: list[str] = []
    if sym.kind == SymbolKind.METHOD:
        if not sym.parameters:
            assumptions.append("Takes no parameters; may rely on instance state.")
        if "static" in sym.modifiers and sym.parameters:
            assumptions.append("Static method; no instance state available.")
    return assumptions


def _infer_risks(sym: Any, graph: CodeGraph) -> list[str]:
    """Flag potential risks from graph structure."""
    risks: list[str] = []
    fan_in = graph.fan_in(sym.fq_name)
    fan_out = graph.fan_out(sym.fq_name)
    loc = sym.end_line - sym.start_line + 1

    if fan_in >= 5:
        risks.append(f"High fan-in ({fan_in} callers) - changes here have wide impact.")
    if fan_out >= 5:
        risks.append(f"High fan-out ({fan_out} callees) - complex orchestration.")
    if loc >= 50:
        risks.append(f"Large method ({loc} lines) - consider splitting.")
    return risks


def _assess_confidence(sym: Any, graph: CodeGraph) -> Confidence:
    """Assess confidence based on available information."""
    score = 0
    if sym.signature:
        score += 1
    if sym.parameters or sym.return_type:
        score += 1
    if sym.doc_comment:
        score += 1
    if graph.get_callers(sym.fq_name) or graph.get_callees(sym.fq_name):
        score += 1

    if score >= 3:
        return Confidence.HIGH
    if score >= 1:
        return Confidence.MEDIUM
    return Confidence.LOW

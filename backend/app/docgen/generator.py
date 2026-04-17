"""
Deterministic document generator.

Builds ``GeneratedDocument`` objects from code graph data, summaries,
and analysis results. All content is factual -- LLM narration is
handled separately by the orchestrator.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from typing import Any

from app.docgen.models import Citation, DocSection, DocType, GeneratedDocument
from app.docgen.templates import (
    SEC_CALLERS,
    SEC_CLASSES,
    SEC_CONFIGURATION,
    SEC_DEPENDENCIES,
    SEC_ENTRY_POINTS,
    SEC_FILES,
    SEC_FLOW_STEPS,
    SEC_HOTSPOTS,
    SEC_INTERNAL,
    SEC_KEY_FLOWS,
    SEC_KNOWN_RISKS,
    SEC_METRICS,
    SEC_MODULES,
    SEC_OVERVIEW,
    SEC_PUBLIC_API,
    SEC_QUICK_START,
    SEC_SIDE_EFFECTS,
    SEC_TECH_STACK,
    get_template_sections,
)

logger = logging.getLogger(__name__)

# Types considered "types" (classes, interfaces, structs)
_TYPE_KINDS = {"class", "interface", "struct", "record", "enum"}


def generate_readme(
    snapshot_id: str,
    symbols: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    modules: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    entry_points: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
) -> GeneratedDocument:
    """Generate a README document for the entire codebase."""
    doc = GeneratedDocument(
        doc_type=DocType.README,
        title="README",
        snapshot_id=snapshot_id,
    )
    sections_spec = get_template_sections(DocType.README)

    for key, heading in sections_spec:
        section = _build_section(
            key,
            heading,
            symbols=symbols,
            edges=edges,
            modules=modules,
            summaries=summaries,
            entry_points=entry_points,
            metrics=metrics,
        )
        doc.sections.append(section)

    doc.metadata = {
        "total_symbols": len(symbols),
        "total_edges": len(edges),
        "total_modules": len(modules),
    }
    return doc


def generate_architecture(
    snapshot_id: str,
    symbols: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    modules: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    entry_points: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
) -> GeneratedDocument:
    """Generate an architecture document."""
    doc = GeneratedDocument(
        doc_type=DocType.ARCHITECTURE,
        title="Architecture",
        snapshot_id=snapshot_id,
    )
    for key, heading in get_template_sections(DocType.ARCHITECTURE):
        doc.sections.append(
            _build_section(
                key,
                heading,
                symbols=symbols,
                edges=edges,
                modules=modules,
                summaries=summaries,
                entry_points=entry_points,
                metrics=metrics,
            )
        )
    return doc


def generate_module_doc(
    snapshot_id: str,
    module_name: str,
    symbols: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    files: list[str],
    dependencies: list[str],
) -> GeneratedDocument:
    """Generate documentation for a single module/namespace."""
    mod_symbols = [s for s in symbols if s.get("namespace") == module_name]

    doc = GeneratedDocument(
        doc_type=DocType.MODULE,
        title=f"Module: {module_name}",
        snapshot_id=snapshot_id,
        scope_id=module_name,
    )

    for key, heading in get_template_sections(DocType.MODULE):
        section = DocSection(heading=heading)

        if key == SEC_OVERVIEW:
            mod_summary = _find_summary(summaries, "module", module_name)
            section.body = mod_summary or (
                f"Module `{module_name}` contains "
                f"{len(mod_symbols)} symbols across {len(files)} files."
            )

        elif key == SEC_FILES:
            lines = [f"- `{f}`" for f in sorted(files)]
            section.body = "\n".join(lines) if lines else "No files."
            section.citations = [Citation(file_path=f) for f in files]

        elif key == SEC_CLASSES:
            types = [s for s in mod_symbols if s.get("kind") in _TYPE_KINDS]
            lines = []
            for t in types:
                sig = t.get("signature", t.get("name", ""))
                lines.append(f"- **`{t['fq_name']}`** ({t['kind']}): `{sig}`")
                section.citations.append(
                    Citation(
                        file_path=t.get("file_path", ""),
                        symbol_fq_name=t["fq_name"],
                        start_line=t.get("start_line", 0),
                        end_line=t.get("end_line", 0),
                    )
                )
            section.body = "\n".join(lines) if lines else "No types."

        elif key == SEC_PUBLIC_API:
            public = [
                s
                for s in mod_symbols
                if "public" in s.get("modifiers", "") and s.get("kind") in ("method", "property")
            ]
            lines = []
            for p in public:
                sig = p.get("signature", p.get("name", ""))
                lines.append(f"- `{sig}`")
                section.citations.append(
                    Citation(
                        file_path=p.get("file_path", ""),
                        symbol_fq_name=p["fq_name"],
                        start_line=p.get("start_line", 0),
                    )
                )
            section.body = "\n".join(lines) if lines else "No public API."

        elif key == SEC_INTERNAL:
            internal = [
                s
                for s in mod_symbols
                if "public" not in s.get("modifiers", "")
                and s.get("kind") in ("method", "property", "field")
            ]
            section.body = f"{len(internal)} internal members." if internal else "None."

        elif key == SEC_DEPENDENCIES:
            lines = [f"- `{d}`" for d in sorted(dependencies)]
            section.body = "\n".join(lines) if lines else "No dependencies."

        doc.sections.append(section)

    return doc


def generate_flow_doc(
    snapshot_id: str,
    entry_fq_name: str,
    symbols: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
) -> GeneratedDocument:
    """Generate a flow document tracing a call chain from an entry point."""
    doc = GeneratedDocument(
        doc_type=DocType.FLOW,
        title=f"Flow: {entry_fq_name}",
        snapshot_id=snapshot_id,
        scope_id=entry_fq_name,
    )

    # Build adjacency for outbound calls
    callees: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        if e.get("edge_type") == "calls":
            callees[e["source_fq_name"]].append(e["target_fq_name"])

    # BFS trace
    steps: list[tuple[int, str]] = []
    visited: set[str] = set()
    queue: list[tuple[int, str]] = [(0, entry_fq_name)]
    while queue and len(steps) < 30:
        depth, fq = queue.pop(0)
        if fq in visited:
            continue
        visited.add(fq)
        steps.append((depth, fq))
        for callee in callees.get(fq, []):
            if callee not in visited:
                queue.append((depth + 1, callee))

    sym_map = {s["fq_name"]: s for s in symbols if "fq_name" in s}

    for key, heading in get_template_sections(DocType.FLOW):
        section = DocSection(heading=heading)

        if key == SEC_OVERVIEW:
            summary = _find_summary(summaries, "symbol", entry_fq_name)
            section.body = summary or f"Call flow starting from `{entry_fq_name}`."

        elif key == SEC_FLOW_STEPS:
            lines = []
            for depth, fq in steps:
                indent = "  " * depth
                sym = sym_map.get(fq, {})
                kind = sym.get("kind", "?")
                fp = sym.get("file_path", "")
                lines.append(f"{indent}- `{fq}` ({kind}) [{fp}]")
                if fp:
                    section.citations.append(
                        Citation(
                            file_path=fp,
                            symbol_fq_name=fq,
                            start_line=sym.get("start_line", 0),
                            end_line=sym.get("end_line", 0),
                        )
                    )
            section.body = "\n".join(lines) if lines else "No steps traced."

        elif key == SEC_CALLERS:
            callers_of_entry = [
                e["source_fq_name"]
                for e in edges
                if e.get("edge_type") == "calls" and e.get("target_fq_name") == entry_fq_name
            ]
            lines = [f"- `{c}`" for c in sorted(set(callers_of_entry))]
            section.body = "\n".join(lines) if lines else "No callers found."

        elif key == SEC_SIDE_EFFECTS:
            se_keywords = (
                "write",
                "save",
                "delete",
                "send",
                "post",
                "log",
                "emit",
            )
            effects = []
            for _, fq in steps:
                if any(kw in fq.lower() for kw in se_keywords):
                    effects.append(f"- `{fq}` may perform I/O or mutations.")
            section.body = "\n".join(effects) if effects else "No obvious side effects."

        doc.sections.append(section)

    return doc


def generate_runbook(
    snapshot_id: str,
    symbols: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    modules: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    entry_points: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
) -> GeneratedDocument:
    """Generate a runbook/operations document."""
    doc = GeneratedDocument(
        doc_type=DocType.RUNBOOK,
        title="Runbook",
        snapshot_id=snapshot_id,
    )
    for key, heading in get_template_sections(DocType.RUNBOOK):
        doc.sections.append(
            _build_section(
                key,
                heading,
                symbols=symbols,
                edges=edges,
                modules=modules,
                summaries=summaries,
                entry_points=entry_points,
                metrics=metrics,
            )
        )
    return doc


# -------------------------------------------------------------------
# Shared section builder
# -------------------------------------------------------------------


def _build_section(
    key: str,
    heading: str,
    *,
    symbols: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    modules: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    entry_points: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
) -> DocSection:
    """Build a section from analysis data."""
    section = DocSection(heading=heading)

    if key == SEC_OVERVIEW:
        kind_counts = Counter(s.get("kind", "unknown") for s in symbols)
        summary_parts = [f"{count} {kind}(s)" for kind, count in kind_counts.most_common()]
        section.body = (
            f"Codebase contains {len(symbols)} symbols "
            f"({', '.join(summary_parts)}), "
            f"{len(edges)} relationships, "
            f"and {len(modules)} modules."
        )

    elif key == SEC_TECH_STACK:
        languages = Counter(s.get("file_path", "").rsplit(".", 1)[-1] for s in symbols)
        lines = [f"- **{ext}**: {count} symbols" for ext, count in languages.most_common(5)]
        section.body = "\n".join(lines) if lines else "Unknown."

    elif key == SEC_MODULES:
        lines = []
        for mod in sorted(modules, key=lambda m: m.get("name", "")):
            name = mod.get("name", "?")
            sc = mod.get("symbol_count", 0)
            fc = mod.get("file_count", 0)
            deps = mod.get("dependencies", [])
            dep_str = f" -> {', '.join(deps[:3])}" if deps else ""
            lines.append(f"- **`{name}`** ({sc} symbols, {fc} files){dep_str}")
        section.body = "\n".join(lines) if lines else "No modules."

    elif key == SEC_ENTRY_POINTS:
        lines = []
        for ep in entry_points:
            fq = ep.get("symbol_fq_name", "?")
            kind = ep.get("kind", "?")
            fp = ep.get("file_path", "")
            route = ep.get("route", "")
            label = f"- `{fq}` ({kind})"
            if route:
                label += f" `{route}`"
            lines.append(label)
            if fp:
                section.citations.append(Citation(file_path=fp, symbol_fq_name=fq))
        section.body = "\n".join(lines) if lines else "No entry points."

    elif key == SEC_KEY_FLOWS:
        controllers = [
            ep for ep in entry_points if ep.get("kind") in ("controller_action", "minimal_api")
        ]
        if controllers:
            lines = [
                f"- **{ep.get('route', ep.get('symbol_fq_name', '?'))}**"
                f" -> `{ep.get('symbol_fq_name', '?')}`"
                for ep in controllers[:10]
            ]
            section.body = "\n".join(lines)
        else:
            section.body = "No HTTP flows detected."

    elif key == SEC_DEPENDENCIES:
        dep_set: set[str] = set()
        for mod in modules:
            dep_set.update(mod.get("dependencies", []))
        internal = {m.get("name", "") for m in modules}
        external = sorted(dep_set - internal)
        lines = [f"- `{d}`" for d in external[:20]]
        section.body = "\n".join(lines) if lines else "No external dependencies."

    elif key in (SEC_METRICS, SEC_HOTSPOTS):
        if metrics:
            lines = [
                f"- `{m.get('fq_name', '?')}`: "
                f"LOC={m.get('lines_of_code', 0)}, "
                f"fan-in={m.get('fan_in', 0)}, "
                f"fan-out={m.get('fan_out', 0)}"
                for m in metrics[:10]
            ]
            section.body = "\n".join(lines)
        else:
            section.body = "No metrics available."

    elif key == SEC_QUICK_START:
        section.body = (
            "1. Clone the repository\n"
            "2. Build the solution\n"
            "3. Run the application\n\n"
            "_Refer to entry points below for the main startup path._"
        )

    elif key == SEC_CONFIGURATION:
        config_symbols = [
            s
            for s in symbols
            if any(
                kw in s.get("name", "").lower() for kw in ("config", "setting", "option", "startup")
            )
        ]
        if config_symbols:
            lines = [
                f"- `{s['fq_name']}` in `{s.get('file_path', '')}`" for s in config_symbols[:10]
            ]
            section.body = "\n".join(lines)
        else:
            section.body = "No configuration classes detected."

    elif key == SEC_KNOWN_RISKS:
        risky = [m for m in metrics if m.get("fan_in", 0) >= 5 or m.get("lines_of_code", 0) >= 50]
        if risky:
            lines = [
                f"- **`{m.get('fq_name', '?')}`**: "
                f"LOC={m.get('lines_of_code', 0)}, "
                f"fan-in={m.get('fan_in', 0)}"
                for m in risky[:10]
            ]
            section.body = "\n".join(lines)
        else:
            section.body = "No high-risk symbols detected."

    return section


def _find_summary(summaries: list[dict[str, Any]], scope_type: str, scope_id: str) -> str:
    """Find a summary's purpose text by scope type and id."""
    for s in summaries:
        if s.get("scope_type") == scope_type and s.get("scope_id") == scope_id:
            data = s.get("summary", {})
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except (json.JSONDecodeError, TypeError):
                    return str(data)
            return str(data.get("purpose", ""))
    return ""

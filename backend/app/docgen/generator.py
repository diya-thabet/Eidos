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


def generate_api_reference(
    snapshot_id: str,
    module_name: str,
    symbols: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
) -> GeneratedDocument:
    """Generate API reference documentation for a module."""
    mod_symbols = [s for s in symbols if s.get("namespace") == module_name]
    types = [s for s in mod_symbols if s.get("kind") in _TYPE_KINDS]
    functions = [
        s for s in mod_symbols
        if s.get("kind") in ("function", "method")
        and "public" in s.get("modifiers", "")
    ]

    doc = GeneratedDocument(
        doc_type=DocType.API_REFERENCE,
        title=f"API Reference: {module_name}",
        snapshot_id=snapshot_id,
        scope_id=module_name,
    )

    # Overview
    overview = DocSection(heading="API Reference Overview")
    overview.body = (
        f"Public API documentation for module `{module_name}`.\n\n"
        f"- **{len(types)}** classes/types\n"
        f"- **{len(functions)}** public methods/functions"
    )
    doc.sections.append(overview)

    # Classes & Types
    classes_section = DocSection(heading="Classes & Types")
    lines = []
    for t in sorted(types, key=lambda x: x.get("fq_name", "")):
        sig = t.get("signature", t.get("name", ""))
        summary = _find_summary(summaries, "symbol", t.get("fq_name", ""))
        desc = f" \u2014 {summary}" if summary else ""
        lines.append(f"### `{t['fq_name']}`\n\n**Kind**: {t.get('kind', 'class')}{desc}\n")
        lines.append(f"**Source**: `{t.get('file_path', '')}#L{t.get('start_line', 0)}`\n")
        classes_section.citations.append(Citation(
            file_path=t.get("file_path", ""),
            symbol_fq_name=t["fq_name"],
            start_line=t.get("start_line", 0),
            end_line=t.get("end_line", 0),
        ))
    classes_section.body = "\n".join(lines) if lines else "No public types."
    doc.sections.append(classes_section)

    # Methods
    methods_section = DocSection(heading="Public Methods")
    method_lines = []
    for f in sorted(functions, key=lambda x: x.get("fq_name", "")):
        sig = f.get("signature", f.get("name", ""))
        summary = _find_summary(summaries, "symbol", f.get("fq_name", ""))
        desc = f"\n  {summary}" if summary else ""
        method_lines.append(f"- **`{sig}`**{desc}")
        methods_section.citations.append(Citation(
            file_path=f.get("file_path", ""),
            symbol_fq_name=f["fq_name"],
            start_line=f.get("start_line", 0),
        ))
    methods_section.body = "\n".join(method_lines) if method_lines else "No public methods."
    doc.sections.append(methods_section)

    # Parameters
    params_section = DocSection(heading="Parameters & Return Types")
    param_lines = []
    for f in functions[:20]:
        sig = f.get("signature", "")
        if sig:
            param_lines.append(f"- `{sig}`")
    params_section.body = "\n".join(param_lines) if param_lines else "No parameter info available."
    doc.sections.append(params_section)

    doc.metadata = {
        "module": module_name,
        "types_count": len(types),
        "methods_count": len(functions),
    }
    return doc


def generate_onboarding(
    snapshot_id: str,
    symbols: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    modules: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    entry_points: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
) -> GeneratedDocument:
    """Generate an onboarding/getting-started guide."""
    doc = GeneratedDocument(
        doc_type=DocType.ONBOARDING,
        title="Onboarding Guide",
        snapshot_id=snapshot_id,
    )

    total_files = len({s.get("file_path", "") for s in symbols})

    # Welcome
    welcome = DocSection(heading="Welcome")
    welcome.body = (
        f"Welcome to the project! This guide helps new contributors get started.\n\n"
        f"The codebase contains **{len(symbols)}** symbols across "
        f"**{total_files}** files organized into **{len(modules)}** modules."
    )
    doc.sections.append(welcome)

    # Setup
    setup = DocSection(heading="Setup & Installation")
    config_files = sorted({
        s.get("file_path", "") for s in symbols
        if any(k in s.get("file_path", "").lower() for k in ("config", "settings", "env"))
    })[:5]
    if config_files:
        setup_lines = ["Check the following configuration files:", ""]
        for cf in config_files:
            setup_lines.append(f"- `{cf}`")
            setup.citations.append(Citation(file_path=cf))
        setup.body = "\n".join(setup_lines)
    else:
        setup.body = "No configuration files detected. Check the project README."
    doc.sections.append(setup)

    # Project Structure
    structure = DocSection(heading="Project Structure")
    struct_lines = [
        "| Module | Files | Symbols | Description |",
        "|--------|-------|---------|-------------|",
    ]
    for m in sorted(modules, key=lambda x: x.get("symbol_count", 0), reverse=True)[:15]:
        mod_summary = _find_summary(summaries, "module", m.get("name", ""))
        desc = (mod_summary[:60] + "...") if mod_summary and len(mod_summary) > 60 else (
            mod_summary or ""
        )
        struct_lines.append(
            f"| `{m.get('name', '')}` | {m.get('file_count', 0)} | "
            f"{m.get('symbol_count', 0)} | {desc} |"
        )
    structure.body = "\n".join(struct_lines)
    doc.sections.append(structure)

    # Entry Points
    ep_section = DocSection(heading="Entry Points")
    ep_lines = []
    for ep in entry_points[:10]:
        fq = ep.get("symbol_fq_name", "")
        ep_lines.append(f"- `{fq}` ({ep.get('kind', '')})")
        ep_section.citations.append(Citation(
            file_path=ep.get("file_path", ""), symbol_fq_name=fq,
            start_line=ep.get("line", 0),
        ))
    ep_section.body = "\n".join(ep_lines) if ep_lines else "No entry points detected."
    doc.sections.append(ep_section)

    # Key Flows
    flow_section = DocSection(heading="Key Flows")
    flow_lines = []
    for ep in entry_points[:5]:
        fq = ep.get("symbol_fq_name", "")
        callees = [e.get("target_fq_name", "") for e in edges if e.get("source_fq_name") == fq][:5]
        if callees:
            flow_lines.append(f"**{fq}** calls:")
            for c in callees:
                flow_lines.append(f"  - `{c}`")
            flow_lines.append("")
    flow_section.body = "\n".join(flow_lines) if flow_lines else "No flow data available."
    doc.sections.append(flow_section)

    # Where to Find
    where = DocSection(heading="Where to Find Things")
    where_lines = []
    for m in sorted(modules, key=lambda x: x.get("name", ""))[:15]:
        files = m.get("files", [])
        where_lines.append(f"- **{m.get('name', '')}**: `{files[0] if files else ''}`")
    where.body = "\n".join(where_lines) if where_lines else "See module list above."
    doc.sections.append(where)

    # First Steps
    first = DocSection(heading="First Steps for Contributors")
    first.body = (
        "1. Read the Architecture doc to understand the high-level design\n"
        "2. Pick a module from the structure table above\n"
        "3. Read its module doc for implementation details\n"
        "4. Look at the entry points to understand request flow\n"
        "5. Run the test suite to verify your setup"
    )
    doc.sections.append(first)

    doc.metadata = {
        "total_symbols": len(symbols),
        "total_modules": len(modules),
        "entry_points_count": len(entry_points),
    }
    return doc


def generate_changelog(
    snapshot_id: str,
    previous_snapshot_id: str,
    current_symbols: list[dict[str, Any]],
    previous_symbols: list[dict[str, Any]],
    current_edges: list[dict[str, Any]],
    previous_edges: list[dict[str, Any]],
) -> GeneratedDocument:
    """Generate a changelog comparing two snapshots."""
    doc = GeneratedDocument(
        doc_type=DocType.CHANGELOG,
        title="Changelog",
        snapshot_id=snapshot_id,
        scope_id=previous_snapshot_id,
    )

    cur_fqs = {s.get("fq_name", "") for s in current_symbols}
    prev_fqs = {s.get("fq_name", "") for s in previous_symbols}

    added_fqs = cur_fqs - prev_fqs
    removed_fqs = prev_fqs - cur_fqs
    common_fqs = cur_fqs & prev_fqs

    prev_sigs = {s.get("fq_name", ""): s.get("signature", "") for s in previous_symbols}
    cur_sigs = {s.get("fq_name", ""): s.get("signature", "") for s in current_symbols}
    modified_fqs = {fq for fq in common_fqs if prev_sigs.get(fq) != cur_sigs.get(fq)}

    breaking = [
        s.get("fq_name", "") for s in previous_symbols
        if s.get("fq_name", "") in removed_fqs and "public" in s.get("modifiers", "")
    ]

    # Overview
    overview = DocSection(heading="Change Summary")
    overview.body = (
        f"Comparing snapshot `{snapshot_id}` vs `{previous_snapshot_id}`:\n\n"
        f"- **{len(added_fqs)}** symbols added\n"
        f"- **{len(removed_fqs)}** symbols removed\n"
        f"- **{len(modified_fqs)}** symbols modified\n"
        f"- **{len(breaking)}** breaking changes"
    )
    doc.sections.append(overview)

    # Added
    added_section = DocSection(heading="Added")
    added_symbols = [s for s in current_symbols if s.get("fq_name", "") in added_fqs]
    added_lines = []
    for s in sorted(added_symbols, key=lambda x: x.get("fq_name", ""))[:50]:
        added_lines.append(f"- `{s.get('fq_name', '')}` ({s.get('kind', '')})")
        added_section.citations.append(Citation(
            file_path=s.get("file_path", ""),
            symbol_fq_name=s.get("fq_name", ""),
            start_line=s.get("start_line", 0),
        ))
    added_section.body = "\n".join(added_lines) if added_lines else "No new symbols."
    doc.sections.append(added_section)

    # Removed
    removed_section = DocSection(heading="Removed")
    removed_symbols = [s for s in previous_symbols if s.get("fq_name", "") in removed_fqs]
    removed_lines = []
    for s in sorted(removed_symbols, key=lambda x: x.get("fq_name", ""))[:50]:
        removed_lines.append(f"- ~~`{s.get('fq_name', '')}`~~ ({s.get('kind', '')})")
    removed_section.body = "\n".join(removed_lines) if removed_lines else "No symbols removed."
    doc.sections.append(removed_section)

    # Modified
    mod_section = DocSection(heading="Modified")
    mod_lines = []
    for fq in sorted(modified_fqs)[:30]:
        old_sig = prev_sigs.get(fq, "")
        new_sig = cur_sigs.get(fq, "")
        mod_lines.append(f"- `{fq}`\n  - Before: `{old_sig}`\n  - After: `{new_sig}`")
    mod_section.body = "\n".join(mod_lines) if mod_lines else "No signature changes."
    doc.sections.append(mod_section)

    # Breaking
    breaking_section = DocSection(heading="Breaking Changes")
    if breaking:
        breaking_lines = [f"- ~~`{fq}`~~ (public symbol removed)" for fq in sorted(breaking)[:20]]
        breaking_section.body = (
            "\u26a0\ufe0f The following public symbols were removed:\n\n"
            + "\n".join(breaking_lines)
        )
    else:
        breaking_section.body = "No breaking changes detected."
    doc.sections.append(breaking_section)

    doc.metadata = {
        "previous_snapshot_id": previous_snapshot_id,
        "added_count": len(added_fqs),
        "removed_count": len(removed_fqs),
        "modified_count": len(modified_fqs),
        "breaking_count": len(breaking),
    }
    return doc


def generate_dependency_map(
    snapshot_id: str,
    symbols: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    modules: list[dict[str, Any]],
) -> GeneratedDocument:
    """Generate a dependency map document."""
    doc = GeneratedDocument(
        doc_type=DocType.DEPENDENCY_MAP,
        title="Dependency Map",
        snapshot_id=snapshot_id,
    )

    # Build internal dep graph
    sym_ns = {s.get("fq_name", ""): s.get("namespace", "") for s in symbols}
    ns_deps: dict[str, set[str]] = {}
    for e in edges:
        src_ns = sym_ns.get(e.get("source_fq_name", ""), "")
        tgt_ns = sym_ns.get(e.get("target_fq_name", ""), "")
        if src_ns and tgt_ns and src_ns != tgt_ns:
            ns_deps.setdefault(src_ns, set()).add(tgt_ns)

    # Circular deps
    circular: list[tuple[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for src, targets in ns_deps.items():
        for tgt in targets:
            if src in ns_deps.get(tgt, set()):
                a, b = (min(src, tgt), max(src, tgt))
                if (a, b) not in seen_pairs:
                    seen_pairs.add((a, b))
                    circular.append((a, b))

    # External deps
    known_ns = {m.get("name", "") for m in modules}
    external_targets: set[str] = set()
    for e in edges:
        tgt = e.get("target_fq_name", "")
        tgt_ns = tgt.split(".")[0] if "." in tgt else ""
        if tgt_ns and tgt_ns not in known_ns:
            external_targets.add(tgt_ns)

    # Overview
    overview = DocSection(heading="Dependency Overview")
    overview.body = (
        f"**{len(modules)}** internal modules with "
        f"**{sum(len(v) for v in ns_deps.values())}** internal dependency edges.\n\n"
        f"**{len(external_targets)}** external dependencies detected.\n"
        f"**{len(circular)}** circular dependencies."
    )
    doc.sections.append(overview)

    # External
    ext_section = DocSection(heading="External Dependencies")
    if external_targets:
        ext_section.body = "\n".join(f"- `{dep}`" for dep in sorted(external_targets)[:30])
    else:
        ext_section.body = "No external dependencies detected from call graph."
    doc.sections.append(ext_section)

    # Internal
    int_section = DocSection(heading="Internal Module Dependencies")
    int_lines = []
    for src in sorted(ns_deps.keys()):
        dep_targets: list[str] = sorted(ns_deps[src])
        deps_str = ", ".join(f"`{t}`" for t in dep_targets)
        int_lines.append(f"- **`{src}`** depends on: {deps_str}")
    int_section.body = "\n".join(int_lines) if int_lines else "No internal dependencies."
    doc.sections.append(int_section)

    # Circular
    circ_section = DocSection(heading="Circular Dependencies")
    if circular:
        circ_lines = [f"- `{a}` \u2194 `{b}`" for a, b in circular]
        circ_section.body = (
            "\u26a0\ufe0f Circular dependencies detected:\n\n"
            + "\n".join(circ_lines)
        )
    else:
        circ_section.body = "\u2705 No circular dependencies detected."
    doc.sections.append(circ_section)

    # Metrics
    metrics_section = DocSection(heading="Dependency Metrics")
    dependents: dict[str, int] = {}
    for targets in ns_deps.values():
        for t in targets:
            dependents[t] = dependents.get(t, 0) + 1
    dep_counts = sorted(ns_deps.items(), key=lambda x: len(x[1]), reverse=True)
    m_lines = ["| Module | Dependencies | Dependents |", "|--------|-------------|------------|"]
    for ns, deps in dep_counts[:15]:
        m_lines.append(f"| `{ns}` | {len(deps)} | {dependents.get(ns, 0)} |")
    metrics_section.body = "\n".join(m_lines)
    doc.sections.append(metrics_section)

    doc.metadata = {
        "internal_deps_count": sum(len(v) for v in ns_deps.values()),
        "external_deps_count": len(external_targets),
        "circular_count": len(circular),
    }
    return doc

"""
Mermaid diagram generators for documentation.

Converts code graph data (symbols, edges, modules) into Mermaid diagram syntax
that can be embedded directly in Markdown documentation.
"""

from __future__ import annotations

import enum
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any


class DiagramType(enum.StrEnum):
    """Supported Mermaid diagram types."""

    CLASS_DIAGRAM = "classDiagram"
    SEQUENCE = "sequenceDiagram"
    FLOWCHART = "flowchart"
    DEPENDENCY_GRAPH = "graph"
    ER_DIAGRAM = "erDiagram"


@dataclass
class DiagramConfig:
    """Configuration for diagram generation."""

    max_nodes: int = 25
    max_edges: int = 50
    collapse_threshold: int = 3  # modules with < N symbols get collapsed
    direction: str = "TD"  # TD (top-down), LR (left-right)
    show_edge_labels: bool = False


@dataclass
class MermaidDiagram:
    """A generated Mermaid diagram."""

    diagram_type: DiagramType
    title: str
    content: str
    node_count: int = 0
    edge_count: int = 0

    def to_markdown(self) -> str:
        """Render as a Markdown code block."""
        return f"```mermaid\n{self.content}\n```"


# ---------------------------------------------------------------------------
# Dependency Graph (module-level)
# ---------------------------------------------------------------------------


def generate_dependency_graph(
    modules: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    symbols: list[dict[str, Any]],
    config: DiagramConfig | None = None,
) -> MermaidDiagram:
    """Generate a module dependency graph (flowchart)."""
    cfg = config or DiagramConfig()

    # Build namespace lookup
    sym_ns: dict[str, str] = {
        s.get("fq_name", ""): s.get("namespace", "")
        for s in symbols
    }

    # Compute module-to-module edges
    ns_deps: dict[str, set[str]] = {}
    for e in edges:
        src_ns = sym_ns.get(e.get("source_fq_name", ""), "")
        tgt_ns = sym_ns.get(e.get("target_fq_name", ""), "")
        if src_ns and tgt_ns and src_ns != tgt_ns:
            ns_deps.setdefault(src_ns, set()).add(tgt_ns)

    # Filter to top modules by connectivity
    all_ns = set(ns_deps.keys())
    for targets in ns_deps.values():
        all_ns.update(targets)

    # Simplify: collapse small modules if too many nodes
    module_sizes = {m.get("name", ""): m.get("symbol_count", 0) for m in modules}
    if len(all_ns) > cfg.max_nodes:
        # Keep only modules above collapse threshold
        significant = {
            ns for ns in all_ns
            if module_sizes.get(ns, 0) >= cfg.collapse_threshold
        }
        if len(significant) < 3:
            significant = all_ns  # fallback
        all_ns = significant

    # Limit nodes
    if len(all_ns) > cfg.max_nodes:
        # Keep most-connected
        connectivity: Counter[str] = Counter()
        for src, targets in ns_deps.items():
            if src in all_ns:
                connectivity[src] += len(targets)
            for t in targets:
                if t in all_ns:
                    connectivity[t] += 1
        all_ns = {ns for ns, _ in connectivity.most_common(cfg.max_nodes)}

    # Build Mermaid
    lines = [f"graph {cfg.direction}"]
    node_ids: dict[str, str] = {}
    for i, ns in enumerate(sorted(all_ns)):
        node_id = f"N{i}"
        node_ids[ns] = node_id
        label = _short_name(ns)
        count = module_sizes.get(ns, 0)
        if count:
            lines.append(f"    {node_id}[\"{label} ({count})\"]")
        else:
            lines.append(f"    {node_id}[\"{label}\"]")

    edge_count = 0
    for src, targets in ns_deps.items():
        if src not in node_ids:
            continue
        for tgt in targets:
            if tgt not in node_ids:
                continue
            if edge_count >= cfg.max_edges:
                break
            lines.append(f"    {node_ids[src]} --> {node_ids[tgt]}")
            edge_count += 1

    return MermaidDiagram(
        diagram_type=DiagramType.DEPENDENCY_GRAPH,
        title="Module Dependencies",
        content="\n".join(lines),
        node_count=len(node_ids),
        edge_count=edge_count,
    )


# ---------------------------------------------------------------------------
# Class Diagram (for a module)
# ---------------------------------------------------------------------------

_TYPE_KINDS = {"class", "interface", "struct", "record", "enum"}


def generate_class_diagram(
    module_name: str,
    symbols: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    config: DiagramConfig | None = None,
) -> MermaidDiagram:
    """Generate a class diagram for a single module."""
    cfg = config or DiagramConfig()

    mod_symbols = [s for s in symbols if s.get("namespace") == module_name]
    types = [s for s in mod_symbols if s.get("kind") in _TYPE_KINDS]
    methods = [s for s in mod_symbols if s.get("kind") in ("method", "function")]

    # Limit types
    types = types[: cfg.max_nodes]

    lines = ["classDiagram"]

    # Classes
    type_fqs = {t.get("fq_name", "") for t in types}
    for t in types:
        fq = t.get("fq_name", "")
        name = _safe_class_name(t.get("name", fq))
        kind = t.get("kind", "class")

        if kind == "interface":
            lines.append(f"    class {name} {{")
            lines.append("        <<interface>>")
        elif kind == "enum":
            lines.append(f"    class {name} {{")
            lines.append("        <<enumeration>>")
        else:
            lines.append(f"    class {name} {{")

        # Add methods belonging to this type
        type_methods = [
            m for m in methods
            if m.get("fq_name", "").startswith(fq + ".")
        ]
        for m in type_methods[:8]:  # limit methods per class
            sig = m.get("name", "")
            visibility = "+" if "public" in m.get("modifiers", "") else "-"
            lines.append(f"        {visibility}{sig}()")
        lines.append("    }")

    # Inheritance/implementation edges
    edge_count = 0
    for e in edges:
        etype = e.get("edge_type", "")
        src = e.get("source_fq_name", "")
        tgt = e.get("target_fq_name", "")
        if src not in type_fqs or tgt not in type_fqs:
            continue

        src_name = _safe_class_name(_last_part(src))
        tgt_name = _safe_class_name(_last_part(tgt))

        if etype == "inherits":
            lines.append(f"    {tgt_name} <|-- {src_name}")
            edge_count += 1
        elif etype == "implements":
            lines.append(f"    {tgt_name} <|.. {src_name}")
            edge_count += 1
        elif etype == "calls" and edge_count < cfg.max_edges:
            lines.append(f"    {src_name} --> {tgt_name}")
            edge_count += 1

    return MermaidDiagram(
        diagram_type=DiagramType.CLASS_DIAGRAM,
        title=f"Class Diagram: {module_name}",
        content="\n".join(lines),
        node_count=len(types),
        edge_count=edge_count,
    )


# ---------------------------------------------------------------------------
# Sequence Diagram (for a flow)
# ---------------------------------------------------------------------------


def generate_sequence_diagram(
    entry_fq_name: str,
    symbols: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    config: DiagramConfig | None = None,
) -> MermaidDiagram:
    """Generate a sequence diagram for a call flow starting from entry point."""
    cfg = config or DiagramConfig()

    # Build call graph from entry point (BFS)
    call_edges = [
        e for e in edges if e.get("edge_type") == "calls"
    ]
    adj: dict[str, list[str]] = defaultdict(list)
    for e in call_edges:
        adj[e["source_fq_name"]].append(e["target_fq_name"])

    # BFS to collect sequence
    visited: set[str] = set()
    sequence: list[tuple[str, str]] = []
    queue = [entry_fq_name]
    visited.add(entry_fq_name)

    while queue and len(sequence) < cfg.max_edges:
        current = queue.pop(0)
        for target in adj.get(current, []):
            if len(sequence) >= cfg.max_edges:
                break
            sequence.append((current, target))
            if target not in visited:
                visited.add(target)
                queue.append(target)

    # Map symbols to participants (by namespace)
    sym_ns: dict[str, str] = {
        s.get("fq_name", ""): s.get("namespace", "") or _last_part(s.get("fq_name", ""))
        for s in symbols
    }

    participants: set[str] = set()
    for src, tgt in sequence:
        participants.add(sym_ns.get(src, _last_part(src)))
        participants.add(sym_ns.get(tgt, _last_part(tgt)))

    # Limit participants
    participant_list = sorted(participants)[: cfg.max_nodes]
    participant_set = set(participant_list)

    lines = ["sequenceDiagram"]
    for p in participant_list:
        lines.append(f"    participant {_safe_participant(p)}")

    edge_count = 0
    for src, tgt in sequence:
        src_p = sym_ns.get(src, _last_part(src))
        tgt_p = sym_ns.get(tgt, _last_part(tgt))
        if src_p not in participant_set or tgt_p not in participant_set:
            continue
        if src_p == tgt_p:
            continue  # skip self-calls for clarity
        call_name = _last_part(tgt)
        lines.append(
            f"    {_safe_participant(src_p)}->>+{_safe_participant(tgt_p)}: {call_name}()"
        )
        edge_count += 1

    return MermaidDiagram(
        diagram_type=DiagramType.SEQUENCE,
        title=f"Sequence: {_last_part(entry_fq_name)}",
        content="\n".join(lines),
        node_count=len(participant_list),
        edge_count=edge_count,
    )


# ---------------------------------------------------------------------------
# Flowchart (for a single function's call tree)
# ---------------------------------------------------------------------------


def generate_flowchart(
    entry_fq_name: str,
    edges: list[dict[str, Any]],
    config: DiagramConfig | None = None,
) -> MermaidDiagram:
    """Generate a flowchart showing call tree from an entry point."""
    cfg = config or DiagramConfig()

    call_edges = [e for e in edges if e.get("edge_type") == "calls"]
    adj: dict[str, list[str]] = defaultdict(list)
    for e in call_edges:
        adj[e["source_fq_name"]].append(e["target_fq_name"])

    # BFS
    visited: set[str] = set()
    flow_edges: list[tuple[str, str]] = []
    queue = [entry_fq_name]
    visited.add(entry_fq_name)

    while queue and len(flow_edges) < cfg.max_edges:
        current = queue.pop(0)
        for target in adj.get(current, []):
            if len(flow_edges) >= cfg.max_edges:
                break
            flow_edges.append((current, target))
            if target not in visited and len(visited) < cfg.max_nodes:
                visited.add(target)
                queue.append(target)

    # Build node IDs
    all_nodes = set()
    for src, tgt in flow_edges:
        all_nodes.add(src)
        all_nodes.add(tgt)

    node_ids: dict[str, str] = {}
    for i, n in enumerate(sorted(all_nodes)):
        node_ids[n] = f"F{i}"

    lines = [f"flowchart {cfg.direction}"]
    for n, nid in sorted(node_ids.items(), key=lambda x: x[1]):
        label = _last_part(n)
        lines.append(f"    {nid}[\"{label}\"]")

    for src, tgt in flow_edges:
        if src in node_ids and tgt in node_ids:
            lines.append(f"    {node_ids[src]} --> {node_ids[tgt]}")

    return MermaidDiagram(
        diagram_type=DiagramType.FLOWCHART,
        title=f"Call Flow: {_last_part(entry_fq_name)}",
        content="\n".join(lines),
        node_count=len(node_ids),
        edge_count=len(flow_edges),
    )


# ---------------------------------------------------------------------------
# ER Diagram (from classes with relationships)
# ---------------------------------------------------------------------------


def generate_er_diagram(
    symbols: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    config: DiagramConfig | None = None,
) -> MermaidDiagram:
    """Generate an ER diagram from class relationships."""
    cfg = config or DiagramConfig()

    types = [s for s in symbols if s.get("kind") in _TYPE_KINDS]
    types = types[: cfg.max_nodes]
    type_fqs = {t.get("fq_name", "") for t in types}

    lines = ["erDiagram"]

    # Entities
    for t in types:
        name = _safe_class_name(t.get("name", ""))
        lines.append(f"    {name} {{")
        lines.append("        string name")
        lines.append("    }")

    # Relationships
    edge_count = 0
    seen: set[tuple[str, str]] = set()
    for e in edges:
        src = e.get("source_fq_name", "")
        tgt = e.get("target_fq_name", "")
        if src not in type_fqs or tgt not in type_fqs:
            continue
        if src == tgt:
            continue
        pair = (min(src, tgt), max(src, tgt))
        if pair in seen:
            continue
        seen.add(pair)

        src_name = _safe_class_name(_last_part(src))
        tgt_name = _safe_class_name(_last_part(tgt))
        etype = e.get("edge_type", "calls")

        if etype == "inherits":
            lines.append(f"    {tgt_name} ||--o{{ {src_name} : inherits")
        elif etype == "implements":
            lines.append(f"    {tgt_name} ||--o{{ {src_name} : implements")
        else:
            lines.append(f"    {src_name} }}o--o{{ {tgt_name} : uses")
        edge_count += 1

        if edge_count >= cfg.max_edges:
            break

    return MermaidDiagram(
        diagram_type=DiagramType.ER_DIAGRAM,
        title="Entity Relationships",
        content="\n".join(lines),
        node_count=len(types),
        edge_count=edge_count,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _short_name(namespace: str) -> str:
    """Shorten a namespace for display."""
    parts = namespace.split(".")
    if len(parts) <= 2:
        return namespace
    return ".".join(parts[-2:])


def _last_part(fq_name: str) -> str:
    """Get the last part of a dotted name."""
    return fq_name.rsplit(".", 1)[-1] if "." in fq_name else fq_name


def _safe_class_name(name: str) -> str:
    """Make a name safe for Mermaid class diagrams."""
    return name.replace(" ", "_").replace("-", "_").replace("<", "").replace(">", "")


def _safe_participant(name: str) -> str:
    """Make a name safe for Mermaid sequence diagrams."""
    safe = name.replace(".", "_").replace(" ", "_").replace("-", "_")
    return safe.replace("<", "").replace(">", "")

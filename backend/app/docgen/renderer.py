"""
Markdown renderer.

Converts ``GeneratedDocument`` objects into Markdown strings
with citation footnotes and symbol links.
"""

from __future__ import annotations

from app.docgen.models import Citation, DocSection, GeneratedDocument


def render_markdown(doc: GeneratedDocument) -> str:
    """Render a complete document to Markdown."""
    lines: list[str] = []
    lines.append(f"# {doc.title}")
    lines.append("")
    lines.append(f"> Auto-generated from snapshot `{doc.snapshot_id}`")
    if doc.scope_id:
        lines.append(f"> Scope: `{doc.scope_id}`")
    lines.append("")

    all_citations: list[Citation] = []

    for section in doc.sections:
        _render_section(section, lines, all_citations, level=2)

    # Citation appendix
    if all_citations:
        lines.append("---")
        lines.append("")
        lines.append("## References")
        lines.append("")
        seen: set[str] = set()
        for i, cite in enumerate(all_citations, 1):
            key = f"{cite.file_path}:{cite.symbol_fq_name}:{cite.start_line}"
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"{i}. {cite.to_link()}")
        lines.append("")

    return "\n".join(lines)


def _render_section(
    section: DocSection,
    lines: list[str],
    all_citations: list[Citation],
    level: int,
) -> None:
    """Render a section and its subsections."""
    prefix = "#" * level
    lines.append(f"{prefix} {section.heading}")
    lines.append("")

    if section.body:
        lines.append(section.body)
        lines.append("")

    all_citations.extend(section.citations)

    for sub in section.subsections:
        _render_section(sub, lines, all_citations, level=level + 1)

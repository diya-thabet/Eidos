"""
Confluence wiki markup renderer.

Converts generated documents into Confluence Storage Format (XHTML).
"""

from __future__ import annotations

import html

from app.docgen.models import DocSection, GeneratedDocument


def render_confluence(doc: GeneratedDocument) -> str:
    """Render a GeneratedDocument to Confluence storage format."""
    parts: list[str] = []

    parts.append(f"<h1>{html.escape(doc.title)}</h1>")
    parts.append(
        f'<ac:structured-macro ac:name="info"><ac:rich-text-body>'
        f"<p>Auto-generated from snapshot <code>{html.escape(doc.snapshot_id)}</code></p>"
        f"</ac:rich-text-body></ac:structured-macro>"
    )

    for section in doc.sections:
        _render_section(section, parts, level=2)

    return "\n".join(parts)


def _render_section(section: DocSection, parts: list[str], level: int) -> None:
    """Render a section to Confluence format."""
    tag = f"h{min(level, 6)}"
    parts.append(f"<{tag}>{html.escape(section.heading)}</{tag}>")

    if section.body:
        # Simple conversion: wrap paragraphs
        for line in section.body.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("- ") or line.startswith("* "):
                parts.append(f"<li>{html.escape(line[2:])}</li>")
            elif line.startswith("|"):
                parts.append(f"<p>{html.escape(line)}</p>")
            else:
                parts.append(f"<p>{html.escape(line)}</p>")

    for sub in section.subsections:
        _render_section(sub, parts, level=level + 1)

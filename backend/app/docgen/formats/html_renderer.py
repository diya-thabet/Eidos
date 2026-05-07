"""
HTML renderer for generated documentation.

Produces standalone HTML with embedded CSS, syntax highlighting,
table of contents, and Mermaid diagram support.
"""

from __future__ import annotations

import html

from app.docgen.models import Citation, DocSection, GeneratedDocument

_CSS = """
<style>
:root { --bg: #fff; --fg: #1a1a2e; --accent: #0f3460; --border: #e0e0e0; --code-bg: #f5f5f5; }
@media (prefers-color-scheme: dark) {
    :root { --bg: #1a1a2e; --fg: #e0e0e0; --accent: #4fc3f7; --border: #333; --code-bg: #2d2d44; }
}
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       max-width: 900px; margin: 0 auto; padding: 2rem; background: var(--bg); color: var(--fg);
       line-height: 1.6; }
h1 { border-bottom: 2px solid var(--accent); padding-bottom: 0.5rem; }
h2 { border-bottom: 1px solid var(--border); padding-bottom: 0.3rem; margin-top: 2rem; }
h3, h4 { margin-top: 1.5rem; }
code { background: var(--code-bg); padding: 0.2em 0.4em; border-radius: 3px; font-size: 0.9em; }
pre { background: var(--code-bg); padding: 1rem; border-radius: 6px; overflow-x: auto; }
pre code { background: none; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
th, td { border: 1px solid var(--border); padding: 0.5rem 0.75rem; text-align: left; }
th { background: var(--code-bg); font-weight: 600; }
blockquote { border-left: 4px solid var(--accent); margin: 1rem 0; padding: 0.5rem 1rem;
             background: var(--code-bg); }
a { color: var(--accent); }
.toc { background: var(--code-bg); padding: 1rem 1.5rem; border-radius: 6px; margin-bottom: 2rem; }
.toc ul { list-style: none; padding-left: 1rem; }
.toc > ul { padding-left: 0; }
.citation { font-size: 0.85em; color: #666; }
@media print { body { max-width: 100%; } .toc { display: none; } }
</style>
"""

_MERMAID_SCRIPT = """
<script type="module">
import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
mermaid.initialize({ startOnLoad: true, theme: 'neutral' });
</script>
"""


def render_html(
    doc: GeneratedDocument,
    theme: str = "default",
    include_toc: bool = True,
) -> str:
    """Render a GeneratedDocument to standalone HTML."""
    parts: list[str] = []
    parts.append("<!DOCTYPE html>")
    parts.append("<html lang='en'><head><meta charset='utf-8'>")
    parts.append(f"<title>{html.escape(doc.title)}</title>")
    parts.append(_CSS)
    parts.append("</head><body>")
    parts.append(_MERMAID_SCRIPT)

    # Title
    parts.append(f"<h1>{html.escape(doc.title)}</h1>")
    parts.append(
        f"<blockquote>Auto-generated from snapshot "
        f"<code>{html.escape(doc.snapshot_id)}</code></blockquote>"
    )

    # Table of contents
    if include_toc and doc.sections:
        parts.append('<nav class="toc"><strong>Contents</strong><ul>')
        for section in doc.sections:
            anchor = _make_anchor(section.heading)
            parts.append(
                f'<li><a href="#{anchor}">{html.escape(section.heading)}</a></li>'
            )
        parts.append("</ul></nav>")

    # Sections
    all_citations: list[Citation] = []
    for section in doc.sections:
        _render_html_section(section, parts, all_citations, level=2)

    # Citations
    if all_citations:
        parts.append("<hr>")
        parts.append("<h2>References</h2><ol class='citation'>")
        seen: set[str] = set()
        for cite in all_citations:
            key = f"{cite.file_path}:{cite.symbol_fq_name}:{cite.start_line}"
            if key in seen:
                continue
            seen.add(key)
            parts.append(f"<li><code>{html.escape(cite.to_link())}</code></li>")
        parts.append("</ol>")

    parts.append("</body></html>")
    return "\n".join(parts)


def _render_html_section(
    section: DocSection,
    parts: list[str],
    all_citations: list[Citation],
    level: int,
) -> None:
    """Render a section to HTML."""
    tag = f"h{min(level, 6)}"
    anchor = _make_anchor(section.heading)
    parts.append(f'<{tag} id="{anchor}">{html.escape(section.heading)}</{tag}>')

    if section.body:
        # Convert markdown-like content to HTML
        body_html = _markdown_to_html(section.body)
        parts.append(f"<div>{body_html}</div>")

    all_citations.extend(section.citations)

    for sub in section.subsections:
        _render_html_section(sub, parts, all_citations, level=level + 1)


def _markdown_to_html(text: str) -> str:
    """Simple markdown-to-HTML conversion (no external deps)."""
    lines = text.split("\n")
    result: list[str] = []
    in_code_block = False
    in_table = False
    in_list = False

    for line in lines:
        # Code blocks
        if line.startswith("```"):
            if in_code_block:
                result.append("</code></pre>")
                in_code_block = False
            else:
                lang = line[3:].strip()
                if lang == "mermaid":
                    result.append('<pre class="mermaid">')
                else:
                    result.append("<pre><code>")
                in_code_block = True
            continue

        if in_code_block:
            if line.startswith('<pre class="mermaid">'):
                result.append(line)
            else:
                result.append(html.escape(line))
            continue

        # Tables
        if "|" in line and line.strip().startswith("|"):
            if not in_table:
                result.append("<table>")
                in_table = True
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(set(c) <= {"-", ":"} for c in cells):
                continue  # separator row
            row = "".join(f"<td>{html.escape(c)}</td>" for c in cells)
            result.append(f"<tr>{row}</tr>")
            continue
        elif in_table:
            result.append("</table>")
            in_table = False

        # Lists
        if line.startswith("- ") or line.startswith("* "):
            if not in_list:
                result.append("<ul>")
                in_list = True
            content = line[2:]
            result.append(f"<li>{_inline_format(content)}</li>")
            continue
        elif in_list and not line.strip():
            result.append("</ul>")
            in_list = False

        # Headers (shouldn't be common inside sections)
        if line.startswith("### "):
            result.append(f"<h5>{html.escape(line[4:])}</h5>")
        elif line.startswith("## "):
            result.append(f"<h4>{html.escape(line[3:])}</h4>")
        elif line.strip():
            result.append(f"<p>{_inline_format(line)}</p>")

    if in_table:
        result.append("</table>")
    if in_list:
        result.append("</ul>")
    if in_code_block:
        result.append("</code></pre>")

    return "\n".join(result)


def _inline_format(text: str) -> str:
    """Apply inline formatting (bold, code, links)."""
    import re

    text = html.escape(text)
    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # Inline code
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text


def _make_anchor(heading: str) -> str:
    """Create an HTML anchor from a heading."""
    return heading.lower().replace(" ", "-").replace("&", "").replace("/", "")

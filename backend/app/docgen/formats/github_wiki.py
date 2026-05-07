"""
GitHub Wiki format exporter.

Converts generated documents into GitHub Wiki-compatible Markdown
with a _Sidebar.md for navigation.
"""

from __future__ import annotations

from app.docgen.models import DocType, GeneratedDocument
from app.docgen.renderer import render_markdown


def render_github_wiki(doc: GeneratedDocument) -> str:
    """Render a document as GitHub Wiki Markdown (same as regular MD)."""
    return render_markdown(doc)


def build_wiki_structure(
    docs: list[GeneratedDocument],
) -> dict[str, str]:
    """Build GitHub Wiki file structure.

    Returns dict mapping filenames to content.
    """
    files: dict[str, str] = {}

    for doc in docs:
        filename = _wiki_filename(doc)
        files[filename] = render_github_wiki(doc)

    # Generate _Sidebar.md
    sidebar_lines = ["## Documentation", ""]
    for doc in sorted(docs, key=lambda d: _sort_key(d)):
        filename = _wiki_filename(doc).replace(".md", "")
        sidebar_lines.append(f"- [[{doc.title}|{filename}]]")

    files["_Sidebar.md"] = "\n".join(sidebar_lines) + "\n"

    # Home page
    readme_docs = [d for d in docs if d.doc_type == DocType.README]
    if readme_docs:
        files["Home.md"] = render_github_wiki(readme_docs[0])

    return files


def _wiki_filename(doc: GeneratedDocument) -> str:
    """Generate a wiki-safe filename."""
    if doc.scope_id:
        name = f"{doc.doc_type}-{doc.scope_id}"
    else:
        name = doc.doc_type
    return name.replace(".", "-").replace("/", "-").replace(" ", "-") + ".md"


def _sort_key(doc: GeneratedDocument) -> tuple[int, str]:
    """Sort docs for sidebar."""
    order = {
        DocType.README: 0,
        DocType.ARCHITECTURE: 1,
        DocType.ONBOARDING: 2,
        DocType.RUNBOOK: 3,
        DocType.DEPENDENCY_MAP: 4,
        DocType.CHANGELOG: 5,
    }
    return (order.get(doc.doc_type, 10), doc.title)

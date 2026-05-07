# ruff: noqa: E501
"""
Tests for DocGen Phase 3: Multi-Format Output.

Tests HTML renderer, Docusaurus exporter, Confluence renderer,
GitHub Wiki exporter, and the export API endpoint.
"""

from __future__ import annotations

from app.docgen.formats.confluence import render_confluence
from app.docgen.formats.docusaurus import (
    build_docusaurus_structure,
    generate_sidebars,
    render_docusaurus,
)
from app.docgen.formats.github_wiki import (
    build_wiki_structure,
    render_github_wiki,
)
from app.docgen.formats.html_renderer import render_html
from app.docgen.models import DocSection, DocType, GeneratedDocument

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_doc(
    doc_type: DocType = DocType.README,
    title: str = "Test Doc",
    snapshot_id: str = "snap1",
    scope_id: str = "",
    body: str = "Hello **world**\n\n- item1\n- item2",
) -> GeneratedDocument:
    return GeneratedDocument(
        doc_type=doc_type,
        title=title,
        snapshot_id=snapshot_id,
        scope_id=scope_id,
        sections=[
            DocSection(heading="Overview", body=body),
            DocSection(heading="Details", body="Some details here."),
        ],
    )


def _make_docs_set() -> list[GeneratedDocument]:
    return [
        _make_doc(DocType.README, "README"),
        _make_doc(DocType.ARCHITECTURE, "Architecture"),
        _make_doc(DocType.MODULE, "Module: auth", scope_id="app.auth"),
        _make_doc(DocType.API_REFERENCE, "API: auth", scope_id="app.auth"),
        _make_doc(DocType.FLOW, "Flow: login", scope_id="login"),
    ]


# ---------------------------------------------------------------------------
# HTML Renderer tests
# ---------------------------------------------------------------------------


class TestHTMLRenderer:

    def test_produces_valid_html(self):
        doc = _make_doc()
        html = render_html(doc)
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html

    def test_includes_title(self):
        doc = _make_doc(title="My Project")
        html = render_html(doc)
        assert "<h1>My Project</h1>" in html
        assert "<title>My Project</title>" in html

    def test_includes_toc(self):
        doc = _make_doc()
        html = render_html(doc)
        assert 'class="toc"' in html
        assert "Overview" in html

    def test_toc_disabled(self):
        doc = _make_doc()
        html = render_html(doc, include_toc=False)
        assert 'class="toc"' not in html

    def test_includes_css(self):
        doc = _make_doc()
        html = render_html(doc)
        assert "<style>" in html

    def test_includes_mermaid_script(self):
        doc = _make_doc()
        html = render_html(doc)
        assert "mermaid" in html

    def test_sections_rendered(self):
        doc = _make_doc()
        html = render_html(doc)
        assert "Overview" in html
        assert "Details" in html

    def test_body_content(self):
        doc = _make_doc()
        html = render_html(doc)
        assert "world" in html

    def test_snapshot_shown(self):
        doc = _make_doc(snapshot_id="abc123")
        html = render_html(doc)
        assert "abc123" in html

    def test_escapes_html(self):
        doc = _make_doc(title="<script>alert('xss')</script>")
        html = render_html(doc)
        assert "<script>alert" not in html
        assert "&lt;script&gt;" in html


# ---------------------------------------------------------------------------
# Docusaurus tests
# ---------------------------------------------------------------------------


class TestDocusaurus:

    def test_renders_frontmatter(self):
        doc = _make_doc(DocType.ARCHITECTURE, "Architecture")
        result = render_docusaurus(doc)
        assert "---" in result
        assert "id: architecture" in result
        assert "title: Architecture" in result
        assert "sidebar_position:" in result

    def test_strips_h1_title(self):
        doc = _make_doc(DocType.README, "README")
        result = render_docusaurus(doc)
        assert "# README" not in result  # H1 stripped (title in frontmatter)

    def test_includes_tags(self):
        doc = _make_doc(DocType.MODULE, "Auth Module", scope_id="app.auth")
        result = render_docusaurus(doc)
        assert "auto-generated" in result
        assert "app.auth" in result

    def test_generate_sidebars(self):
        docs = _make_docs_set()
        sidebars = generate_sidebars(docs)
        assert "module.exports" in sidebars
        assert "docs" in sidebars

    def test_build_structure(self):
        docs = _make_docs_set()
        files = build_docusaurus_structure(docs)
        assert "sidebars.js" in files
        assert any("docs/" in k for k in files)
        assert len(files) >= 5  # 5 docs + sidebars

    def test_module_in_category(self):
        docs = _make_docs_set()
        files = build_docusaurus_structure(docs)
        module_files = [k for k in files if "modules/" in k]
        assert len(module_files) >= 1

    def test_api_in_category(self):
        docs = _make_docs_set()
        files = build_docusaurus_structure(docs)
        api_files = [k for k in files if "api/" in k]
        assert len(api_files) >= 1


# ---------------------------------------------------------------------------
# Confluence tests
# ---------------------------------------------------------------------------


class TestConfluence:

    def test_produces_xhtml(self):
        doc = _make_doc()
        result = render_confluence(doc)
        assert "<h1>" in result
        assert "</h1>" in result

    def test_title_rendered(self):
        doc = _make_doc(title="My Doc")
        result = render_confluence(doc)
        assert "My Doc" in result

    def test_info_macro(self):
        doc = _make_doc(snapshot_id="snap123")
        result = render_confluence(doc)
        assert "ac:structured-macro" in result
        assert "snap123" in result

    def test_sections_rendered(self):
        doc = _make_doc()
        result = render_confluence(doc)
        assert "<h2>" in result
        assert "Overview" in result


# ---------------------------------------------------------------------------
# GitHub Wiki tests
# ---------------------------------------------------------------------------


class TestGitHubWiki:

    def test_renders_markdown(self):
        doc = _make_doc()
        result = render_github_wiki(doc)
        assert "# Test Doc" in result

    def test_build_structure(self):
        docs = _make_docs_set()
        files = build_wiki_structure(docs)
        assert "_Sidebar.md" in files
        assert "Home.md" in files

    def test_sidebar_has_links(self):
        docs = _make_docs_set()
        files = build_wiki_structure(docs)
        sidebar = files["_Sidebar.md"]
        assert "[[" in sidebar  # wiki-style links

    def test_filenames_safe(self):
        docs = _make_docs_set()
        files = build_wiki_structure(docs)
        for name in files:
            assert " " not in name
            assert "/" not in name.replace("_Sidebar.md", "x").replace("Home.md", "x")


# ---------------------------------------------------------------------------
# Integration: format selection
# ---------------------------------------------------------------------------


class TestFormatSelection:

    def test_all_formats_importable(self):
        from app.docgen.formats.confluence import render_confluence
        from app.docgen.formats.docusaurus import render_docusaurus
        from app.docgen.formats.github_wiki import render_github_wiki
        from app.docgen.formats.html_renderer import render_html
        assert all([render_html, render_docusaurus, render_confluence, render_github_wiki])

    def test_markdown_still_works(self):
        from app.docgen.renderer import render_markdown
        doc = _make_doc()
        md = render_markdown(doc)
        assert "# Test Doc" in md

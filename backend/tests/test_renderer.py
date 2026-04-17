"""
Tests for the Markdown renderer.

Covers: document rendering, section hierarchy, citations appendix,
symbol links, and edge cases.
"""

from app.docgen.models import Citation, DocSection, DocType, GeneratedDocument
from app.docgen.renderer import render_markdown


def _make_doc(sections=None, scope_id=""):
    return GeneratedDocument(
        doc_type=DocType.README,
        title="Test Doc",
        snapshot_id="snap-001",
        scope_id=scope_id,
        sections=sections or [],
    )


class TestRenderMarkdown:
    def test_renders_title(self):
        md = render_markdown(_make_doc())
        assert "# Test Doc" in md

    def test_renders_snapshot_id(self):
        md = render_markdown(_make_doc())
        assert "snap-001" in md

    def test_renders_scope_id(self):
        md = render_markdown(_make_doc(scope_id="MyApp"))
        assert "MyApp" in md

    def test_renders_section_heading(self):
        doc = _make_doc(sections=[DocSection(heading="Overview", body="Hello world.")])
        md = render_markdown(doc)
        assert "## Overview" in md
        assert "Hello world." in md

    def test_renders_multiple_sections(self):
        doc = _make_doc(
            sections=[
                DocSection(heading="A", body="Content A"),
                DocSection(heading="B", body="Content B"),
            ]
        )
        md = render_markdown(doc)
        assert "## A" in md
        assert "## B" in md
        assert "Content A" in md
        assert "Content B" in md

    def test_renders_subsections(self):
        doc = _make_doc(
            sections=[
                DocSection(
                    heading="Parent",
                    body="Parent body",
                    subsections=[
                        DocSection(heading="Child", body="Child body"),
                    ],
                ),
            ]
        )
        md = render_markdown(doc)
        assert "## Parent" in md
        assert "### Child" in md

    def test_renders_citations_appendix(self):
        doc = _make_doc(
            sections=[
                DocSection(
                    heading="A",
                    body="Some body",
                    citations=[
                        Citation(
                            file_path="Foo.cs",
                            symbol_fq_name="MyApp.Foo",
                            start_line=5,
                            end_line=10,
                        ),
                    ],
                ),
            ]
        )
        md = render_markdown(doc)
        assert "## References" in md
        assert "Foo.cs" in md
        assert "MyApp.Foo" in md

    def test_deduplicates_citations(self):
        cite = Citation(
            file_path="Foo.cs",
            symbol_fq_name="MyApp.Foo",
            start_line=5,
        )
        doc = _make_doc(
            sections=[
                DocSection(heading="A", citations=[cite, cite, cite]),
            ]
        )
        md = render_markdown(doc)
        # Should only appear once in references
        assert md.count("`MyApp.Foo`") == 1

    def test_no_citations_no_references(self):
        doc = _make_doc(sections=[DocSection(heading="A", body="B")])
        md = render_markdown(doc)
        assert "## References" not in md

    def test_citation_to_link_with_lines(self):
        c = Citation(
            file_path="Bar.cs",
            symbol_fq_name="X.Y",
            start_line=10,
            end_line=20,
        )
        link = c.to_link()
        assert "Bar.cs#L10-L20" in link
        assert "`X.Y`" in link

    def test_citation_to_link_no_symbol(self):
        c = Citation(file_path="Bar.cs", start_line=5)
        link = c.to_link()
        assert "Bar.cs#L5" in link
        assert "[Bar.cs" in link

    def test_citation_to_link_no_lines(self):
        c = Citation(file_path="Bar.cs", symbol_fq_name="X")
        link = c.to_link()
        assert "Bar.cs" in link
        assert "`X`" in link

    def test_empty_doc(self):
        md = render_markdown(_make_doc())
        assert "# Test Doc" in md

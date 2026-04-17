"""
Tests for the document templates.

Covers: all document types have templates, section keys are valid.
"""

from app.docgen.models import DocType
from app.docgen.templates import TEMPLATE_SECTIONS, get_template_sections


class TestTemplates:
    def test_all_doc_types_have_templates(self):
        for dt in DocType:
            sections = get_template_sections(dt)
            assert len(sections) > 0, f"No template for {dt.value}"

    def test_readme_sections(self):
        sections = get_template_sections(DocType.README)
        keys = [k for k, _ in sections]
        assert "overview" in keys
        assert "modules" in keys
        assert "entry_points" in keys

    def test_architecture_sections(self):
        sections = get_template_sections(DocType.ARCHITECTURE)
        keys = [k for k, _ in sections]
        assert "overview" in keys
        assert "modules" in keys
        assert "hotspots" in keys

    def test_module_sections(self):
        sections = get_template_sections(DocType.MODULE)
        keys = [k for k, _ in sections]
        assert "overview" in keys
        assert "files" in keys
        assert "classes" in keys
        assert "public_api" in keys

    def test_flow_sections(self):
        sections = get_template_sections(DocType.FLOW)
        keys = [k for k, _ in sections]
        assert "overview" in keys
        assert "flow_steps" in keys
        assert "side_effects" in keys

    def test_runbook_sections(self):
        sections = get_template_sections(DocType.RUNBOOK)
        keys = [k for k, _ in sections]
        assert "overview" in keys
        assert "quick_start" in keys
        assert "known_risks" in keys

    def test_sections_are_tuples(self):
        for dt in DocType:
            for item in get_template_sections(dt):
                assert len(item) == 2
                assert isinstance(item[0], str)
                assert isinstance(item[1], str)

    def test_unknown_type_returns_empty(self):
        # get_template_sections with invalid key returns empty
        result = TEMPLATE_SECTIONS.get("nonexistent", [])
        assert result == []

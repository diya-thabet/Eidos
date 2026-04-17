"""
Tests for the document generator.

Covers: README, architecture, module, flow, runbook generation,
citation inclusion, edge cases, and empty data handling.
"""

from app.docgen.generator import (
    generate_architecture,
    generate_flow_doc,
    generate_module_doc,
    generate_readme,
    generate_runbook,
)
from app.docgen.models import DocType


def _symbols():
    return [
        {
            "fq_name": "MyApp.UserService",
            "kind": "class",
            "name": "UserService",
            "file_path": "UserService.cs",
            "start_line": 1,
            "end_line": 50,
            "namespace": "MyApp",
            "parent_fq_name": None,
            "signature": "public class UserService",
            "modifiers": "public",
            "return_type": "",
        },
        {
            "fq_name": "MyApp.UserService.GetById",
            "kind": "method",
            "name": "GetById",
            "file_path": "UserService.cs",
            "start_line": 10,
            "end_line": 20,
            "namespace": "MyApp",
            "parent_fq_name": "MyApp.UserService",
            "signature": "public User GetById(int id)",
            "modifiers": "public",
            "return_type": "User",
        },
        {
            "fq_name": "MyApp.UserService.Delete",
            "kind": "method",
            "name": "Delete",
            "file_path": "UserService.cs",
            "start_line": 30,
            "end_line": 40,
            "namespace": "MyApp",
            "parent_fq_name": "MyApp.UserService",
            "signature": "public void Delete(int id)",
            "modifiers": "public",
            "return_type": "void",
        },
        {
            "fq_name": "MyApp.Controllers.UserController",
            "kind": "class",
            "name": "UserController",
            "file_path": "UserController.cs",
            "start_line": 1,
            "end_line": 30,
            "namespace": "MyApp.Controllers",
            "parent_fq_name": None,
            "signature": "public class UserController",
            "modifiers": "public",
            "return_type": "",
        },
        {
            "fq_name": "MyApp.Controllers.UserController.Get",
            "kind": "method",
            "name": "Get",
            "file_path": "UserController.cs",
            "start_line": 10,
            "end_line": 18,
            "namespace": "MyApp.Controllers",
            "parent_fq_name": "MyApp.Controllers.UserController",
            "signature": "public IActionResult Get(int id)",
            "modifiers": "public",
            "return_type": "IActionResult",
        },
    ]


def _edges():
    return [
        {
            "source_fq_name": "MyApp.Controllers.UserController.Get",
            "target_fq_name": "MyApp.UserService.GetById",
            "edge_type": "calls",
            "file_path": "UserController.cs",
            "line": 12,
        },
        {
            "source_fq_name": "MyApp.UserService.Delete",
            "target_fq_name": "MyApp.UserService.GetById",
            "edge_type": "calls",
            "file_path": "UserService.cs",
            "line": 35,
        },
    ]


def _modules():
    return [
        {
            "name": "MyApp",
            "symbol_count": 3,
            "file_count": 1,
            "files": ["UserService.cs"],
            "dependencies": ["MyApp.Controllers"],
        },
        {
            "name": "MyApp.Controllers",
            "symbol_count": 2,
            "file_count": 1,
            "files": ["UserController.cs"],
            "dependencies": ["MyApp"],
        },
    ]


def _summaries():
    return [
        {
            "scope_type": "module",
            "scope_id": "MyApp",
            "summary": {"purpose": "Core domain logic."},
        },
    ]


def _entry_points():
    return [
        {
            "symbol_fq_name": "MyApp.Controllers.UserController.Get",
            "kind": "controller_action",
            "file_path": "UserController.cs",
            "line": 10,
            "route": "GET /users/{id}",
        },
    ]


def _metrics():
    return [
        {
            "fq_name": "MyApp.UserService.GetById",
            "kind": "method",
            "lines_of_code": 10,
            "fan_in": 2,
            "fan_out": 0,
        },
    ]


class TestGenerateReadme:
    def test_returns_readme_doc(self):
        doc = generate_readme(
            "s1",
            _symbols(),
            _edges(),
            _modules(),
            _summaries(),
            _entry_points(),
            _metrics(),
        )
        assert doc.doc_type == DocType.README
        assert doc.title == "README"
        assert doc.snapshot_id == "s1"

    def test_has_all_sections(self):
        doc = generate_readme(
            "s1",
            _symbols(),
            _edges(),
            _modules(),
            _summaries(),
            _entry_points(),
            _metrics(),
        )
        headings = [s.heading for s in doc.sections]
        assert "Overview" in headings
        assert "Modules" in headings
        assert "Entry Points" in headings

    def test_overview_contains_counts(self):
        doc = generate_readme(
            "s1",
            _symbols(),
            _edges(),
            _modules(),
            _summaries(),
            _entry_points(),
            _metrics(),
        )
        overview = doc.sections[0]
        assert "5 symbols" in overview.body
        assert "2 relationships" in overview.body
        assert "2 modules" in overview.body

    def test_modules_section_lists_modules(self):
        doc = generate_readme(
            "s1",
            _symbols(),
            _edges(),
            _modules(),
            _summaries(),
            _entry_points(),
            _metrics(),
        )
        mod_sec = next(s for s in doc.sections if s.heading == "Modules")
        assert "MyApp" in mod_sec.body
        assert "MyApp.Controllers" in mod_sec.body

    def test_entry_points_section(self):
        doc = generate_readme(
            "s1",
            _symbols(),
            _edges(),
            _modules(),
            _summaries(),
            _entry_points(),
            _metrics(),
        )
        ep_sec = next(s for s in doc.sections if s.heading == "Entry Points")
        assert "UserController.Get" in ep_sec.body

    def test_metadata(self):
        doc = generate_readme(
            "s1",
            _symbols(),
            _edges(),
            _modules(),
            _summaries(),
            _entry_points(),
            _metrics(),
        )
        assert doc.metadata["total_symbols"] == 5
        assert doc.metadata["total_edges"] == 2

    def test_empty_data(self):
        doc = generate_readme("s1", [], [], [], [], [], [])
        assert doc.doc_type == DocType.README
        assert len(doc.sections) > 0


class TestGenerateArchitecture:
    def test_returns_architecture_doc(self):
        doc = generate_architecture(
            "s1",
            _symbols(),
            _edges(),
            _modules(),
            _summaries(),
            _entry_points(),
            _metrics(),
        )
        assert doc.doc_type == DocType.ARCHITECTURE
        assert doc.title == "Architecture"

    def test_has_hotspots_section(self):
        doc = generate_architecture(
            "s1",
            _symbols(),
            _edges(),
            _modules(),
            _summaries(),
            _entry_points(),
            _metrics(),
        )
        headings = [s.heading for s in doc.sections]
        assert "Hotspots" in headings

    def test_has_module_map(self):
        doc = generate_architecture(
            "s1",
            _symbols(),
            _edges(),
            _modules(),
            _summaries(),
            _entry_points(),
            _metrics(),
        )
        mm = next(s for s in doc.sections if s.heading == "Module Map")
        assert "MyApp" in mm.body


class TestGenerateModuleDoc:
    def test_returns_module_doc(self):
        doc = generate_module_doc(
            "s1",
            "MyApp",
            _symbols(),
            _edges(),
            _summaries(),
            ["UserService.cs"],
            ["MyApp.Controllers"],
        )
        assert doc.doc_type == DocType.MODULE
        assert doc.scope_id == "MyApp"

    def test_overview_uses_summary(self):
        doc = generate_module_doc(
            "s1",
            "MyApp",
            _symbols(),
            _edges(),
            _summaries(),
            ["UserService.cs"],
            [],
        )
        overview = doc.sections[0]
        assert "Core domain logic" in overview.body

    def test_files_section(self):
        doc = generate_module_doc(
            "s1",
            "MyApp",
            _symbols(),
            _edges(),
            _summaries(),
            ["UserService.cs"],
            [],
        )
        files_sec = next(s for s in doc.sections if s.heading == "Files")
        assert "UserService.cs" in files_sec.body

    def test_classes_section_has_citations(self):
        doc = generate_module_doc(
            "s1",
            "MyApp",
            _symbols(),
            _edges(),
            _summaries(),
            ["UserService.cs"],
            [],
        )
        cls_sec = next(s for s in doc.sections if s.heading == "Classes & Interfaces")
        assert "UserService" in cls_sec.body
        assert len(cls_sec.citations) >= 1

    def test_public_api_section(self):
        doc = generate_module_doc(
            "s1",
            "MyApp",
            _symbols(),
            _edges(),
            _summaries(),
            ["UserService.cs"],
            [],
        )
        api_sec = next(s for s in doc.sections if s.heading == "Public API")
        assert "GetById" in api_sec.body

    def test_dependencies_section(self):
        doc = generate_module_doc(
            "s1",
            "MyApp",
            _symbols(),
            _edges(),
            _summaries(),
            ["UserService.cs"],
            ["MyApp.Controllers"],
        )
        dep_sec = next(s for s in doc.sections if s.heading == "Dependencies")
        assert "MyApp.Controllers" in dep_sec.body


class TestGenerateFlowDoc:
    def test_returns_flow_doc(self):
        doc = generate_flow_doc(
            "s1",
            "MyApp.Controllers.UserController.Get",
            _symbols(),
            _edges(),
            _summaries(),
        )
        assert doc.doc_type == DocType.FLOW
        assert "UserController.Get" in doc.title

    def test_flow_steps_traced(self):
        doc = generate_flow_doc(
            "s1",
            "MyApp.Controllers.UserController.Get",
            _symbols(),
            _edges(),
            _summaries(),
        )
        steps_sec = next(s for s in doc.sections if s.heading == "Execution Steps")
        assert "UserController.Get" in steps_sec.body
        assert "GetById" in steps_sec.body

    def test_flow_has_citations(self):
        doc = generate_flow_doc(
            "s1",
            "MyApp.Controllers.UserController.Get",
            _symbols(),
            _edges(),
            _summaries(),
        )
        steps_sec = next(s for s in doc.sections if s.heading == "Execution Steps")
        assert len(steps_sec.citations) >= 1

    def test_callers_section(self):
        doc = generate_flow_doc(
            "s1",
            "MyApp.UserService.GetById",
            _symbols(),
            _edges(),
            _summaries(),
        )
        callers = next(s for s in doc.sections if s.heading == "Entry Points / Callers")
        assert "UserController.Get" in callers.body or "Delete" in callers.body

    def test_empty_flow(self):
        doc = generate_flow_doc("s1", "Nonexistent", [], [], [])
        steps = next(s for s in doc.sections if s.heading == "Execution Steps")
        assert "Nonexistent" in steps.body


class TestGenerateRunbook:
    def test_returns_runbook(self):
        doc = generate_runbook(
            "s1",
            _symbols(),
            _edges(),
            _modules(),
            _summaries(),
            _entry_points(),
            _metrics(),
        )
        assert doc.doc_type == DocType.RUNBOOK
        assert doc.title == "Runbook"

    def test_has_quick_start(self):
        doc = generate_runbook(
            "s1",
            _symbols(),
            _edges(),
            _modules(),
            _summaries(),
            _entry_points(),
            _metrics(),
        )
        qs = next(s for s in doc.sections if s.heading == "Quick Start")
        assert "Clone" in qs.body

    def test_has_known_risks(self):
        doc = generate_runbook(
            "s1",
            _symbols(),
            _edges(),
            _modules(),
            _summaries(),
            _entry_points(),
            _metrics(),
        )
        kr = next(s for s in doc.sections if s.heading == "Known Risks & Hotspots")
        assert len(kr.body) > 0

# ruff: noqa: E501
"""
Tests for DocGen Phase 1: Enhanced Doc Types & Content Quality.

Tests 4 new doc types: API Reference, Onboarding, Changelog, Dependency Map.
"""

from __future__ import annotations

from app.docgen.generator import (
    generate_api_reference,
    generate_changelog,
    generate_dependency_map,
    generate_onboarding,
)
from app.docgen.models import DocType
from app.docgen.renderer import render_markdown

# ---------------------------------------------------------------------------
# Test data fixtures
# ---------------------------------------------------------------------------

SYMBOLS = [
    {
        "fq_name": "app.auth.AuthService",
        "name": "AuthService",
        "kind": "class",
        "namespace": "app.auth",
        "file_path": "app/auth/service.py",
        "start_line": 10,
        "end_line": 50,
        "signature": "class AuthService",
        "modifiers": "public",
    },
    {
        "fq_name": "app.auth.AuthService.authenticate",
        "name": "authenticate",
        "kind": "method",
        "namespace": "app.auth",
        "file_path": "app/auth/service.py",
        "start_line": 15,
        "end_line": 30,
        "signature": "def authenticate(self, token: str) -> User",
        "modifiers": "public",
    },
    {
        "fq_name": "app.auth.AuthService._validate",
        "name": "_validate",
        "kind": "method",
        "namespace": "app.auth",
        "file_path": "app/auth/service.py",
        "start_line": 32,
        "end_line": 40,
        "signature": "def _validate(self, token: str) -> bool",
        "modifiers": "private",
    },
    {
        "fq_name": "app.storage.UserRepo",
        "name": "UserRepo",
        "kind": "class",
        "namespace": "app.storage",
        "file_path": "app/storage/repo.py",
        "start_line": 5,
        "end_line": 40,
        "signature": "class UserRepo",
        "modifiers": "public",
    },
    {
        "fq_name": "app.storage.UserRepo.get_by_id",
        "name": "get_by_id",
        "kind": "method",
        "namespace": "app.storage",
        "file_path": "app/storage/repo.py",
        "start_line": 10,
        "end_line": 20,
        "signature": "def get_by_id(self, user_id: str) -> User | None",
        "modifiers": "public",
    },
    {
        "fq_name": "app.config.Settings",
        "name": "Settings",
        "kind": "class",
        "namespace": "app.config",
        "file_path": "app/config/settings.py",
        "start_line": 1,
        "end_line": 30,
        "signature": "class Settings",
        "modifiers": "public",
    },
    {
        "fq_name": "app.main.startup",
        "name": "startup",
        "kind": "function",
        "namespace": "app.main",
        "file_path": "app/main.py",
        "start_line": 1,
        "end_line": 10,
        "signature": "async def startup()",
        "modifiers": "public",
    },
]

EDGES = [
    {
        "source_fq_name": "app.auth.AuthService.authenticate",
        "target_fq_name": "app.storage.UserRepo.get_by_id",
        "edge_type": "calls",
    },
    {
        "source_fq_name": "app.auth.AuthService.authenticate",
        "target_fq_name": "app.auth.AuthService._validate",
        "edge_type": "calls",
    },
    {
        "source_fq_name": "app.main.startup",
        "target_fq_name": "app.config.Settings",
        "edge_type": "calls",
    },
]

MODULES = [
    {
        "name": "app.auth",
        "symbol_count": 3,
        "file_count": 1,
        "files": ["app/auth/service.py"],
        "dependencies": ["app.storage"],
    },
    {
        "name": "app.storage",
        "symbol_count": 2,
        "file_count": 1,
        "files": ["app/storage/repo.py"],
        "dependencies": [],
    },
    {
        "name": "app.config",
        "symbol_count": 1,
        "file_count": 1,
        "files": ["app/config/settings.py"],
        "dependencies": [],
    },
    {
        "name": "app.main",
        "symbol_count": 1,
        "file_count": 1,
        "files": ["app/main.py"],
        "dependencies": ["app.config"],
    },
]

SUMMARIES = [
    {"scope_type": "module", "scope_id": "app.auth", "content": "Authentication module"},
    {"scope_type": "symbol", "scope_id": "app.auth.AuthService", "content": "Main auth service"},
]

ENTRY_POINTS = [
    {
        "symbol_fq_name": "app.main.startup",
        "kind": "entry_point",
        "file_path": "app/main.py",
        "line": 1,
    },
]

METRICS = [
    {"fq_name": "app.auth.AuthService.authenticate", "kind": "method", "fan_in": 5, "fan_out": 2, "lines_of_code": 15},
]


# ---------------------------------------------------------------------------
# API Reference tests
# ---------------------------------------------------------------------------


class TestGenerateApiReference:

    def test_generates_correct_doc_type(self):
        doc = generate_api_reference("snap1", "app.auth", SYMBOLS, EDGES, SUMMARIES)
        assert doc.doc_type == DocType.API_REFERENCE

    def test_title_contains_module(self):
        doc = generate_api_reference("snap1", "app.auth", SYMBOLS, EDGES, SUMMARIES)
        assert "app.auth" in doc.title

    def test_scope_id_is_module(self):
        doc = generate_api_reference("snap1", "app.auth", SYMBOLS, EDGES, SUMMARIES)
        assert doc.scope_id == "app.auth"

    def test_has_4_sections(self):
        doc = generate_api_reference("snap1", "app.auth", SYMBOLS, EDGES, SUMMARIES)
        assert len(doc.sections) == 4

    def test_overview_shows_counts(self):
        doc = generate_api_reference("snap1", "app.auth", SYMBOLS, EDGES, SUMMARIES)
        overview = doc.sections[0]
        assert "1" in overview.body  # 1 class
        assert "public" in overview.body.lower() or "methods" in overview.body.lower()

    def test_classes_section_lists_types(self):
        doc = generate_api_reference("snap1", "app.auth", SYMBOLS, EDGES, SUMMARIES)
        classes = doc.sections[1]
        assert "AuthService" in classes.body
        assert len(classes.citations) >= 1

    def test_methods_section_lists_public_only(self):
        doc = generate_api_reference("snap1", "app.auth", SYMBOLS, EDGES, SUMMARIES)
        methods = doc.sections[2]
        assert "authenticate" in methods.body
        assert "_validate" not in methods.body  # private excluded

    def test_metadata_has_counts(self):
        doc = generate_api_reference("snap1", "app.auth", SYMBOLS, EDGES, SUMMARIES)
        assert doc.metadata["module"] == "app.auth"
        assert doc.metadata["types_count"] == 1

    def test_renders_to_markdown(self):
        doc = generate_api_reference("snap1", "app.auth", SYMBOLS, EDGES, SUMMARIES)
        md = render_markdown(doc)
        assert "# API Reference: app.auth" in md
        assert "AuthService" in md

    def test_empty_module(self):
        doc = generate_api_reference("snap1", "nonexistent", SYMBOLS, EDGES, SUMMARIES)
        assert doc.metadata["types_count"] == 0
        assert doc.metadata["methods_count"] == 0


# ---------------------------------------------------------------------------
# Onboarding tests
# ---------------------------------------------------------------------------


class TestGenerateOnboarding:

    def test_generates_correct_doc_type(self):
        doc = generate_onboarding("snap1", SYMBOLS, EDGES, MODULES, SUMMARIES, ENTRY_POINTS, METRICS)
        assert doc.doc_type == DocType.ONBOARDING

    def test_title(self):
        doc = generate_onboarding("snap1", SYMBOLS, EDGES, MODULES, SUMMARIES, ENTRY_POINTS, METRICS)
        assert "Onboarding" in doc.title

    def test_has_7_sections(self):
        doc = generate_onboarding("snap1", SYMBOLS, EDGES, MODULES, SUMMARIES, ENTRY_POINTS, METRICS)
        assert len(doc.sections) == 7

    def test_welcome_shows_counts(self):
        doc = generate_onboarding("snap1", SYMBOLS, EDGES, MODULES, SUMMARIES, ENTRY_POINTS, METRICS)
        welcome = doc.sections[0]
        assert "7" in welcome.body  # 7 symbols
        assert "4" in welcome.body  # 4 modules

    def test_setup_detects_config(self):
        doc = generate_onboarding("snap1", SYMBOLS, EDGES, MODULES, SUMMARIES, ENTRY_POINTS, METRICS)
        setup = doc.sections[1]
        assert "config" in setup.body.lower() or "settings" in setup.body.lower()

    def test_project_structure_table(self):
        doc = generate_onboarding("snap1", SYMBOLS, EDGES, MODULES, SUMMARIES, ENTRY_POINTS, METRICS)
        structure = doc.sections[2]
        assert "app.auth" in structure.body
        assert "|" in structure.body  # table format

    def test_entry_points_listed(self):
        doc = generate_onboarding("snap1", SYMBOLS, EDGES, MODULES, SUMMARIES, ENTRY_POINTS, METRICS)
        ep = doc.sections[3]
        assert "app.main.startup" in ep.body

    def test_key_flows_show_callees(self):
        doc = generate_onboarding("snap1", SYMBOLS, EDGES, MODULES, SUMMARIES, ENTRY_POINTS, METRICS)
        flows = doc.sections[4]
        assert "app.config.Settings" in flows.body

    def test_where_to_find(self):
        doc = generate_onboarding("snap1", SYMBOLS, EDGES, MODULES, SUMMARIES, ENTRY_POINTS, METRICS)
        where = doc.sections[5]
        assert "app.auth" in where.body

    def test_first_steps(self):
        doc = generate_onboarding("snap1", SYMBOLS, EDGES, MODULES, SUMMARIES, ENTRY_POINTS, METRICS)
        first = doc.sections[6]
        assert "Architecture" in first.body

    def test_renders_to_markdown(self):
        doc = generate_onboarding("snap1", SYMBOLS, EDGES, MODULES, SUMMARIES, ENTRY_POINTS, METRICS)
        md = render_markdown(doc)
        assert "# Onboarding Guide" in md


# ---------------------------------------------------------------------------
# Changelog tests
# ---------------------------------------------------------------------------


PREV_SYMBOLS = [
    {
        "fq_name": "app.auth.AuthService",
        "name": "AuthService", "kind": "class",
        "namespace": "app.auth", "file_path": "app/auth/service.py",
        "start_line": 10, "end_line": 50,
        "signature": "class AuthService", "modifiers": "public",
    },
    {
        "fq_name": "app.auth.AuthService.login",
        "name": "login", "kind": "method",
        "namespace": "app.auth", "file_path": "app/auth/service.py",
        "start_line": 15, "end_line": 25,
        "signature": "def login(self, username: str) -> Token",
        "modifiers": "public",
    },
    {
        "fq_name": "app.old.OldClass",
        "name": "OldClass", "kind": "class",
        "namespace": "app.old", "file_path": "app/old.py",
        "start_line": 1, "end_line": 10,
        "signature": "class OldClass", "modifiers": "public",
    },
]

CUR_SYMBOLS_FOR_CHANGELOG = [
    {
        "fq_name": "app.auth.AuthService",
        "name": "AuthService", "kind": "class",
        "namespace": "app.auth", "file_path": "app/auth/service.py",
        "start_line": 10, "end_line": 60,
        "signature": "class AuthService(BaseService)",  # MODIFIED
        "modifiers": "public",
    },
    {
        "fq_name": "app.auth.AuthService.login",
        "name": "login", "kind": "method",
        "namespace": "app.auth", "file_path": "app/auth/service.py",
        "start_line": 15, "end_line": 25,
        "signature": "def login(self, username: str) -> Token",  # unchanged
        "modifiers": "public",
    },
    {
        "fq_name": "app.auth.AuthService.logout",
        "name": "logout", "kind": "method",
        "namespace": "app.auth", "file_path": "app/auth/service.py",
        "start_line": 30, "end_line": 35,
        "signature": "def logout(self) -> None",  # ADDED
        "modifiers": "public",
    },
]


class TestGenerateChangelog:

    def test_generates_correct_doc_type(self):
        doc = generate_changelog("snap2", "snap1", CUR_SYMBOLS_FOR_CHANGELOG, PREV_SYMBOLS, [], [])
        assert doc.doc_type == DocType.CHANGELOG

    def test_scope_id_is_previous(self):
        doc = generate_changelog("snap2", "snap1", CUR_SYMBOLS_FOR_CHANGELOG, PREV_SYMBOLS, [], [])
        assert doc.scope_id == "snap1"

    def test_has_5_sections(self):
        doc = generate_changelog("snap2", "snap1", CUR_SYMBOLS_FOR_CHANGELOG, PREV_SYMBOLS, [], [])
        assert len(doc.sections) == 5

    def test_detects_added(self):
        doc = generate_changelog("snap2", "snap1", CUR_SYMBOLS_FOR_CHANGELOG, PREV_SYMBOLS, [], [])
        added = doc.sections[1]
        assert "logout" in added.body

    def test_detects_removed(self):
        doc = generate_changelog("snap2", "snap1", CUR_SYMBOLS_FOR_CHANGELOG, PREV_SYMBOLS, [], [])
        removed = doc.sections[2]
        assert "OldClass" in removed.body

    def test_detects_modified(self):
        doc = generate_changelog("snap2", "snap1", CUR_SYMBOLS_FOR_CHANGELOG, PREV_SYMBOLS, [], [])
        modified = doc.sections[3]
        assert "AuthService" in modified.body
        assert "BaseService" in modified.body

    def test_detects_breaking_changes(self):
        doc = generate_changelog("snap2", "snap1", CUR_SYMBOLS_FOR_CHANGELOG, PREV_SYMBOLS, [], [])
        breaking = doc.sections[4]
        assert "OldClass" in breaking.body  # public symbol removed

    def test_metadata_counts(self):
        doc = generate_changelog("snap2", "snap1", CUR_SYMBOLS_FOR_CHANGELOG, PREV_SYMBOLS, [], [])
        assert doc.metadata["added_count"] == 1
        assert doc.metadata["removed_count"] == 1
        assert doc.metadata["modified_count"] == 1
        assert doc.metadata["breaking_count"] == 1

    def test_no_changes(self):
        doc = generate_changelog("snap2", "snap1", PREV_SYMBOLS, PREV_SYMBOLS, [], [])
        assert doc.metadata["added_count"] == 0
        assert doc.metadata["removed_count"] == 0

    def test_renders_to_markdown(self):
        doc = generate_changelog("snap2", "snap1", CUR_SYMBOLS_FOR_CHANGELOG, PREV_SYMBOLS, [], [])
        md = render_markdown(doc)
        assert "Changelog" in md
        assert "Added" in md
        assert "Breaking" in md


# ---------------------------------------------------------------------------
# Dependency Map tests
# ---------------------------------------------------------------------------


class TestGenerateDependencyMap:

    def test_generates_correct_doc_type(self):
        doc = generate_dependency_map("snap1", SYMBOLS, EDGES, MODULES)
        assert doc.doc_type == DocType.DEPENDENCY_MAP

    def test_has_5_sections(self):
        doc = generate_dependency_map("snap1", SYMBOLS, EDGES, MODULES)
        assert len(doc.sections) == 5

    def test_overview_shows_counts(self):
        doc = generate_dependency_map("snap1", SYMBOLS, EDGES, MODULES)
        overview = doc.sections[0]
        assert "4" in overview.body  # 4 modules

    def test_external_deps_detected(self):
        # Add an edge to an external namespace
        edges_with_ext = EDGES + [
            {"source_fq_name": "app.auth.AuthService", "target_fq_name": "jwt.decode", "edge_type": "calls"},
        ]
        doc = generate_dependency_map("snap1", SYMBOLS, edges_with_ext, MODULES)
        ext = doc.sections[1]
        assert "jwt" in ext.body

    def test_internal_deps(self):
        doc = generate_dependency_map("snap1", SYMBOLS, EDGES, MODULES)
        internal = doc.sections[2]
        assert "app.auth" in internal.body or "app.main" in internal.body

    def test_circular_deps_detected(self):
        # Create circular: auth -> storage and storage -> auth
        circular_edges = [
            {"source_fq_name": "app.auth.AuthService.authenticate", "target_fq_name": "app.storage.UserRepo.get_by_id", "edge_type": "calls"},
            {"source_fq_name": "app.storage.UserRepo.get_by_id", "target_fq_name": "app.auth.AuthService.authenticate", "edge_type": "calls"},
        ]
        doc = generate_dependency_map("snap1", SYMBOLS, circular_edges, MODULES)
        circ = doc.sections[3]
        assert "app.auth" in circ.body
        assert "app.storage" in circ.body

    def test_no_circular_deps(self):
        doc = generate_dependency_map("snap1", SYMBOLS, EDGES, MODULES)
        circ = doc.sections[3]
        assert "No circular" in circ.body or "?" in circ.body

    def test_metrics_table(self):
        doc = generate_dependency_map("snap1", SYMBOLS, EDGES, MODULES)
        metrics = doc.sections[4]
        assert "Module" in metrics.body
        assert "|" in metrics.body

    def test_metadata(self):
        doc = generate_dependency_map("snap1", SYMBOLS, EDGES, MODULES)
        assert "internal_deps_count" in doc.metadata
        assert "circular_count" in doc.metadata

    def test_renders_to_markdown(self):
        doc = generate_dependency_map("snap1", SYMBOLS, EDGES, MODULES)
        md = render_markdown(doc)
        assert "# Dependency Map" in md
        assert "Internal" in md

    def test_empty_edges(self):
        doc = generate_dependency_map("snap1", SYMBOLS, [], MODULES)
        assert doc.metadata["internal_deps_count"] == 0
        assert doc.metadata["circular_count"] == 0

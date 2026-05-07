# ruff: noqa: E501
"""
Tests for DocGen Phase 2: Diagram Embedding.

Tests all 5 Mermaid diagram generators + config + simplification.
"""

from __future__ import annotations

import pytest

from app.docgen.diagrams import (
    DiagramConfig,
    DiagramType,
    MermaidDiagram,
    generate_class_diagram,
    generate_dependency_graph,
    generate_er_diagram,
    generate_flowchart,
    generate_sequence_diagram,
)


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

SYMBOLS = [
    {"fq_name": "app.auth.AuthService", "name": "AuthService", "kind": "class", "namespace": "app.auth", "file_path": "app/auth/service.py", "start_line": 10, "end_line": 50, "signature": "class AuthService", "modifiers": "public"},
    {"fq_name": "app.auth.AuthService.authenticate", "name": "authenticate", "kind": "method", "namespace": "app.auth", "file_path": "app/auth/service.py", "start_line": 15, "end_line": 30, "signature": "def authenticate()", "modifiers": "public"},
    {"fq_name": "app.auth.AuthService._validate", "name": "_validate", "kind": "method", "namespace": "app.auth", "file_path": "app/auth/service.py", "start_line": 32, "end_line": 40, "signature": "def _validate()", "modifiers": "private"},
    {"fq_name": "app.auth.Token", "name": "Token", "kind": "class", "namespace": "app.auth", "file_path": "app/auth/models.py", "start_line": 1, "end_line": 10, "signature": "class Token", "modifiers": "public"},
    {"fq_name": "app.storage.UserRepo", "name": "UserRepo", "kind": "class", "namespace": "app.storage", "file_path": "app/storage/repo.py", "start_line": 5, "end_line": 40, "signature": "class UserRepo", "modifiers": "public"},
    {"fq_name": "app.storage.UserRepo.get_by_id", "name": "get_by_id", "kind": "method", "namespace": "app.storage", "file_path": "app/storage/repo.py", "start_line": 10, "end_line": 20, "signature": "def get_by_id()", "modifiers": "public"},
    {"fq_name": "app.api.Router", "name": "Router", "kind": "class", "namespace": "app.api", "file_path": "app/api/router.py", "start_line": 1, "end_line": 30, "signature": "class Router", "modifiers": "public"},
    {"fq_name": "app.api.Router.handle", "name": "handle", "kind": "method", "namespace": "app.api", "file_path": "app/api/router.py", "start_line": 5, "end_line": 15, "signature": "def handle()", "modifiers": "public"},
]

EDGES = [
    {"source_fq_name": "app.api.Router.handle", "target_fq_name": "app.auth.AuthService.authenticate", "edge_type": "calls"},
    {"source_fq_name": "app.auth.AuthService.authenticate", "target_fq_name": "app.storage.UserRepo.get_by_id", "edge_type": "calls"},
    {"source_fq_name": "app.auth.AuthService.authenticate", "target_fq_name": "app.auth.AuthService._validate", "edge_type": "calls"},
    {"source_fq_name": "app.auth.Token", "target_fq_name": "app.auth.AuthService", "edge_type": "inherits"},
]

MODULES = [
    {"name": "app.auth", "symbol_count": 4, "file_count": 2, "files": ["app/auth/service.py", "app/auth/models.py"], "dependencies": ["app.storage"]},
    {"name": "app.storage", "symbol_count": 2, "file_count": 1, "files": ["app/storage/repo.py"], "dependencies": []},
    {"name": "app.api", "symbol_count": 2, "file_count": 1, "files": ["app/api/router.py"], "dependencies": ["app.auth"]},
]


# ---------------------------------------------------------------------------
# Dependency Graph tests
# ---------------------------------------------------------------------------


class TestDependencyGraph:

    def test_generates_graph_type(self):
        d = generate_dependency_graph(MODULES, EDGES, SYMBOLS)
        assert d.diagram_type == DiagramType.DEPENDENCY_GRAPH

    def test_contains_mermaid_header(self):
        d = generate_dependency_graph(MODULES, EDGES, SYMBOLS)
        assert d.content.startswith("graph TD")

    def test_has_nodes(self):
        d = generate_dependency_graph(MODULES, EDGES, SYMBOLS)
        assert d.node_count >= 2

    def test_has_edges(self):
        d = generate_dependency_graph(MODULES, EDGES, SYMBOLS)
        assert d.edge_count >= 1
        assert "-->" in d.content

    def test_to_markdown(self):
        d = generate_dependency_graph(MODULES, EDGES, SYMBOLS)
        md = d.to_markdown()
        assert "```mermaid" in md
        assert "```" in md

    def test_respects_max_nodes(self):
        cfg = DiagramConfig(max_nodes=2)
        d = generate_dependency_graph(MODULES, EDGES, SYMBOLS, config=cfg)
        assert d.node_count <= 2

    def test_respects_direction(self):
        cfg = DiagramConfig(direction="LR")
        d = generate_dependency_graph(MODULES, EDGES, SYMBOLS, config=cfg)
        assert "graph LR" in d.content

    def test_empty_edges(self):
        d = generate_dependency_graph(MODULES, [], SYMBOLS)
        assert d.edge_count == 0

    def test_title(self):
        d = generate_dependency_graph(MODULES, EDGES, SYMBOLS)
        assert d.title == "Module Dependencies"


# ---------------------------------------------------------------------------
# Class Diagram tests
# ---------------------------------------------------------------------------


class TestClassDiagram:

    def test_generates_class_type(self):
        d = generate_class_diagram("app.auth", SYMBOLS, EDGES)
        assert d.diagram_type == DiagramType.CLASS_DIAGRAM

    def test_contains_header(self):
        d = generate_class_diagram("app.auth", SYMBOLS, EDGES)
        assert "classDiagram" in d.content

    def test_lists_classes(self):
        d = generate_class_diagram("app.auth", SYMBOLS, EDGES)
        assert "AuthService" in d.content
        assert "Token" in d.content

    def test_shows_methods(self):
        d = generate_class_diagram("app.auth", SYMBOLS, EDGES)
        assert "+authenticate()" in d.content

    def test_shows_private_methods(self):
        d = generate_class_diagram("app.auth", SYMBOLS, EDGES)
        assert "-_validate()" in d.content

    def test_inheritance_edge(self):
        d = generate_class_diagram("app.auth", SYMBOLS, EDGES)
        assert "<|--" in d.content  # Token inherits AuthService

    def test_empty_module(self):
        d = generate_class_diagram("nonexistent", SYMBOLS, EDGES)
        assert d.node_count == 0

    def test_title_contains_module(self):
        d = generate_class_diagram("app.auth", SYMBOLS, EDGES)
        assert "app.auth" in d.title

    def test_max_nodes_respected(self):
        cfg = DiagramConfig(max_nodes=1)
        d = generate_class_diagram("app.auth", SYMBOLS, EDGES, config=cfg)
        assert d.node_count <= 1


# ---------------------------------------------------------------------------
# Sequence Diagram tests
# ---------------------------------------------------------------------------


class TestSequenceDiagram:

    def test_generates_sequence_type(self):
        d = generate_sequence_diagram("app.api.Router.handle", SYMBOLS, EDGES)
        assert d.diagram_type == DiagramType.SEQUENCE

    def test_contains_header(self):
        d = generate_sequence_diagram("app.api.Router.handle", SYMBOLS, EDGES)
        assert "sequenceDiagram" in d.content

    def test_has_participants(self):
        d = generate_sequence_diagram("app.api.Router.handle", SYMBOLS, EDGES)
        assert "participant" in d.content

    def test_has_messages(self):
        d = generate_sequence_diagram("app.api.Router.handle", SYMBOLS, EDGES)
        assert "->>" in d.content

    def test_follows_call_chain(self):
        d = generate_sequence_diagram("app.api.Router.handle", SYMBOLS, EDGES)
        # Should show api -> auth -> storage
        assert d.edge_count >= 2

    def test_no_self_calls(self):
        d = generate_sequence_diagram("app.auth.AuthService.authenticate", SYMBOLS, EDGES)
        # _validate is in same namespace, should be skipped
        lines = d.content.split("\n")
        for line in lines:
            if "->>" in line:
                parts = line.split("->>")
                src = parts[0].strip()
                tgt = parts[1].split(":")[0].strip().lstrip("+")
                assert src != tgt

    def test_empty_entry(self):
        d = generate_sequence_diagram("nonexistent", SYMBOLS, EDGES)
        assert d.edge_count == 0

    def test_title(self):
        d = generate_sequence_diagram("app.api.Router.handle", SYMBOLS, EDGES)
        assert "handle" in d.title


# ---------------------------------------------------------------------------
# Flowchart tests
# ---------------------------------------------------------------------------


class TestFlowchart:

    def test_generates_flowchart_type(self):
        d = generate_flowchart("app.api.Router.handle", EDGES)
        assert d.diagram_type == DiagramType.FLOWCHART

    def test_contains_header(self):
        d = generate_flowchart("app.api.Router.handle", EDGES)
        assert "flowchart TD" in d.content

    def test_has_nodes(self):
        d = generate_flowchart("app.api.Router.handle", EDGES)
        assert d.node_count >= 2

    def test_has_edges(self):
        d = generate_flowchart("app.api.Router.handle", EDGES)
        assert "-->" in d.content

    def test_bfs_from_entry(self):
        d = generate_flowchart("app.api.Router.handle", EDGES)
        assert "handle" in d.content
        assert "authenticate" in d.content

    def test_max_edges_respected(self):
        cfg = DiagramConfig(max_edges=1)
        d = generate_flowchart("app.api.Router.handle", EDGES, config=cfg)
        assert d.edge_count <= 1

    def test_empty_entry(self):
        d = generate_flowchart("nonexistent", EDGES)
        assert d.node_count == 0

    def test_direction_config(self):
        cfg = DiagramConfig(direction="LR")
        d = generate_flowchart("app.api.Router.handle", EDGES, config=cfg)
        assert "flowchart LR" in d.content


# ---------------------------------------------------------------------------
# ER Diagram tests
# ---------------------------------------------------------------------------


class TestERDiagram:

    def test_generates_er_type(self):
        d = generate_er_diagram(SYMBOLS, EDGES)
        assert d.diagram_type == DiagramType.ER_DIAGRAM

    def test_contains_header(self):
        d = generate_er_diagram(SYMBOLS, EDGES)
        assert "erDiagram" in d.content

    def test_lists_entities(self):
        d = generate_er_diagram(SYMBOLS, EDGES)
        assert "AuthService" in d.content
        assert "UserRepo" in d.content

    def test_shows_relationships(self):
        d = generate_er_diagram(SYMBOLS, EDGES)
        # Token inherits AuthService
        assert "inherits" in d.content or d.edge_count >= 1

    def test_max_nodes(self):
        cfg = DiagramConfig(max_nodes=2)
        d = generate_er_diagram(SYMBOLS, EDGES, config=cfg)
        assert d.node_count <= 2

    def test_empty_symbols(self):
        d = generate_er_diagram([], EDGES)
        assert d.node_count == 0


# ---------------------------------------------------------------------------
# MermaidDiagram model tests
# ---------------------------------------------------------------------------


class TestMermaidDiagramModel:

    def test_to_markdown_wraps_in_code_block(self):
        d = MermaidDiagram(
            diagram_type=DiagramType.FLOWCHART,
            title="Test",
            content="flowchart TD\n    A --> B",
        )
        md = d.to_markdown()
        assert md == "```mermaid\nflowchart TD\n    A --> B\n```"

    def test_diagram_config_defaults(self):
        cfg = DiagramConfig()
        assert cfg.max_nodes == 25
        assert cfg.max_edges == 50
        assert cfg.direction == "TD"

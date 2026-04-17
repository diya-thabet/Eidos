"""
Java parser using tree-sitter.

Extracts symbols (classes, interfaces, enums, methods, constructors, fields)
and edges (calls, inheritance, implements, imports, containment) from Java
source files.
"""

from __future__ import annotations

import logging
from pathlib import Path

import tree_sitter_java as tsjava
from tree_sitter import Language, Node, Parser

from app.analysis.base_parser import LanguageParser
from app.analysis.models import (
    EdgeInfo,
    EdgeType,
    FileAnalysis,
    SymbolInfo,
    SymbolKind,
)

logger = logging.getLogger(__name__)

JAVA_LANGUAGE = Language(tsjava.language())

_TYPE_DECLARATION_MAP: dict[str, SymbolKind] = {
    "class_declaration": SymbolKind.CLASS,
    "interface_declaration": SymbolKind.INTERFACE,
    "enum_declaration": SymbolKind.ENUM,
    "record_declaration": SymbolKind.RECORD,
    "annotation_type_declaration": SymbolKind.INTERFACE,
}

_MEMBER_DECLARATION_MAP: dict[str, SymbolKind] = {
    "method_declaration": SymbolKind.METHOD,
    "constructor_declaration": SymbolKind.CONSTRUCTOR,
    "field_declaration": SymbolKind.FIELD,
}


class JavaParser(LanguageParser):
    """Full Java source parser built on tree-sitter."""

    @property
    def language_id(self) -> str:
        return "java"

    def parse_file(self, source: bytes, file_path: str) -> FileAnalysis:
        return parse_file(source, file_path)


def create_parser() -> Parser:
    return Parser(JAVA_LANGUAGE)


def parse_file(source: bytes, file_path: str) -> FileAnalysis:
    """Parse a single Java source file and extract symbols + edges."""
    parser = create_parser()
    tree = parser.parse(source)
    root = tree.root_node

    analysis = FileAnalysis(path=file_path, namespace="")
    analysis.namespace = _extract_package(root, source)
    analysis.using_directives = _extract_imports(root, source)

    for imp in analysis.using_directives:
        analysis.edges.append(
            EdgeInfo(
                source_fq_name=analysis.namespace or file_path,
                target_fq_name=imp,
                edge_type=EdgeType.IMPORTS,
                file_path=file_path,
            )
        )

    _extract_types(root, source, file_path, analysis, analysis.namespace, None)
    return analysis


def parse_file_from_path(file_path: Path, repo_root: Path) -> FileAnalysis:
    source = file_path.read_bytes()
    rel_path = file_path.relative_to(repo_root).as_posix()
    return parse_file(source, rel_path)


# ------------------------------------------------------------------
# Package and imports
# ------------------------------------------------------------------


def _extract_package(root: Node, source: bytes) -> str:
    for child in root.children:
        if child.type == "package_declaration":
            for sub in child.children:
                if sub.type in ("scoped_identifier", "identifier"):
                    return _node_text(sub, source)
    return ""


def _extract_imports(root: Node, source: bytes) -> list[str]:
    imports: list[str] = []
    for child in root.children:
        if child.type == "import_declaration":
            for sub in child.children:
                if sub.type in ("scoped_identifier", "identifier"):
                    imports.append(_node_text(sub, source))
                    break
    return imports


# ------------------------------------------------------------------
# Type and member extraction
# ------------------------------------------------------------------


def _extract_types(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    pkg: str,
    parent_fq: str | None,
) -> None:
    for child in node.children:
        if child.type in _TYPE_DECLARATION_MAP:
            _extract_type(child, source, file_path, analysis, pkg, parent_fq)
        elif child.type == "class_body":
            _extract_types(child, source, file_path, analysis, pkg, parent_fq)


def _extract_type(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    pkg: str,
    parent_fq: str | None,
) -> None:
    kind = _TYPE_DECLARATION_MAP[node.type]
    name = _get_declaration_name(node, source)

    if parent_fq:
        fq = f"{parent_fq}.{name}"
    elif pkg:
        fq = f"{pkg}.{name}"
    else:
        fq = name

    modifiers = _extract_modifiers(node, source)
    superclass = _extract_superclass(node, source)
    interfaces = _extract_super_interfaces(node, source)
    base_types = ([superclass] if superclass else []) + interfaces

    symbol = SymbolInfo(
        name=name,
        kind=kind,
        fq_name=fq,
        file_path=file_path,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        namespace=pkg,
        parent_fq_name=parent_fq,
        modifiers=modifiers,
        base_types=base_types,
        doc_comment=_extract_doc_comment(node, source),
    )
    analysis.symbols.append(symbol)

    if parent_fq:
        analysis.edges.append(
            EdgeInfo(
                source_fq_name=parent_fq,
                target_fq_name=fq,
                edge_type=EdgeType.CONTAINS,
                file_path=file_path,
                line=node.start_point[0] + 1,
            )
        )

    if superclass:
        analysis.edges.append(
            EdgeInfo(
                source_fq_name=fq,
                target_fq_name=superclass,
                edge_type=EdgeType.INHERITS,
                file_path=file_path,
                line=node.start_point[0] + 1,
            )
        )
    for iface in interfaces:
        analysis.edges.append(
            EdgeInfo(
                source_fq_name=fq,
                target_fq_name=iface,
                edge_type=EdgeType.IMPLEMENTS,
                file_path=file_path,
                line=node.start_point[0] + 1,
            )
        )

    body = (
        _find_child_by_type(node, "class_body")
        or _find_child_by_type(node, "interface_body")
        or _find_child_by_type(node, "enum_body")
    )
    if body:
        # For enums, members live inside enum_body_declarations
        enum_body_decls = _find_child_by_type(body, "enum_body_declarations")
        if enum_body_decls:
            _extract_members(enum_body_decls, source, file_path, analysis, pkg, fq)
            _extract_types(enum_body_decls, source, file_path, analysis, pkg, fq)
        _extract_members(body, source, file_path, analysis, pkg, fq)
        _extract_types(body, source, file_path, analysis, pkg, fq)


def _extract_members(
    body: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    pkg: str,
    parent_fq: str,
) -> None:
    for child in body.children:
        if child.type not in _MEMBER_DECLARATION_MAP:
            continue

        kind = _MEMBER_DECLARATION_MAP[child.type]
        name = _get_member_name(child, kind, source, parent_fq)
        if not name:
            continue

        fq = f"{parent_fq}.{name}"

        symbol = SymbolInfo(
            name=name,
            kind=kind,
            fq_name=fq,
            file_path=file_path,
            start_line=child.start_point[0] + 1,
            end_line=child.end_point[0] + 1,
            namespace=pkg,
            parent_fq_name=parent_fq,
            modifiers=_extract_modifiers(child, source),
            signature=_extract_signature(child, source),
            parameters=_extract_parameters(child, source),
            return_type=_extract_return_type(child, source),
            doc_comment=_extract_doc_comment(child, source),
        )
        analysis.symbols.append(symbol)

        analysis.edges.append(
            EdgeInfo(
                source_fq_name=parent_fq,
                target_fq_name=fq,
                edge_type=EdgeType.CONTAINS,
                file_path=file_path,
                line=child.start_point[0] + 1,
            )
        )

        if kind in (SymbolKind.METHOD, SymbolKind.CONSTRUCTOR):
            _extract_calls(child, source, file_path, analysis, fq)


def _extract_calls(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    caller_fq: str,
) -> None:
    for child in _walk(node):
        if child.type == "method_invocation":
            target = _extract_invocation_target(child, source)
            if target:
                analysis.edges.append(
                    EdgeInfo(
                        source_fq_name=caller_fq,
                        target_fq_name=target,
                        edge_type=EdgeType.CALLS,
                        file_path=file_path,
                        line=child.start_point[0] + 1,
                    )
                )
        elif child.type == "object_creation_expression":
            type_node = _find_child_by_type(child, "type_identifier") or child.child_by_field_name(
                "type"
            )
            if type_node:
                analysis.edges.append(
                    EdgeInfo(
                        source_fq_name=caller_fq,
                        target_fq_name=_node_text(type_node, source),
                        edge_type=EdgeType.CALLS,
                        file_path=file_path,
                        line=child.start_point[0] + 1,
                    )
                )


# ------------------------------------------------------------------
# Java-specific AST helpers
# ------------------------------------------------------------------


def _extract_superclass(node: Node, source: bytes) -> str:
    sc = _find_child_by_type(node, "superclass")
    if sc:
        tn = _find_child_by_type(sc, "type_identifier") or _find_child_by_type(sc, "generic_type")
        if tn:
            return _node_text(tn, source)
    return ""


def _extract_super_interfaces(node: Node, source: bytes) -> list[str]:
    result: list[str] = []
    iface_node = _find_child_by_type(node, "super_interfaces") or _find_child_by_type(
        node, "extends_interfaces"
    )
    if not iface_node:
        return result
    type_list = _find_child_by_type(iface_node, "type_list")
    if type_list:
        for child in type_list.children:
            if child.type in (
                "type_identifier",
                "generic_type",
                "scoped_type_identifier",
            ):
                result.append(_node_text(child, source))
    return result


def _extract_modifiers(node: Node, source: bytes) -> list[str]:
    """Extract modifiers (public, static, final, abstract, etc.)."""
    mods = _find_child_by_type(node, "modifiers")
    if not mods:
        return []
    return [_node_text(c, source) for c in mods.children if c.type != "marker_annotation"]


def _extract_signature(node: Node, source: bytes) -> str:
    text = _node_text(node, source)
    for marker in ("{", ";"):
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx]
    return text.strip().replace("\n", " ").replace("\r", "")[:500]


def _extract_parameters(node: Node, source: bytes) -> list[str]:
    params_node = _find_child_by_type(node, "formal_parameters")
    if not params_node:
        return []
    result: list[str] = []
    for child in params_node.children:
        if child.type == "formal_parameter":
            type_node = child.child_by_field_name("type")
            name_node = child.child_by_field_name("name")
            t = _node_text(type_node, source) if type_node else ""
            n = _node_text(name_node, source) if name_node else ""
            result.append(f"{t} {n}".strip())
        elif child.type == "spread_parameter":
            result.append(_node_text(child, source))
    return result


def _extract_return_type(node: Node, source: bytes) -> str:
    type_node = node.child_by_field_name("type")
    if type_node:
        return _node_text(type_node, source)
    return ""


def _extract_doc_comment(node: Node, source: bytes) -> str:
    """Extract Javadoc comment preceding a declaration."""
    prev = node.prev_named_sibling
    if prev and prev.type in ("block_comment", "comment"):
        text = _node_text(prev, source)
        if text.startswith("/**"):
            return text
    return ""


def _extract_invocation_target(node: Node, source: bytes) -> str:
    name_node = node.child_by_field_name("name")
    if name_node:
        return _node_text(name_node, source)
    obj = node.child_by_field_name("object")
    if obj:
        return _node_text(obj, source)
    return ""


# ------------------------------------------------------------------
# Generic tree-sitter utilities
# ------------------------------------------------------------------


def _walk(node: Node):  # type: ignore[no-untyped-def]
    cursor = node.walk()
    visited = False
    while True:
        if not visited:
            yield cursor.node
            if cursor.goto_first_child():
                continue
        if cursor.goto_next_sibling():
            visited = False
            continue
        if not cursor.goto_parent():
            break
        visited = True


def _node_text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _find_child_by_type(node: Node, type_name: str) -> Node | None:
    for child in node.children:
        if child.type == type_name:
            return child
    return None


def _get_declaration_name(node: Node, source: bytes) -> str:
    name_node = node.child_by_field_name("name")
    if name_node:
        return _node_text(name_node, source)
    ident = _find_child_by_type(node, "identifier")
    if ident:
        return _node_text(ident, source)
    return "<unknown>"


def _get_member_name(node: Node, kind: SymbolKind, source: bytes, parent_fq: str) -> str:
    if kind == SymbolKind.CONSTRUCTOR:
        name_node = node.child_by_field_name("name")
        if name_node:
            return _node_text(name_node, source)
        return parent_fq.rsplit(".", 1)[-1] if "." in parent_fq else parent_fq

    name_node = node.child_by_field_name("name")
    if name_node:
        return _node_text(name_node, source)

    if kind == SymbolKind.FIELD:
        decl = _find_child_by_type(node, "variable_declarator")
        if decl:
            ident = decl.child_by_field_name("name") or _find_child_by_type(decl, "identifier")
            if ident:
                return _node_text(ident, source)
    return ""

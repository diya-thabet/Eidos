"""
Go parser using tree-sitter.

Extracts symbols (structs, interfaces, functions, methods, fields)
and edges (calls, implements, imports, containment) from Go source files.
"""

from __future__ import annotations

import logging
from pathlib import Path

import tree_sitter_go as tsgo
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

GO_LANGUAGE = Language(tsgo.language())


class GoParser(LanguageParser):
    """Go source parser built on tree-sitter."""

    @property
    def language_id(self) -> str:
        return "go"

    def parse_file(self, source: bytes, file_path: str) -> FileAnalysis:
        return parse_file(source, file_path)


def create_parser() -> Parser:
    return Parser(GO_LANGUAGE)


def parse_file(source: bytes, file_path: str) -> FileAnalysis:
    """Parse a single Go source file."""
    parser = create_parser()
    tree = parser.parse(source)
    root = tree.root_node

    pkg = _extract_package(root, source)
    analysis = FileAnalysis(path=file_path, namespace=pkg)
    analysis.using_directives = _extract_imports(root, source)

    for imp in analysis.using_directives:
        analysis.edges.append(
            EdgeInfo(
                source_fq_name=pkg or file_path,
                target_fq_name=imp,
                edge_type=EdgeType.IMPORTS,
                file_path=file_path,
            )
        )

    _extract_top_level(root, source, file_path, analysis, pkg)
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
        if child.type == "package_clause":
            ident = _find_child_by_type(child, "package_identifier")
            if ident:
                return _node_text(ident, source)
    return ""


def _extract_imports(root: Node, source: bytes) -> list[str]:
    imports: list[str] = []
    for child in root.children:
        if child.type == "import_declaration":
            for cc in child.children:
                if cc.type == "import_spec":
                    _add_import_path(cc, source, imports)
                elif cc.type == "import_spec_list":
                    for spec in cc.children:
                        if spec.type == "import_spec":
                            _add_import_path(spec, source, imports)
    return imports


def _add_import_path(spec: Node, source: bytes, imports: list[str]) -> None:
    path_node = spec.child_by_field_name("path")
    if path_node:
        text = _node_text(path_node, source).strip('"')
        imports.append(text)


# ------------------------------------------------------------------
# Top-level declarations
# ------------------------------------------------------------------


def _extract_top_level(
    root: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    pkg: str,
) -> None:
    for child in root.children:
        if child.type == "type_declaration":
            _extract_type_declaration(child, source, file_path, analysis, pkg)
        elif child.type == "function_declaration":
            _extract_function(child, source, file_path, analysis, pkg)
        elif child.type == "method_declaration":
            _extract_method(child, source, file_path, analysis, pkg)


# ------------------------------------------------------------------
# Type declarations (struct, interface, type alias)
# ------------------------------------------------------------------


def _extract_type_declaration(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    pkg: str,
) -> None:
    for child in node.children:
        if child.type != "type_spec":
            continue
        name_node = child.child_by_field_name("name")
        type_node = child.child_by_field_name("type")
        if not name_node or not type_node:
            continue
        name = _node_text(name_node, source)
        fq = f"{pkg}.{name}" if pkg else name

        if type_node.type == "struct_type":
            _extract_struct(name, fq, type_node, node, source, file_path, analysis, pkg)
        elif type_node.type == "interface_type":
            _extract_interface(name, fq, type_node, node, source, file_path, analysis, pkg)
        else:
            # type alias (e.g. type Status int)
            analysis.symbols.append(
                SymbolInfo(
                    name=name,
                    kind=SymbolKind.CLASS,
                    fq_name=fq,
                    file_path=file_path,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    namespace=pkg,
                )
            )


def _extract_struct(
    name: str,
    fq: str,
    type_node: Node,
    decl_node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    pkg: str,
) -> None:
    symbol = SymbolInfo(
        name=name,
        kind=SymbolKind.STRUCT,
        fq_name=fq,
        file_path=file_path,
        start_line=decl_node.start_point[0] + 1,
        end_line=decl_node.end_point[0] + 1,
        namespace=pkg,
        doc_comment=_extract_doc_comment(decl_node, source),
    )
    analysis.symbols.append(symbol)

    field_list = _find_child_by_type(type_node, "field_declaration_list")
    if field_list:
        for child in field_list.children:
            if child.type == "field_declaration":
                fn = child.child_by_field_name("name")
                ft = child.child_by_field_name("type")
                if fn:
                    fname = _node_text(fn, source)
                    ffq = f"{fq}.{fname}"
                    analysis.symbols.append(
                        SymbolInfo(
                            name=fname,
                            kind=SymbolKind.FIELD,
                            fq_name=ffq,
                            file_path=file_path,
                            start_line=child.start_point[0] + 1,
                            end_line=child.end_point[0] + 1,
                            namespace=pkg,
                            parent_fq_name=fq,
                            return_type=_node_text(ft, source) if ft else "",
                        )
                    )
                    analysis.edges.append(
                        EdgeInfo(
                            source_fq_name=fq,
                            target_fq_name=ffq,
                            edge_type=EdgeType.CONTAINS,
                            file_path=file_path,
                            line=child.start_point[0] + 1,
                        )
                    )


def _extract_interface(
    name: str,
    fq: str,
    type_node: Node,
    decl_node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    pkg: str,
) -> None:
    symbol = SymbolInfo(
        name=name,
        kind=SymbolKind.INTERFACE,
        fq_name=fq,
        file_path=file_path,
        start_line=decl_node.start_point[0] + 1,
        end_line=decl_node.end_point[0] + 1,
        namespace=pkg,
        doc_comment=_extract_doc_comment(decl_node, source),
    )
    analysis.symbols.append(symbol)

    for child in type_node.children:
        if child.type == "method_elem":
            mn = child.child_by_field_name("name")
            if mn:
                mname = _node_text(mn, source)
                mfq = f"{fq}.{mname}"
                analysis.symbols.append(
                    SymbolInfo(
                        name=mname,
                        kind=SymbolKind.METHOD,
                        fq_name=mfq,
                        file_path=file_path,
                        start_line=child.start_point[0] + 1,
                        end_line=child.end_point[0] + 1,
                        namespace=pkg,
                        parent_fq_name=fq,
                        parameters=_extract_parameters(child, source),
                    )
                )
                analysis.edges.append(
                    EdgeInfo(
                        source_fq_name=fq,
                        target_fq_name=mfq,
                        edge_type=EdgeType.CONTAINS,
                        file_path=file_path,
                        line=child.start_point[0] + 1,
                    )
                )


# ------------------------------------------------------------------
# Functions (top-level)
# ------------------------------------------------------------------


def _extract_function(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    pkg: str,
) -> None:
    name = _get_name(node, source)
    fq = f"{pkg}.{name}" if pkg else name

    analysis.symbols.append(
        SymbolInfo(
            name=name,
            kind=SymbolKind.METHOD,
            fq_name=fq,
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            namespace=pkg,
            signature=_extract_signature(node, source),
            parameters=_extract_parameters(node, source),
            return_type=_extract_result_type(node, source),
            doc_comment=_extract_doc_comment(node, source),
        )
    )

    body = node.child_by_field_name("body")
    if body:
        _extract_calls(body, source, file_path, analysis, fq)


# ------------------------------------------------------------------
# Methods (with receiver)
# ------------------------------------------------------------------


def _extract_method(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    pkg: str,
) -> None:
    name = _get_name(node, source)
    receiver_type = _extract_receiver_type(node, source)
    parent_fq = f"{pkg}.{receiver_type}" if pkg and receiver_type else receiver_type
    fq = f"{parent_fq}.{name}" if parent_fq else name

    analysis.symbols.append(
        SymbolInfo(
            name=name,
            kind=SymbolKind.METHOD,
            fq_name=fq,
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            namespace=pkg,
            parent_fq_name=parent_fq,
            signature=_extract_signature(node, source),
            parameters=_extract_parameters(node, source),
            return_type=_extract_result_type(node, source),
            doc_comment=_extract_doc_comment(node, source),
        )
    )

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

    body = node.child_by_field_name("body")
    if body:
        _extract_calls(body, source, file_path, analysis, fq)


# ------------------------------------------------------------------
# Call extraction
# ------------------------------------------------------------------


def _extract_calls(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    caller_fq: str,
) -> None:
    for child in _walk(node):
        if child.type == "call_expression":
            target = _extract_call_target(child, source)
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


# ------------------------------------------------------------------
# Go-specific helpers
# ------------------------------------------------------------------


def _extract_receiver_type(node: Node, source: bytes) -> str:
    """Extract the receiver type from a method_declaration."""
    receiver = node.child_by_field_name("receiver")
    if not receiver:
        return ""
    # receiver is a parameter_list containing a parameter_declaration
    for child in receiver.children:
        if child.type == "parameter_declaration":
            tp = child.child_by_field_name("type")
            if tp:
                text = _node_text(tp, source)
                return text.lstrip("*")
    return ""


def _extract_parameters(node: Node, source: bytes) -> list[str]:
    params = node.child_by_field_name("parameters")
    if not params:
        return []
    result: list[str] = []
    for child in params.children:
        if child.type == "parameter_declaration":
            name_node = child.child_by_field_name("name")
            type_node = child.child_by_field_name("type")
            n = _node_text(name_node, source) if name_node else ""
            t = _node_text(type_node, source) if type_node else ""
            result.append(f"{n} {t}".strip())
    return result


def _extract_result_type(node: Node, source: bytes) -> str:
    result = node.child_by_field_name("result")
    if result:
        return _node_text(result, source)
    return ""


def _extract_signature(node: Node, source: bytes) -> str:
    text = _node_text(node, source)
    idx = text.find("{")
    if idx != -1:
        text = text[:idx]
    return text.strip().replace("\n", " ").replace("\r", "")[:500]


def _extract_doc_comment(node: Node, source: bytes) -> str:
    prev = node.prev_named_sibling
    if prev and prev.type == "comment":
        text = _node_text(prev, source)
        if text.startswith("//"):
            return text
    return ""


def _extract_call_target(node: Node, source: bytes) -> str:
    func = node.child_by_field_name("function")
    if func is None:
        return ""
    if func.type == "identifier":
        return _node_text(func, source)
    if func.type == "selector_expression":
        field = func.child_by_field_name("field")
        if field:
            return _node_text(field, source)
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


def _get_name(node: Node, source: bytes) -> str:
    name_node = node.child_by_field_name("name")
    if name_node:
        return _node_text(name_node, source)
    return "<unknown>"

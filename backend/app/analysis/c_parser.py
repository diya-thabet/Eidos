"""
C parser using tree-sitter.

Extracts symbols (structs, enums, functions, fields, typedefs)
and edges (calls, imports/includes, containment) from C source files.
"""

from __future__ import annotations

import logging

import tree_sitter_c as tsc
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

C_LANGUAGE = Language(tsc.language())


class CParser(LanguageParser):
    """C source parser built on tree-sitter."""

    @property
    def language_id(self) -> str:
        return "c"

    def parse_file(self, source: bytes, file_path: str) -> FileAnalysis:
        return parse_file(source, file_path)


def create_parser() -> Parser:
    return Parser(C_LANGUAGE)


def parse_file(source: bytes, file_path: str) -> FileAnalysis:
    parser = create_parser()
    tree = parser.parse(source)
    root = tree.root_node

    module = file_path.replace("/", ".").replace("\\", ".")
    for suffix in (".c", ".h"):
        if module.endswith(suffix):
            module = module[: -len(suffix)]
            break

    analysis = FileAnalysis(path=file_path, namespace=module)
    analysis.using_directives = _extract_includes(root, source)

    for inc in analysis.using_directives:
        analysis.edges.append(
            EdgeInfo(
                source_fq_name=module,
                target_fq_name=inc,
                edge_type=EdgeType.IMPORTS,
                file_path=file_path,
            )
        )

    _extract_top_level(root, source, file_path, analysis, module)
    return analysis


# ------------------------------------------------------------------
# Includes
# ------------------------------------------------------------------


def _extract_includes(root: Node, source: bytes) -> list[str]:
    result: list[str] = []
    for child in root.children:
        if child.type == "preproc_include":
            path = child.child_by_field_name("path")
            if path:
                result.append(_node_text(path, source).strip('<>"'))
    return result


# ------------------------------------------------------------------
# Top-level
# ------------------------------------------------------------------


def _extract_top_level(
    root: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
) -> None:
    for child in root.children:
        if child.type == "struct_specifier":
            _extract_struct(child, source, file_path, analysis, module)
        elif child.type == "enum_specifier":
            _extract_enum(child, source, file_path, analysis, module)
        elif child.type == "function_definition":
            _extract_function(child, source, file_path, analysis, module)
        elif child.type == "type_definition":
            _extract_typedef(child, source, file_path, analysis, module)
        elif child.type == "declaration":
            # Forward declarations / function prototypes
            pass


# ------------------------------------------------------------------
# Struct
# ------------------------------------------------------------------


def _extract_struct(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
) -> None:
    name = _get_name(node, source)
    if not name or name == "<unknown>":
        return
    fq = f"{module}.{name}" if module else name

    analysis.symbols.append(
        SymbolInfo(
            name=name,
            kind=SymbolKind.STRUCT,
            fq_name=fq,
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            namespace=module,
            doc_comment=_extract_doc_comment(node, source),
        )
    )

    body = node.child_by_field_name("body")
    if body:
        _extract_fields(body, source, file_path, analysis, module, fq)


# ------------------------------------------------------------------
# Enum
# ------------------------------------------------------------------


def _extract_enum(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
) -> None:
    name = _get_name(node, source)
    if not name or name == "<unknown>":
        return
    fq = f"{module}.{name}" if module else name

    analysis.symbols.append(
        SymbolInfo(
            name=name,
            kind=SymbolKind.ENUM,
            fq_name=fq,
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            namespace=module,
        )
    )


# ------------------------------------------------------------------
# Function
# ------------------------------------------------------------------


def _extract_function(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
) -> None:
    decl = node.child_by_field_name("declarator")
    ret_type = node.child_by_field_name("type")
    if not decl:
        return

    name = _get_function_name(decl, source)
    if not name:
        return
    fq = f"{module}.{name}" if module else name

    modifiers: list[str] = []
    # Check for static
    for child in node.children:
        if child.type == "storage_class_specifier":
            modifiers.append(_node_text(child, source))

    analysis.symbols.append(
        SymbolInfo(
            name=name,
            kind=SymbolKind.METHOD,
            fq_name=fq,
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            namespace=module,
            modifiers=modifiers,
            signature=_extract_signature(node, source),
            parameters=_extract_parameters(decl, source),
            return_type=_node_text(ret_type, source) if ret_type else "",
            doc_comment=_extract_doc_comment(node, source),
        )
    )

    body = node.child_by_field_name("body")
    if body:
        _extract_calls(body, source, file_path, analysis, fq)


# ------------------------------------------------------------------
# Typedef
# ------------------------------------------------------------------


def _extract_typedef(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
) -> None:
    decl = node.child_by_field_name("declarator")
    type_node = node.child_by_field_name("type")
    if not decl:
        return
    name = _node_text(decl, source)
    fq = f"{module}.{name}" if module else name

    # If the underlying type is a struct, extract it as STRUCT
    kind = SymbolKind.CLASS
    if type_node and type_node.type == "struct_specifier":
        kind = SymbolKind.STRUCT
        # Also extract fields from the anonymous struct
        body = type_node.child_by_field_name("body")
        analysis.symbols.append(
            SymbolInfo(
                name=name,
                kind=kind,
                fq_name=fq,
                file_path=file_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                namespace=module,
            )
        )
        if body:
            _extract_fields(body, source, file_path, analysis, module, fq)
        return

    analysis.symbols.append(
        SymbolInfo(
            name=name,
            kind=kind,
            fq_name=fq,
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            namespace=module,
        )
    )


# ------------------------------------------------------------------
# Fields
# ------------------------------------------------------------------


def _extract_fields(
    body: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
    parent_fq: str,
) -> None:
    for child in body.children:
        if child.type == "field_declaration":
            decl = child.child_by_field_name("declarator")
            tp = child.child_by_field_name("type")
            if not decl:
                continue
            # Unwrap pointer declarators
            fname = _node_text(decl, source).lstrip("* ")
            ffq = f"{parent_fq}.{fname}"
            analysis.symbols.append(
                SymbolInfo(
                    name=fname,
                    kind=SymbolKind.FIELD,
                    fq_name=ffq,
                    file_path=file_path,
                    start_line=child.start_point[0] + 1,
                    end_line=child.end_point[0] + 1,
                    namespace=module,
                    parent_fq_name=parent_fq,
                    return_type=_node_text(tp, source) if tp else "",
                )
            )
            analysis.edges.append(
                EdgeInfo(
                    source_fq_name=parent_fq,
                    target_fq_name=ffq,
                    edge_type=EdgeType.CONTAINS,
                    file_path=file_path,
                    line=child.start_point[0] + 1,
                )
            )


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


def _extract_call_target(node: Node, source: bytes) -> str:
    func = node.child_by_field_name("function")
    if func is None:
        return ""
    if func.type == "identifier":
        return _node_text(func, source)
    if func.type == "field_expression":
        field = func.child_by_field_name("field")
        if field:
            return _node_text(field, source)
    return ""


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _get_function_name(decl: Node, source: bytes) -> str:
    # function_declarator -> declarator (identifier) + parameters
    fn = decl.child_by_field_name("declarator")
    if fn:
        return _node_text(fn, source)
    # Fallback: first identifier child
    for child in decl.children:
        if child.type == "identifier":
            return _node_text(child, source)
    return ""


def _extract_parameters(decl: Node, source: bytes) -> list[str]:
    params = decl.child_by_field_name("parameters")
    if not params:
        return []
    result: list[str] = []
    for child in params.children:
        if child.type == "parameter_declaration":
            pn = child.child_by_field_name("declarator")
            pt = child.child_by_field_name("type")
            n = _node_text(pn, source) if pn else ""
            t = _node_text(pt, source) if pt else ""
            result.append(f"{t} {n}".strip())
    return result


def _extract_signature(node: Node, source: bytes) -> str:
    text = _node_text(node, source)
    idx = text.find("{")
    if idx != -1:
        text = text[:idx]
    return text.strip().replace("\n", " ")[:500]


def _extract_doc_comment(node: Node, source: bytes) -> str:
    prev = node.prev_named_sibling
    if prev and prev.type == "comment":
        text = _node_text(prev, source)
        if text.startswith("/**") or text.startswith("///"):
            return text
    return ""


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


def _get_name(node: Node, source: bytes) -> str:
    name_node = node.child_by_field_name("name")
    if name_node:
        return _node_text(name_node, source)
    return "<unknown>"

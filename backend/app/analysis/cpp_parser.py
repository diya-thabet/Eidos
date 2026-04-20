"""
C++ parser using tree-sitter.

Extracts symbols (classes, structs, enums, namespaces, functions, methods,
constructors, destructors, fields) and edges (calls, inherits, imports,
containment) from C++ source files.
"""

from __future__ import annotations

import logging

import tree_sitter_cpp as tscpp
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

CPP_LANGUAGE = Language(tscpp.language())


class CppParser(LanguageParser):
    """C++ source parser built on tree-sitter."""

    @property
    def language_id(self) -> str:
        return "cpp"

    def parse_file(self, source: bytes, file_path: str) -> FileAnalysis:
        return parse_file(source, file_path)


def create_parser() -> Parser:
    return Parser(CPP_LANGUAGE)


def parse_file(source: bytes, file_path: str) -> FileAnalysis:
    parser = create_parser()
    tree = parser.parse(source)
    root = tree.root_node

    module = file_path.replace("/", ".").replace("\\", ".")
    for suffix in (".cpp", ".cc", ".cxx", ".hpp", ".hxx", ".h"):
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
        _dispatch(child, source, file_path, analysis, module, None)


def _dispatch(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
    parent_fq: str | None,
) -> None:
    if node.type == "namespace_definition":
        _extract_namespace(node, source, file_path, analysis, module, parent_fq)
    elif node.type in ("class_specifier", "struct_specifier"):
        _extract_class_or_struct(node, source, file_path, analysis, module, parent_fq)
    elif node.type == "enum_specifier":
        _extract_enum(node, source, file_path, analysis, module, parent_fq)
    elif node.type == "function_definition":
        _extract_function(node, source, file_path, analysis, module, parent_fq)
    elif node.type == "template_declaration":
        # Unwrap template to get inner declaration
        for child in node.children:
            _dispatch(child, source, file_path, analysis, module, parent_fq)


# ------------------------------------------------------------------
# Namespace
# ------------------------------------------------------------------


def _extract_namespace(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
    parent_fq: str | None,
) -> None:
    name = _get_name(node, source)
    if name == "<unknown>":
        name = ""
    fq = _make_fq(module, parent_fq, name) if name else (parent_fq or module)

    if name:
        analysis.symbols.append(
            SymbolInfo(
                name=name,
                kind=SymbolKind.NAMESPACE,
                fq_name=fq,
                file_path=file_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                namespace=module,
                parent_fq_name=parent_fq,
            )
        )

    body = node.child_by_field_name("body")
    if body:
        for child in body.children:
            _dispatch(child, source, file_path, analysis, module, fq)


# ------------------------------------------------------------------
# Class / Struct
# ------------------------------------------------------------------


def _extract_class_or_struct(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
    parent_fq: str | None,
) -> None:
    name = _get_name(node, source)
    if name == "<unknown>":
        return
    fq = _make_fq(module, parent_fq, name)
    kind = SymbolKind.CLASS if node.type == "class_specifier" else SymbolKind.STRUCT

    bases = _extract_bases(node, source)

    analysis.symbols.append(
        SymbolInfo(
            name=name,
            kind=kind,
            fq_name=fq,
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            namespace=module,
            parent_fq_name=parent_fq,
            base_types=bases,
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

    for base in bases:
        analysis.edges.append(
            EdgeInfo(
                source_fq_name=fq,
                target_fq_name=base,
                edge_type=EdgeType.INHERITS,
                file_path=file_path,
                line=node.start_point[0] + 1,
            )
        )

    body = node.child_by_field_name("body")
    if body:
        _extract_class_body(body, source, file_path, analysis, module, fq, name)


def _extract_class_body(
    body: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
    parent_fq: str,
    class_name: str,
) -> None:
    for child in body.children:
        if child.type == "function_definition":
            _extract_method(child, source, file_path, analysis, module, parent_fq, class_name)
        elif child.type == "field_declaration":
            _extract_field_decl(child, source, file_path, analysis, module, parent_fq)
        elif child.type == "declaration":
            # Pure virtual / declared methods
            _extract_field_decl(child, source, file_path, analysis, module, parent_fq)
        elif child.type == "template_declaration":
            for sub in child.children:
                if sub.type == "function_definition":
                    _extract_method(sub, source, file_path, analysis, module, parent_fq, class_name)


# ------------------------------------------------------------------
# Enum
# ------------------------------------------------------------------


def _extract_enum(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
    parent_fq: str | None,
) -> None:
    name = _get_name(node, source)
    if name == "<unknown>":
        return
    fq = _make_fq(module, parent_fq, name)

    analysis.symbols.append(
        SymbolInfo(
            name=name,
            kind=SymbolKind.ENUM,
            fq_name=fq,
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            namespace=module,
            parent_fq_name=parent_fq,
        )
    )


# ------------------------------------------------------------------
# Functions (free)
# ------------------------------------------------------------------


def _extract_function(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
    parent_fq: str | None,
) -> None:
    decl = node.child_by_field_name("declarator")
    ret_type = node.child_by_field_name("type")
    if not decl:
        return
    name = _get_function_name(decl, source)
    if not name:
        return
    fq = _make_fq(module, parent_fq, name)

    analysis.symbols.append(
        SymbolInfo(
            name=name,
            kind=SymbolKind.METHOD,
            fq_name=fq,
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            namespace=module,
            parent_fq_name=parent_fq,
            signature=_extract_signature(node, source),
            parameters=_extract_parameters(decl, source),
            return_type=_node_text(ret_type, source) if ret_type else "",
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
# Methods (inside class)
# ------------------------------------------------------------------


def _extract_method(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
    parent_fq: str,
    class_name: str,
) -> None:
    decl = node.child_by_field_name("declarator")
    ret_type = node.child_by_field_name("type")
    if not decl:
        return
    name = _get_function_name(decl, source)
    if not name:
        return

    # Detect constructor / destructor
    if name == class_name:
        kind = SymbolKind.CONSTRUCTOR
    elif name.startswith("~"):
        kind = SymbolKind.METHOD
        name = name  # keep destructor name
    else:
        kind = SymbolKind.METHOD

    fq = f"{parent_fq}.{name}"

    analysis.symbols.append(
        SymbolInfo(
            name=name,
            kind=kind,
            fq_name=fq,
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            namespace=module,
            parent_fq_name=parent_fq,
            signature=_extract_signature(node, source),
            parameters=_extract_parameters(decl, source),
            return_type=_node_text(ret_type, source) if ret_type else "",
        )
    )

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
# Fields
# ------------------------------------------------------------------


def _extract_field_decl(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
    parent_fq: str,
) -> None:
    decl = node.child_by_field_name("declarator")
    tp = node.child_by_field_name("type")
    if not decl:
        return

    # Check if it's a method declaration (function_declarator)
    is_method = decl.type == "function_declarator"
    if is_method:
        name = _get_function_name(decl, source)
        if not name:
            return
        fq = f"{parent_fq}.{name}"
        analysis.symbols.append(
            SymbolInfo(
                name=name,
                kind=SymbolKind.METHOD,
                fq_name=fq,
                file_path=file_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                namespace=module,
                parent_fq_name=parent_fq,
                parameters=_extract_parameters(decl, source),
                return_type=_node_text(tp, source) if tp else "",
            )
        )
        analysis.edges.append(
            EdgeInfo(
                source_fq_name=parent_fq,
                target_fq_name=fq,
                edge_type=EdgeType.CONTAINS,
                file_path=file_path,
                line=node.start_point[0] + 1,
            )
        )
        return

    name = _node_text(decl, source).lstrip("* ")
    if not name or name.startswith("("):
        return
    fq = f"{parent_fq}.{name}"

    analysis.symbols.append(
        SymbolInfo(
            name=name,
            kind=SymbolKind.FIELD,
            fq_name=fq,
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            namespace=module,
            parent_fq_name=parent_fq,
            return_type=_node_text(tp, source) if tp else "",
        )
    )
    analysis.edges.append(
        EdgeInfo(
            source_fq_name=parent_fq,
            target_fq_name=fq,
            edge_type=EdgeType.CONTAINS,
            file_path=file_path,
            line=node.start_point[0] + 1,
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
        elif child.type == "new_expression":
            tp = child.child_by_field_name("type")
            if tp:
                analysis.edges.append(
                    EdgeInfo(
                        source_fq_name=caller_fq,
                        target_fq_name=_node_text(tp, source),
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
    if func.type == "qualified_identifier":
        name = func.child_by_field_name("name")
        if name:
            return _node_text(name, source)
    return ""


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _extract_bases(node: Node, source: bytes) -> list[str]:
    bases: list[str] = []
    for child in node.children:
        if child.type == "base_class_clause":
            for sub in child.children:
                if sub.type == "type_identifier":
                    bases.append(_node_text(sub, source))
    return bases


def _make_fq(module: str, parent_fq: str | None, name: str) -> str:
    if parent_fq:
        return f"{parent_fq}.{name}"
    if module:
        return f"{module}.{name}"
    return name


def _get_function_name(decl: Node, source: bytes) -> str:
    fn = decl.child_by_field_name("declarator")
    if fn:
        text = _node_text(fn, source)
        return text.split("(")[0].strip()
    for child in decl.children:
        if child.type in ("identifier", "destructor_name", "field_identifier"):
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

"""
Rust parser using tree-sitter.

Extracts symbols (structs, traits, enums, functions, impl methods, fields)
and edges (calls, implements, imports, containment) from Rust source files.
"""

from __future__ import annotations

import logging
from pathlib import Path

import tree_sitter_rust as tsrust
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

RUST_LANGUAGE = Language(tsrust.language())


class RustParser(LanguageParser):
    """Rust source parser built on tree-sitter."""

    @property
    def language_id(self) -> str:
        return "rust"

    def parse_file(self, source: bytes, file_path: str) -> FileAnalysis:
        return parse_file(source, file_path)


def create_parser() -> Parser:
    return Parser(RUST_LANGUAGE)


def parse_file(source: bytes, file_path: str) -> FileAnalysis:
    """Parse a single Rust source file."""
    parser = create_parser()
    tree = parser.parse(source)
    root = tree.root_node

    # Derive module from path: src/models/user.rs -> src.models.user
    module = file_path.replace("/", ".").replace("\\", ".")
    if module.endswith(".rs"):
        module = module[:-3]

    analysis = FileAnalysis(path=file_path, namespace=module)
    analysis.using_directives = _extract_uses(root, source)

    for imp in analysis.using_directives:
        analysis.edges.append(
            EdgeInfo(
                source_fq_name=module,
                target_fq_name=imp,
                edge_type=EdgeType.IMPORTS,
                file_path=file_path,
            )
        )

    _extract_top_level(root, source, file_path, analysis, module)
    return analysis


def parse_file_from_path(file_path: Path, repo_root: Path) -> FileAnalysis:
    source = file_path.read_bytes()
    rel_path = file_path.relative_to(repo_root).as_posix()
    return parse_file(source, rel_path)


# ------------------------------------------------------------------
# Use declarations
# ------------------------------------------------------------------


def _extract_uses(root: Node, source: bytes) -> list[str]:
    uses: list[str] = []
    for child in root.children:
        if child.type == "use_declaration":
            arg = child.child_by_field_name("argument")
            if arg:
                uses.append(_node_text(arg, source))
    return uses


# ------------------------------------------------------------------
# Top-level extraction
# ------------------------------------------------------------------


def _extract_top_level(
    root: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
) -> None:
    for child in root.children:
        if child.type == "struct_item":
            _extract_struct(child, source, file_path, analysis, module)
        elif child.type == "trait_item":
            _extract_trait(child, source, file_path, analysis, module)
        elif child.type == "enum_item":
            _extract_enum(child, source, file_path, analysis, module)
        elif child.type == "function_item":
            _extract_function(child, source, file_path, analysis, module, None)
        elif child.type == "impl_item":
            _extract_impl(child, source, file_path, analysis, module)
        elif child.type == "type_item":
            _extract_type_alias(child, source, file_path, analysis, module)
        elif child.type == "mod_item":
            _extract_mod(child, source, file_path, analysis, module)


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
    fq = f"{module}.{name}" if module else name
    mods = _extract_visibility(node, source)

    analysis.symbols.append(
        SymbolInfo(
            name=name,
            kind=SymbolKind.STRUCT,
            fq_name=fq,
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            namespace=module,
            modifiers=mods,
            doc_comment=_extract_doc_comment(node, source),
        )
    )

    body = node.child_by_field_name("body")
    if body:
        for child in body.children:
            if child.type == "field_declaration":
                _extract_field(child, source, file_path, analysis, module, fq)


# ------------------------------------------------------------------
# Trait
# ------------------------------------------------------------------


def _extract_trait(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
) -> None:
    name = _get_name(node, source)
    fq = f"{module}.{name}" if module else name

    analysis.symbols.append(
        SymbolInfo(
            name=name,
            kind=SymbolKind.INTERFACE,
            fq_name=fq,
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            namespace=module,
            modifiers=_extract_visibility(node, source),
            doc_comment=_extract_doc_comment(node, source),
        )
    )

    body = node.child_by_field_name("body")
    if body:
        for child in body.children:
            if child.type == "function_signature_item":
                _extract_trait_method(child, source, file_path, analysis, module, fq)
            elif child.type == "function_item":
                # Default method implementation in trait
                _extract_function(child, source, file_path, analysis, module, fq)


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
            modifiers=_extract_visibility(node, source),
            doc_comment=_extract_doc_comment(node, source),
        )
    )


# ------------------------------------------------------------------
# Impl block
# ------------------------------------------------------------------


def _extract_impl(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
) -> None:
    type_node = node.child_by_field_name("type")
    trait_node = node.child_by_field_name("trait")
    if not type_node:
        return

    type_name = _node_text(type_node, source)
    parent_fq = f"{module}.{type_name}" if module else type_name

    # impl Trait for Type -> IMPLEMENTS edge
    if trait_node:
        trait_name = _node_text(trait_node, source)
        analysis.edges.append(
            EdgeInfo(
                source_fq_name=parent_fq,
                target_fq_name=trait_name,
                edge_type=EdgeType.IMPLEMENTS,
                file_path=file_path,
                line=node.start_point[0] + 1,
            )
        )

    body = node.child_by_field_name("body")
    if body:
        for child in body.children:
            if child.type == "function_item":
                _extract_function(child, source, file_path, analysis, module, parent_fq)


# ------------------------------------------------------------------
# Functions / methods
# ------------------------------------------------------------------


def _extract_function(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
    parent_fq: str | None,
) -> None:
    name = _get_name(node, source)
    fq = f"{parent_fq}.{name}" if parent_fq else (f"{module}.{name}" if module else name)

    kind = SymbolKind.METHOD
    params = _extract_parameters(node, source)

    # Constructor-like: fn new(...) -> Self in an impl block
    if parent_fq and name == "new":
        kind = SymbolKind.CONSTRUCTOR

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
            modifiers=_extract_visibility(node, source),
            signature=_extract_signature(node, source),
            parameters=params,
            return_type=_extract_return_type(node, source),
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


def _extract_trait_method(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
    parent_fq: str,
) -> None:
    name = _get_name(node, source)
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
            parameters=_extract_parameters(node, source),
            return_type=_extract_return_type(node, source),
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
# Fields
# ------------------------------------------------------------------


def _extract_field(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
    parent_fq: str,
) -> None:
    fn = node.child_by_field_name("name")
    ft = node.child_by_field_name("type")
    if not fn:
        return
    name = _node_text(fn, source)
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
            modifiers=_extract_visibility(node, source),
            return_type=_node_text(ft, source) if ft else "",
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
# Type alias and mod
# ------------------------------------------------------------------


def _extract_type_alias(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
) -> None:
    name = _get_name(node, source)
    fq = f"{module}.{name}" if module else name
    analysis.symbols.append(
        SymbolInfo(
            name=name,
            kind=SymbolKind.CLASS,
            fq_name=fq,
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            namespace=module,
        )
    )


def _extract_mod(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
) -> None:
    name = _get_name(node, source)
    fq = f"{module}.{name}" if module else name
    analysis.symbols.append(
        SymbolInfo(
            name=name,
            kind=SymbolKind.NAMESPACE,
            fq_name=fq,
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            namespace=module,
        )
    )
    # Recurse into inline mod body
    body = node.child_by_field_name("body")
    if body:
        for child in body.children:
            if child.type == "struct_item":
                _extract_struct(child, source, file_path, analysis, fq)
            elif child.type == "function_item":
                _extract_function(child, source, file_path, analysis, fq, None)
            elif child.type == "impl_item":
                _extract_impl(child, source, file_path, analysis, fq)
            elif child.type == "trait_item":
                _extract_trait(child, source, file_path, analysis, fq)
            elif child.type == "enum_item":
                _extract_enum(child, source, file_path, analysis, fq)


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
    if func.type == "scoped_identifier":
        name = func.child_by_field_name("name")
        if name:
            return _node_text(name, source)
    return ""


# ------------------------------------------------------------------
# Rust-specific helpers
# ------------------------------------------------------------------


def _extract_visibility(node: Node, source: bytes) -> list[str]:
    for child in node.children:
        if child.type == "visibility_modifier":
            return ["pub"]
    return []


def _extract_parameters(node: Node, source: bytes) -> list[str]:
    params = node.child_by_field_name("parameters")
    if not params:
        return []
    result: list[str] = []
    for child in params.children:
        if child.type == "parameter":
            pat = child.child_by_field_name("pattern")
            tp = child.child_by_field_name("type")
            n = _node_text(pat, source) if pat else ""
            t = _node_text(tp, source) if tp else ""
            result.append(f"{n}: {t}" if t else n)
    return result


def _has_self_param(node: Node, source: bytes) -> bool:
    params = node.child_by_field_name("parameters")
    if not params:
        return False
    for child in params.children:
        if child.type in ("self_parameter", "self"):
            return True
    return False


def _extract_return_type(node: Node, source: bytes) -> str:
    ret = node.child_by_field_name("return_type")
    if ret:
        text = _node_text(ret, source)
        return text.lstrip("-> ").strip()
    return ""


def _extract_signature(node: Node, source: bytes) -> str:
    text = _node_text(node, source)
    idx = text.find("{")
    if idx != -1:
        text = text[:idx]
    return text.strip().replace("\n", " ").replace("\r", "")[:500]


def _extract_doc_comment(node: Node, source: bytes) -> str:
    prev = node.prev_named_sibling
    if prev and prev.type == "line_comment":
        text = _node_text(prev, source)
        if text.startswith("///"):
            return text
    return ""


# ------------------------------------------------------------------
# Generic utilities
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

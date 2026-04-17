"""
C# parser using tree-sitter.

Extracts symbols (classes, methods, interfaces, enums, properties, fields)
and edges (calls, inheritance, using directives) from C# source files.
"""

from __future__ import annotations

import logging
from pathlib import Path

import tree_sitter_c_sharp as tscsharp
from tree_sitter import Language, Node, Parser

from app.analysis.models import (
    EdgeInfo,
    EdgeType,
    FileAnalysis,
    SymbolInfo,
    SymbolKind,
)

logger = logging.getLogger(__name__)

CS_LANGUAGE = Language(tscsharp.language())

# Map tree-sitter node types to our SymbolKind
_TYPE_DECLARATION_MAP: dict[str, SymbolKind] = {
    "class_declaration": SymbolKind.CLASS,
    "interface_declaration": SymbolKind.INTERFACE,
    "struct_declaration": SymbolKind.STRUCT,
    "enum_declaration": SymbolKind.ENUM,
    "record_declaration": SymbolKind.RECORD,
    "delegate_declaration": SymbolKind.DELEGATE,
}

_MEMBER_DECLARATION_MAP: dict[str, SymbolKind] = {
    "method_declaration": SymbolKind.METHOD,
    "constructor_declaration": SymbolKind.CONSTRUCTOR,
    "property_declaration": SymbolKind.PROPERTY,
    "field_declaration": SymbolKind.FIELD,
}


def create_parser() -> Parser:
    """Create a tree-sitter parser configured for C#."""
    parser = Parser(CS_LANGUAGE)
    return parser


def parse_file(source: bytes, file_path: str) -> FileAnalysis:
    """
    Parse a single C# source file and extract symbols + edges.

    Args:
        source: Raw file content as bytes.
        file_path: Relative path of the file (for references).

    Returns:
        FileAnalysis with all extracted symbols and edges.
    """
    parser = create_parser()
    tree = parser.parse(source)
    root = tree.root_node

    analysis = FileAnalysis(path=file_path, namespace="")
    analysis.using_directives = _extract_using_directives(root, source)
    _extract_namespace_and_types(
        root, source, file_path, analysis, parent_namespace="", parent_fq_name=None
    )

    # Build import edges from using directives
    for directive in analysis.using_directives:
        analysis.edges.append(
            EdgeInfo(
                source_fq_name=analysis.namespace or file_path,
                target_fq_name=directive,
                edge_type=EdgeType.IMPORTS,
                file_path=file_path,
            )
        )

    return analysis


def parse_file_from_path(file_path: Path, repo_root: Path) -> FileAnalysis:
    """Convenience: read a file and parse it."""
    source = file_path.read_bytes()
    rel_path = file_path.relative_to(repo_root).as_posix()
    return parse_file(source, rel_path)


# ---------------------------------------------------------------------------
# Internal extraction helpers
# ---------------------------------------------------------------------------


def _extract_using_directives(root: Node, source: bytes) -> list[str]:
    """Extract all 'using Foo.Bar;' directives from file root."""
    directives: list[str] = []
    for node in root.children:
        if node.type == "using_directive":
            # Try qualified_name first, then identifier
            name_node = (
                _find_child_by_type(node, "qualified_name")
                or _find_child_by_type(node, "identifier")
                or node.child_by_field_name("name")
            )
            if name_node:
                directives.append(_node_text(name_node, source))
    return directives


def _extract_namespace_and_types(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    parent_namespace: str,
    parent_fq_name: str | None,
) -> None:
    """Recursively walk the AST to find namespaces, type declarations, and members."""
    for child in node.children:
        # Namespace declarations (both block-scoped and file-scoped)
        if child.type in ("namespace_declaration", "file_scoped_namespace_declaration"):
            ns_name = _get_declaration_name(child, source)
            full_ns = f"{parent_namespace}.{ns_name}" if parent_namespace else ns_name
            if not analysis.namespace:
                analysis.namespace = full_ns
            _extract_namespace_and_types(
                child, source, file_path, analysis, full_ns, parent_fq_name
            )

        # declaration_list inside namespace
        elif child.type == "declaration_list":
            _extract_namespace_and_types(
                child, source, file_path, analysis, parent_namespace, parent_fq_name
            )

        # Type declarations (class, interface, struct, enum, record, delegate)
        elif child.type in _TYPE_DECLARATION_MAP:
            _extract_type_declaration(
                child, source, file_path, analysis, parent_namespace, parent_fq_name
            )


def _extract_type_declaration(
    child: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    parent_namespace: str,
    parent_fq_name: str | None,
) -> None:
    """Extract a type declaration and its members."""
    kind = _TYPE_DECLARATION_MAP[child.type]
    name = _get_declaration_name(child, source)

    if parent_fq_name:
        fq = f"{parent_fq_name}.{name}"
    elif parent_namespace:
        fq = f"{parent_namespace}.{name}"
    else:
        fq = name

    symbol = SymbolInfo(
        name=name,
        kind=kind,
        fq_name=fq,
        file_path=file_path,
        start_line=child.start_point[0] + 1,
        end_line=child.end_point[0] + 1,
        namespace=parent_namespace,
        parent_fq_name=parent_fq_name,
        modifiers=_extract_modifiers(child, source),
        base_types=_extract_base_types(child, source),
        doc_comment=_extract_doc_comment(child, source),
    )
    analysis.symbols.append(symbol)

    # Add containment edge if nested
    if parent_fq_name:
        analysis.edges.append(
            EdgeInfo(
                source_fq_name=parent_fq_name,
                target_fq_name=fq,
                edge_type=EdgeType.CONTAINS,
                file_path=file_path,
                line=child.start_point[0] + 1,
            )
        )

    # Add inheritance / implements edges
    for base in symbol.base_types:
        edge_type = EdgeType.IMPLEMENTS if kind == SymbolKind.CLASS else EdgeType.INHERITS
        analysis.edges.append(
            EdgeInfo(
                source_fq_name=fq,
                target_fq_name=base,
                edge_type=edge_type,
                file_path=file_path,
                line=child.start_point[0] + 1,
            )
        )

    # Recurse into the type body for members and nested types
    body = _find_child_by_type(child, "declaration_list")
    if body:
        _extract_members(body, source, file_path, analysis, parent_namespace, fq)
        # Look for nested type declarations
        for nested in body.children:
            if nested.type in _TYPE_DECLARATION_MAP:
                _extract_type_declaration(nested, source, file_path, analysis, parent_namespace, fq)


def _extract_members(
    body: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    namespace: str,
    parent_fq_name: str,
) -> None:
    """Extract methods, constructors, properties, and fields from a type body."""
    for child in body.children:
        if child.type not in _MEMBER_DECLARATION_MAP:
            continue

        kind = _MEMBER_DECLARATION_MAP[child.type]
        name = _get_member_name(child, kind, source, parent_fq_name)
        if not name:
            continue

        fq = f"{parent_fq_name}.{name}"

        symbol = SymbolInfo(
            name=name,
            kind=kind,
            fq_name=fq,
            file_path=file_path,
            start_line=child.start_point[0] + 1,
            end_line=child.end_point[0] + 1,
            namespace=namespace,
            parent_fq_name=parent_fq_name,
            modifiers=_extract_modifiers(child, source),
            signature=_extract_signature(child, source),
            parameters=_extract_parameters(child, source),
            return_type=_extract_return_type(child, source),
            doc_comment=_extract_doc_comment(child, source),
        )
        analysis.symbols.append(symbol)

        # Containment edge
        analysis.edges.append(
            EdgeInfo(
                source_fq_name=parent_fq_name,
                target_fq_name=fq,
                edge_type=EdgeType.CONTAINS,
                file_path=file_path,
                line=child.start_point[0] + 1,
            )
        )

        # Extract call edges from method/constructor bodies
        if kind in (SymbolKind.METHOD, SymbolKind.CONSTRUCTOR):
            _extract_calls(child, source, file_path, analysis, fq)


def _extract_calls(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    caller_fq_name: str,
) -> None:
    """Find invocation expressions inside a method body and create CALLS edges."""
    for child in _walk(node):
        if child.type == "invocation_expression":
            target = _extract_invocation_target(child, source)
            if target:
                analysis.edges.append(
                    EdgeInfo(
                        source_fq_name=caller_fq_name,
                        target_fq_name=target,
                        edge_type=EdgeType.CALLS,
                        file_path=file_path,
                        line=child.start_point[0] + 1,
                    )
                )
        elif child.type == "object_creation_expression":
            type_node = child.child_by_field_name("type")
            if type_node:
                target = _node_text(type_node, source)
                analysis.edges.append(
                    EdgeInfo(
                        source_fq_name=caller_fq_name,
                        target_fq_name=target,
                        edge_type=EdgeType.CALLS,
                        file_path=file_path,
                        line=child.start_point[0] + 1,
                    )
                )


# ---------------------------------------------------------------------------
# AST utility helpers
# ---------------------------------------------------------------------------


def _walk(node: Node):
    """Iterate all descendant nodes depth-first."""
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
    """Get the name from a type or namespace declaration."""
    name_node = node.child_by_field_name("name")
    if name_node:
        return _node_text(name_node, source)
    # Fallback: look for identifier child
    ident = _find_child_by_type(node, "identifier")
    if ident:
        return _node_text(ident, source)
    return "<unknown>"


def _get_member_name(node: Node, kind: SymbolKind, source: bytes, parent_fq: str) -> str:
    """Get the name of a member declaration."""
    if kind == SymbolKind.CONSTRUCTOR:
        # In tree-sitter C#, constructors have an identifier field
        name_node = node.child_by_field_name("name")
        if name_node:
            return _node_text(name_node, source)
        ident = _find_child_by_type(node, "identifier")
        if ident:
            return _node_text(ident, source)
        # Fallback: use class name
        return parent_fq.rsplit(".", 1)[-1] if "." in parent_fq else parent_fq

    name_node = node.child_by_field_name("name")
    if name_node:
        return _node_text(name_node, source)

    # Field declarations have variable declarators
    if kind == SymbolKind.FIELD:
        decl = _find_child_by_type(node, "variable_declaration")
        if decl:
            declarator = _find_child_by_type(decl, "variable_declarator")
            if declarator:
                ident = declarator.child_by_field_name("name")
                if ident:
                    return _node_text(ident, source)
                ident = _find_child_by_type(declarator, "identifier")
                if ident:
                    return _node_text(ident, source)
    return ""


def _extract_modifiers(node: Node, source: bytes) -> list[str]:
    """Extract access/other modifiers (public, static, abstract, etc.)."""
    modifiers = []
    for child in node.children:
        if child.type == "modifier":
            # The modifier node wraps the actual keyword (public, static, etc.)
            if child.child_count > 0:
                modifiers.append(_node_text(child.children[0], source))
            else:
                modifiers.append(_node_text(child, source))
    return modifiers


def _extract_base_types(node: Node, source: bytes) -> list[str]:
    """Extract base class / implemented interface names."""
    base_list = _find_child_by_type(node, "base_list")
    if not base_list:
        return []
    types = []
    for child in base_list.children:
        # In tree-sitter C#, base types can appear as:
        # - simple_base_type wrapping an identifier
        # - direct identifier or generic_name
        # - qualified_name
        if child.type in ("simple_base_type", "primary_constructor_base_type"):
            inner = (
                _find_child_by_type(child, "identifier")
                or _find_child_by_type(child, "generic_name")
                or _find_child_by_type(child, "qualified_name")
            )
            if inner:
                types.append(_node_text(inner, source))
        elif child.type in ("identifier", "generic_name", "qualified_name"):
            types.append(_node_text(child, source))
    return types


def _extract_signature(node: Node, source: bytes) -> str:
    """Build a human-readable signature from the method/property declaration."""
    text = _node_text(node, source)
    for marker in ("{", "=>"):
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx]
    return text.strip().replace("\n", " ").replace("\r", "")[:500]


def _extract_parameters(node: Node, source: bytes) -> list[str]:
    """Extract parameter names from a method/constructor parameter list."""
    param_list = _find_child_by_type(node, "parameter_list")
    if not param_list:
        return []
    params = []
    for child in param_list.children:
        if child.type == "parameter":
            name_node = child.child_by_field_name("name")
            if name_node:
                type_node = child.child_by_field_name("type")
                type_str = _node_text(type_node, source) if type_node else ""
                name_str = _node_text(name_node, source)
                params.append(f"{type_str} {name_str}".strip())
    return params


def _extract_return_type(node: Node, source: bytes) -> str:
    """Extract the return type from a method declaration."""
    # tree-sitter C# uses 'returns' field for methods, 'type' for properties
    type_node = node.child_by_field_name("returns") or node.child_by_field_name("type")
    if type_node:
        return _node_text(type_node, source)
    return ""


def _extract_doc_comment(node: Node, source: bytes) -> str:
    """Extract XML doc comment (/// ...) preceding a declaration."""
    prev = node.prev_named_sibling
    if prev and prev.type == "comment":
        text = _node_text(prev, source)
        if text.startswith("///"):
            return text
    return ""


def _extract_invocation_target(node: Node, source: bytes) -> str:
    """Extract the target name from an invocation_expression."""
    func = node.child_by_field_name("function")
    if func is None and node.child_count > 0:
        func = node.children[0]
    if func is None:
        return ""

    if func.type == "member_access_expression":
        name_node = func.child_by_field_name("name")
        if name_node:
            return _node_text(name_node, source)
    elif func.type == "identifier":
        return _node_text(func, source)
    elif func.type == "generic_name":
        ident = _find_child_by_type(func, "identifier")
        if ident:
            return _node_text(ident, source)

    return _node_text(func, source)

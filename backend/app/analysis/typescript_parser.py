"""
TypeScript / TSX parser using tree-sitter.

Extracts symbols (classes, interfaces, enums, methods, constructors,
properties, functions) and edges (calls, inheritance, implements,
imports, containment) from TypeScript and TSX source files.
"""

from __future__ import annotations

import logging
from pathlib import Path

import tree_sitter_typescript as tstypescript
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

TS_LANGUAGE = Language(tstypescript.language_typescript())
TSX_LANGUAGE = Language(tstypescript.language_tsx())


class TypeScriptParser(LanguageParser):
    """TypeScript source parser built on tree-sitter."""

    @property
    def language_id(self) -> str:
        return "typescript"

    def parse_file(self, source: bytes, file_path: str) -> FileAnalysis:
        return parse_file(source, file_path)


class TSXParser(LanguageParser):
    """TSX (TypeScript + JSX) parser."""

    @property
    def language_id(self) -> str:
        return "tsx"

    def parse_file(self, source: bytes, file_path: str) -> FileAnalysis:
        return parse_file(source, file_path, tsx=True)


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def create_parser(tsx: bool = False) -> Parser:
    return Parser(TSX_LANGUAGE if tsx else TS_LANGUAGE)


def parse_file(source: bytes, file_path: str, tsx: bool = False) -> FileAnalysis:
    """Parse a single TypeScript/TSX source file."""
    parser = create_parser(tsx=tsx)
    tree = parser.parse(source)
    root = tree.root_node

    # Module name from file path
    module = file_path.replace("/", ".").replace("\\", ".")
    for suffix in (".tsx", ".ts", ".d.ts"):
        if module.endswith(suffix.replace(".", ".")):
            module = module[: -len(suffix)]
            break

    analysis = FileAnalysis(path=file_path, namespace=module)
    analysis.using_directives = _extract_imports(root, source)

    for imp in analysis.using_directives:
        analysis.edges.append(
            EdgeInfo(
                source_fq_name=module,
                target_fq_name=imp,
                edge_type=EdgeType.IMPORTS,
                file_path=file_path,
            )
        )

    _extract_top_level(root, source, file_path, analysis, module, None)
    return analysis


def parse_file_from_path(file_path: Path, repo_root: Path) -> FileAnalysis:
    source = file_path.read_bytes()
    rel_path = file_path.relative_to(repo_root).as_posix()
    tsx = rel_path.endswith(".tsx")
    return parse_file(source, rel_path, tsx=tsx)


# ------------------------------------------------------------------
# Imports
# ------------------------------------------------------------------


def _extract_imports(root: Node, source: bytes) -> list[str]:
    imports: list[str] = []
    for child in root.children:
        if child.type == "import_statement":
            src_node = _find_child_by_type(child, "string")
            if src_node:
                text = _node_text(src_node, source).strip("'\"")
                imports.append(text)
    return imports


# ------------------------------------------------------------------
# Top-level extraction
# ------------------------------------------------------------------


def _extract_top_level(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
    parent_fq: str | None,
) -> None:
    for child in node.children:
        # Unwrap export_statement
        actual = child
        if child.type == "export_statement":
            inner = _get_exported_declaration(child)
            if inner is None:
                continue
            actual = inner

        _dispatch_declaration(actual, source, file_path, analysis, module, parent_fq)


def _get_exported_declaration(node: Node) -> Node | None:
    for child in node.children:
        if child.type in (
            "class_declaration",
            "abstract_class_declaration",
            "interface_declaration",
            "enum_declaration",
            "function_declaration",
            "type_alias_declaration",
            "lexical_declaration",
        ):
            return child
    return None


def _dispatch_declaration(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
    parent_fq: str | None,
) -> None:
    if node.type in ("class_declaration", "abstract_class_declaration"):
        _extract_class(node, source, file_path, analysis, module, parent_fq)
    elif node.type == "interface_declaration":
        _extract_interface(node, source, file_path, analysis, module, parent_fq)
    elif node.type == "enum_declaration":
        _extract_enum(node, source, file_path, analysis, module, parent_fq)
    elif node.type == "function_declaration":
        _extract_function(node, source, file_path, analysis, module, parent_fq)
    elif node.type == "type_alias_declaration":
        _extract_type_alias(node, source, file_path, analysis, module, parent_fq)
    elif node.type == "lexical_declaration":
        _extract_arrow_functions(node, source, file_path, analysis, module, parent_fq)


# ------------------------------------------------------------------
# Class
# ------------------------------------------------------------------


def _extract_class(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
    parent_fq: str | None,
) -> None:
    name = _get_name(node, source)
    fq = _make_fq(module, parent_fq, name)

    superclass = _extract_extends(node, source)
    interfaces = _extract_implements(node, source)
    base_types = ([superclass] if superclass else []) + interfaces

    modifiers = _extract_class_modifiers(node, source)

    symbol = SymbolInfo(
        name=name,
        kind=SymbolKind.CLASS,
        fq_name=fq,
        file_path=file_path,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        namespace=module,
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

    body = node.child_by_field_name("body")
    if body:
        _extract_class_members(body, source, file_path, analysis, module, fq)


# ------------------------------------------------------------------
# Interface
# ------------------------------------------------------------------


def _extract_interface(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
    parent_fq: str | None,
) -> None:
    name = _get_name(node, source)
    fq = _make_fq(module, parent_fq, name)

    symbol = SymbolInfo(
        name=name,
        kind=SymbolKind.INTERFACE,
        fq_name=fq,
        file_path=file_path,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        namespace=module,
        parent_fq_name=parent_fq,
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

    body = node.child_by_field_name("body")
    if body:
        for child in body.children:
            if child.type in ("method_signature", "property_signature"):
                mname = _get_member_name(child, source)
                if mname:
                    mfq = f"{fq}.{mname}"
                    kind = (
                        SymbolKind.METHOD
                        if child.type == "method_signature"
                        else SymbolKind.PROPERTY
                    )
                    analysis.symbols.append(
                        SymbolInfo(
                            name=mname,
                            kind=kind,
                            fq_name=mfq,
                            file_path=file_path,
                            start_line=child.start_point[0] + 1,
                            end_line=child.end_point[0] + 1,
                            namespace=module,
                            parent_fq_name=fq,
                            parameters=_extract_parameters(child, source),
                            return_type=_extract_return_type(child, source),
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
    fq = _make_fq(module, parent_fq, name)

    symbol = SymbolInfo(
        name=name,
        kind=SymbolKind.ENUM,
        fq_name=fq,
        file_path=file_path,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        namespace=module,
        parent_fq_name=parent_fq,
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


# ------------------------------------------------------------------
# Function (top-level)
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
    fq = _make_fq(module, parent_fq, name)

    symbol = SymbolInfo(
        name=name,
        kind=SymbolKind.METHOD,
        fq_name=fq,
        file_path=file_path,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        namespace=module,
        parent_fq_name=parent_fq,
        signature=_extract_signature(node, source),
        parameters=_extract_parameters(node, source),
        return_type=_extract_return_type(node, source),
        doc_comment=_extract_doc_comment(node, source),
    )
    analysis.symbols.append(symbol)

    body = node.child_by_field_name("body")
    if body:
        _extract_calls(body, source, file_path, analysis, fq)


# ------------------------------------------------------------------
# Type alias (export type Foo = ...)
# ------------------------------------------------------------------


def _extract_type_alias(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
    parent_fq: str | None,
) -> None:
    name = _get_name(node, source)
    fq = _make_fq(module, parent_fq, name)
    analysis.symbols.append(
        SymbolInfo(
            name=name,
            kind=SymbolKind.INTERFACE,  # type aliases are structurally similar
            fq_name=fq,
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            namespace=module,
            parent_fq_name=parent_fq,
        )
    )


# ------------------------------------------------------------------
# Arrow function (const fn = () => { ... })
# ------------------------------------------------------------------


def _extract_arrow_functions(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
    parent_fq: str | None,
) -> None:
    """Extract const/let declarations that bind arrow functions."""
    for child in node.children:
        if child.type != "variable_declarator":
            continue
        name_node = child.child_by_field_name("name")
        value_node = child.child_by_field_name("value")
        if not name_node or not value_node:
            continue
        if value_node.type != "arrow_function":
            continue

        name = _node_text(name_node, source)
        fq = _make_fq(module, parent_fq, name)
        params = _extract_parameters(value_node, source)
        ret = _extract_return_type(value_node, source)

        analysis.symbols.append(
            SymbolInfo(
                name=name,
                kind=SymbolKind.METHOD,
                fq_name=fq,
                file_path=file_path,
                start_line=child.start_point[0] + 1,
                end_line=child.end_point[0] + 1,
                namespace=module,
                parent_fq_name=parent_fq,
                parameters=params,
                return_type=ret,
                signature=_extract_signature(child, source),
            )
        )

        body = value_node.child_by_field_name("body")
        if body:
            _extract_calls(body, source, file_path, analysis, fq)


# ------------------------------------------------------------------
# Class members
# ------------------------------------------------------------------


def _extract_class_members(
    body: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
    parent_fq: str,
) -> None:
    for child in body.children:
        if child.type == "method_definition":
            _extract_method(child, source, file_path, analysis, module, parent_fq)
        elif child.type in ("public_field_definition", "property_definition"):
            _extract_field(child, source, file_path, analysis, module, parent_fq)


def _extract_method(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
    parent_fq: str,
) -> None:
    name = _get_member_name(node, source)
    if not name:
        return
    fq = f"{parent_fq}.{name}"

    kind = SymbolKind.CONSTRUCTOR if name == "constructor" else SymbolKind.METHOD
    modifiers = _extract_member_modifiers(node, source)

    symbol = SymbolInfo(
        name=name,
        kind=kind,
        fq_name=fq,
        file_path=file_path,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        namespace=module,
        parent_fq_name=parent_fq,
        modifiers=modifiers,
        signature=_extract_signature(node, source),
        parameters=_extract_parameters(node, source),
        return_type=_extract_return_type(node, source),
        doc_comment=_extract_doc_comment(node, source),
    )
    analysis.symbols.append(symbol)

    analysis.edges.append(
        EdgeInfo(
            source_fq_name=parent_fq,
            target_fq_name=fq,
            edge_type=EdgeType.CONTAINS,
            file_path=file_path,
            line=node.start_point[0] + 1,
        )
    )

    stmt_block = _find_child_by_type(node, "statement_block")
    if stmt_block:
        _extract_calls(stmt_block, source, file_path, analysis, fq)


def _extract_field(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
    parent_fq: str,
) -> None:
    name = _get_member_name(node, source)
    if not name:
        return
    fq = f"{parent_fq}.{name}"

    symbol = SymbolInfo(
        name=name,
        kind=SymbolKind.FIELD,
        fq_name=fq,
        file_path=file_path,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        namespace=module,
        parent_fq_name=parent_fq,
        modifiers=_extract_member_modifiers(node, source),
    )
    analysis.symbols.append(symbol)

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
            constr = child.child_by_field_name("constructor")
            if constr:
                analysis.edges.append(
                    EdgeInfo(
                        source_fq_name=caller_fq,
                        target_fq_name=_node_text(constr, source),
                        edge_type=EdgeType.CALLS,
                        file_path=file_path,
                        line=child.start_point[0] + 1,
                    )
                )


# ------------------------------------------------------------------
# TS-specific AST helpers
# ------------------------------------------------------------------


def _extract_extends(node: Node, source: bytes) -> str:
    heritage = _find_child_by_type(node, "class_heritage")
    if not heritage:
        return ""
    ext = _find_child_by_type(heritage, "extends_clause")
    if ext:
        for child in ext.children:
            if child.type in ("identifier", "type_identifier"):
                return _node_text(child, source)
    return ""


def _extract_implements(node: Node, source: bytes) -> list[str]:
    heritage = _find_child_by_type(node, "class_heritage")
    if not heritage:
        return []
    impl = _find_child_by_type(heritage, "implements_clause")
    if not impl:
        return []
    result: list[str] = []
    for child in impl.children:
        if child.type in ("type_identifier", "generic_type"):
            result.append(_node_text(child, source))
    return result


def _extract_class_modifiers(node: Node, source: bytes) -> list[str]:
    mods: list[str] = []
    if node.type == "abstract_class_declaration":
        mods.append("abstract")
    # Check if parent is export_statement
    parent = node.parent
    if parent and parent.type == "export_statement":
        mods.append("export")
    return mods


def _extract_member_modifiers(node: Node, source: bytes) -> list[str]:
    mods: list[str] = []
    for child in node.children:
        if child.type == "accessibility_modifier":
            mods.append(_node_text(child, source))
        elif child.type in ("readonly", "static", "async", "override", "abstract"):
            mods.append(child.type)
    return mods


def _extract_parameters(node: Node, source: bytes) -> list[str]:
    params = node.child_by_field_name("parameters") or _find_child_by_type(
        node, "formal_parameters"
    )
    if not params:
        return []
    result: list[str] = []
    for child in params.children:
        if child.type in ("required_parameter", "optional_parameter"):
            pat = child.child_by_field_name("pattern")
            if pat:
                name = _node_text(pat, source)
                ta = child.child_by_field_name("type")
                if ta:
                    result.append(f"{name}: {_node_text(ta, source)}")
                else:
                    result.append(name)
            else:
                # constructor shorthand: accessibility_modifier + identifier
                ident = _find_child_by_type(child, "identifier")
                if ident:
                    result.append(_node_text(ident, source))
        elif child.type == "rest_parameter":
            result.append(_node_text(child, source))
    return result


def _extract_return_type(node: Node, source: bytes) -> str:
    ret = node.child_by_field_name("return_type")
    if ret:
        text = _node_text(ret, source)
        return text.lstrip(": ").strip()
    return ""


def _extract_signature(node: Node, source: bytes) -> str:
    text = _node_text(node, source)
    for marker in ("{", ";"):
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx]
    return text.strip().replace("\n", " ").replace("\r", "")[:500]


def _extract_doc_comment(node: Node, source: bytes) -> str:
    prev = node.prev_named_sibling
    if prev and prev.type == "comment":
        text = _node_text(prev, source)
        if text.startswith("/**"):
            return text
    return ""


def _extract_call_target(node: Node, source: bytes) -> str:
    func = node.child_by_field_name("function")
    if func is None:
        return ""
    if func.type == "identifier":
        return _node_text(func, source)
    if func.type == "member_expression":
        prop = func.child_by_field_name("property")
        if prop:
            return _node_text(prop, source)
    return ""


# ------------------------------------------------------------------
# Generic tree-sitter utilities
# ------------------------------------------------------------------


def _make_fq(module: str, parent_fq: str | None, name: str) -> str:
    if parent_fq:
        return f"{parent_fq}.{name}"
    if module:
        return f"{module}.{name}"
    return name


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
    ident = _find_child_by_type(node, "identifier") or _find_child_by_type(node, "type_identifier")
    if ident:
        return _node_text(ident, source)
    return "<unknown>"


def _get_member_name(node: Node, source: bytes) -> str:
    name_node = node.child_by_field_name("name")
    if name_node:
        return _node_text(name_node, source)
    for child in node.children:
        if child.type in ("property_identifier", "identifier"):
            return _node_text(child, source)
    return ""

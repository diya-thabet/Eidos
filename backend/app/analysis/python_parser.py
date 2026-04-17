"""
Python parser using tree-sitter.

Extracts symbols (classes, functions/methods, module-level assignments)
and edges (calls, inheritance, imports, containment) from Python source.
"""

from __future__ import annotations

import logging
from pathlib import Path

import tree_sitter_python as tspython
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

PY_LANGUAGE = Language(tspython.language())


class PythonParser(LanguageParser):
    """Full Python source parser built on tree-sitter."""

    @property
    def language_id(self) -> str:
        return "python"

    def parse_file(self, source: bytes, file_path: str) -> FileAnalysis:
        return parse_file(source, file_path)


def create_parser() -> Parser:
    return Parser(PY_LANGUAGE)


def parse_file(source: bytes, file_path: str) -> FileAnalysis:
    """Parse a single Python source file and extract symbols + edges."""
    parser = create_parser()
    tree = parser.parse(source)
    root = tree.root_node

    analysis = FileAnalysis(path=file_path, namespace="")
    analysis.using_directives = _extract_imports(root, source)

    # Derive module name from file path (e.g. "app/core/config.py" -> "app.core.config")
    module = file_path.replace("/", ".").replace("\\", ".")
    if module.endswith(".pyi"):
        module = module[:-4]
    elif module.endswith(".py"):
        module = module[:-3]
    analysis.namespace = module

    for imp in analysis.using_directives:
        analysis.edges.append(
            EdgeInfo(
                source_fq_name=module,
                target_fq_name=imp,
                edge_type=EdgeType.IMPORTS,
                file_path=file_path,
            )
        )

    _extract_definitions(root, source, file_path, analysis, module, None)
    return analysis


def parse_file_from_path(file_path: Path, repo_root: Path) -> FileAnalysis:
    source = file_path.read_bytes()
    rel_path = file_path.relative_to(repo_root).as_posix()
    return parse_file(source, rel_path)


# ------------------------------------------------------------------
# Imports
# ------------------------------------------------------------------


def _extract_imports(root: Node, source: bytes) -> list[str]:
    imports: list[str] = []
    for child in root.children:
        if child.type == "import_statement":
            for sub in child.children:
                if sub.type == "dotted_name":
                    imports.append(_node_text(sub, source))
        elif child.type == "import_from_statement":
            module_node = _find_child_by_type(child, "dotted_name")
            if module_node:
                imports.append(_node_text(module_node, source))
    return imports


# ------------------------------------------------------------------
# Definitions
# ------------------------------------------------------------------


def _extract_definitions(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
    parent_fq: str | None,
) -> None:
    """Walk top-level or class-body children for class/function defs."""
    for child in node.children:
        if child.type == "class_definition":
            _extract_class(child, source, file_path, analysis, module, parent_fq)
        elif child.type in ("function_definition", "decorated_definition"):
            actual: Node = child
            if child.type == "decorated_definition":
                found = _find_child_by_type(child, "function_definition") or _find_child_by_type(
                    child, "class_definition"
                )
                if found is None:
                    continue
                if found.type == "class_definition":
                    _extract_class(found, source, file_path, analysis, module, parent_fq)
                    continue
                actual = found
            _extract_function(actual, source, file_path, analysis, module, parent_fq)


def _extract_class(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
    parent_fq: str | None,
) -> None:
    name = _get_name(node, source)
    fq = f"{parent_fq}.{name}" if parent_fq else f"{module}.{name}" if module else name

    base_types = _extract_bases(node, source)
    symbol = SymbolInfo(
        name=name,
        kind=SymbolKind.CLASS,
        fq_name=fq,
        file_path=file_path,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        namespace=module,
        parent_fq_name=parent_fq,
        modifiers=_extract_decorators(node, source),
        base_types=base_types,
        doc_comment=_extract_docstring(node, source),
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

    for base in base_types:
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
        _extract_definitions(body, source, file_path, analysis, module, fq)


def _extract_function(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    module: str,
    parent_fq: str | None,
) -> None:
    name = _get_name(node, source)
    fq = f"{parent_fq}.{name}" if parent_fq else f"{module}.{name}" if module else name

    # Determine kind: constructor if __init__, method if inside class, else function
    if name == "__init__":
        kind = SymbolKind.CONSTRUCTOR
    elif parent_fq:
        kind = SymbolKind.METHOD
    else:
        kind = SymbolKind.METHOD  # top-level functions as METHOD

    params = _extract_parameters(node, source)
    ret = _extract_return_type(node, source)
    mods = _extract_decorators(node, source)

    # Check for async
    prev = node.prev_sibling
    if prev and _node_text(prev, source).strip() == "async":
        mods = ["async"] + mods

    symbol = SymbolInfo(
        name=name,
        kind=kind,
        fq_name=fq,
        file_path=file_path,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        namespace=module,
        parent_fq_name=parent_fq,
        modifiers=mods,
        signature=_extract_signature(node, source),
        parameters=params,
        return_type=ret,
        doc_comment=_extract_docstring(node, source),
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
        _extract_calls(body, source, file_path, analysis, fq)


def _extract_calls(
    node: Node,
    source: bytes,
    file_path: str,
    analysis: FileAnalysis,
    caller_fq: str,
) -> None:
    for child in _walk(node):
        if child.type == "call":
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
# Python-specific helpers
# ------------------------------------------------------------------


def _extract_bases(node: Node, source: bytes) -> list[str]:
    """Extract base classes from ``class Foo(Bar, Baz):``."""
    arg_list = _find_child_by_type(node, "argument_list")
    if not arg_list:
        return []
    bases: list[str] = []
    for child in arg_list.children:
        if child.type == "identifier":
            bases.append(_node_text(child, source))
        elif child.type == "attribute":
            bases.append(_node_text(child, source))
    return bases


def _extract_decorators(node: Node, source: bytes) -> list[str]:
    """Extract decorator names (without @)."""
    result: list[str] = []
    # decorators are siblings before the definition, or inside decorated_definition
    parent = node.parent
    if parent and parent.type == "decorated_definition":
        for child in parent.children:
            if child.type == "decorator":
                # decorator children: @ + expression
                for sub in child.children:
                    if sub.type in ("identifier", "attribute", "call"):
                        result.append(_node_text(sub, source).split("(")[0])
                        break
    return result


def _extract_parameters(node: Node, source: bytes) -> list[str]:
    params_node = node.child_by_field_name("parameters")
    if not params_node:
        return []
    result: list[str] = []
    for child in params_node.children:
        if child.type == "identifier":
            text = _node_text(child, source)
            if text != "self" and text != "cls":
                result.append(text)
        elif child.type == "typed_parameter":
            name_node = _find_child_by_type(child, "identifier")
            type_node = child.child_by_field_name("type")
            n = _node_text(name_node, source) if name_node else ""
            t = _node_text(type_node, source) if type_node else ""
            if n and n not in ("self", "cls"):
                result.append(f"{n}: {t}" if t else n)
        elif child.type in (
            "default_parameter",
            "typed_default_parameter",
        ):
            name_node = child.child_by_field_name("name")
            if name_node:
                n = _node_text(name_node, source)
                if n not in ("self", "cls"):
                    result.append(n)
        elif child.type in ("list_splat_pattern", "dictionary_splat_pattern"):
            result.append(_node_text(child, source))
    return result


def _extract_return_type(node: Node, source: bytes) -> str:
    ret = node.child_by_field_name("return_type")
    if ret:
        return _node_text(ret, source)
    return ""


def _extract_signature(node: Node, source: bytes) -> str:
    text = _node_text(node, source)
    # Find the colon that starts the body (after closing paren or return type)
    body = node.child_by_field_name("body")
    if body:
        cut = body.start_byte - node.start_byte
        text = text[:cut]
    # Remove trailing colon
    text = text.rstrip().rstrip(":")
    return text.strip().replace("\n", " ")[:500]


def _extract_docstring(node: Node, source: bytes) -> str:
    body = node.child_by_field_name("body")
    if not body or not body.children:
        return ""
    first = body.children[0]
    if first.type == "expression_statement" and first.child_count > 0:
        expr = first.children[0]
        if expr.type == "string":
            text = _node_text(expr, source)
            if text.startswith('"""') or text.startswith("'''"):
                return text
    return ""


def _extract_call_target(node: Node, source: bytes) -> str:
    func = node.child_by_field_name("function")
    if func is None:
        return ""
    if func.type == "identifier":
        return _node_text(func, source)
    if func.type == "attribute":
        attr = func.child_by_field_name("attribute")
        if attr:
            return _node_text(attr, source)
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

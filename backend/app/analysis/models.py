"""
Data models for static analysis results.

These are pure data classes (not ORM models) used to pass analysis results
between the parser, graph builder, and storage layer.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class SymbolKind(str, enum.Enum):
    """Kind of code symbol extracted from C# source."""
    CLASS = "class"
    INTERFACE = "interface"
    STRUCT = "struct"
    ENUM = "enum"
    METHOD = "method"
    CONSTRUCTOR = "constructor"
    PROPERTY = "property"
    FIELD = "field"
    DELEGATE = "delegate"
    RECORD = "record"
    NAMESPACE = "namespace"


class EdgeType(str, enum.Enum):
    """Type of relationship between two symbols."""
    CALLS = "calls"
    IMPLEMENTS = "implements"
    INHERITS = "inherits"
    USES = "uses"
    CONTAINS = "contains"  # parent-child (class -> method)
    IMPORTS = "imports"     # using directive


@dataclass
class SymbolInfo:
    """A single code symbol extracted from the AST."""
    name: str
    kind: SymbolKind
    fq_name: str                    # fully-qualified: Namespace.Class.Method
    file_path: str
    start_line: int
    end_line: int
    namespace: str = ""
    parent_fq_name: str | None = None  # enclosing class/struct/interface
    signature: str = ""              # method/property signature
    modifiers: list[str] = field(default_factory=list)  # public, static, abstract, etc.
    parameters: list[str] = field(default_factory=list)  # method parameters
    return_type: str = ""
    base_types: list[str] = field(default_factory=list)  # inheritance / implements
    doc_comment: str = ""


@dataclass
class EdgeInfo:
    """A directed relationship between two symbols."""
    source_fq_name: str
    target_fq_name: str
    edge_type: EdgeType
    file_path: str = ""
    line: int = 0


@dataclass
class FileAnalysis:
    """Complete analysis result for a single file."""
    path: str
    namespace: str
    using_directives: list[str] = field(default_factory=list)
    symbols: list[SymbolInfo] = field(default_factory=list)
    edges: list[EdgeInfo] = field(default_factory=list)


@dataclass
class ModuleInfo:
    """A logical module (namespace or folder-based grouping)."""
    name: str
    file_count: int = 0
    symbol_count: int = 0
    files: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)  # namespaces this module depends on


@dataclass
class EntryPoint:
    """An identified entry point in the codebase."""
    symbol_fq_name: str
    kind: str  # "controller", "main", "startup", "minimal_api", "worker"
    file_path: str
    line: int
    route: str = ""  # HTTP route for controllers

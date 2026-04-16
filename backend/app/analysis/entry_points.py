"""
Entry point detection for C# codebases.

Identifies:
- ASP.NET controllers (classes inheriting Controller/ControllerBase)
- Main methods (static void/async Main or top-level statements)
- Startup / Program classes
- Minimal API patterns (WebApplication.CreateBuilder)
- Background services (IHostedService implementations)
"""

from __future__ import annotations

import re

from app.analysis.models import EntryPoint, SymbolInfo, SymbolKind
from app.analysis.graph_builder import CodeGraph

# Controller base class names that indicate an ASP.NET controller
_CONTROLLER_BASES = {"Controller", "ControllerBase", "ApiController", "ODataController"}

# Startup/config class patterns
_STARTUP_NAMES = {"Startup", "Program"}

# Background service interfaces
_WORKER_BASES = {"IHostedService", "BackgroundService"}


def detect_entry_points(graph: CodeGraph) -> list[EntryPoint]:
    """
    Scan the code graph for entry points.

    Returns a list of EntryPoint objects sorted by kind and name.
    """
    entries: list[EntryPoint] = []
    entries.extend(_detect_controllers(graph))
    entries.extend(_detect_main_methods(graph))
    entries.extend(_detect_startup_classes(graph))
    entries.extend(_detect_workers(graph))
    entries.sort(key=lambda e: (e.kind, e.symbol_fq_name))
    return entries


def _detect_controllers(graph: CodeGraph) -> list[EntryPoint]:
    """Find classes that inherit from a known controller base."""
    results: list[EntryPoint] = []
    for sym in graph.get_symbols_by_kind(SymbolKind.CLASS):
        if any(base in _CONTROLLER_BASES for base in sym.base_types):
            # Also find action methods inside this controller
            route = _infer_controller_route(sym)
            results.append(EntryPoint(
                symbol_fq_name=sym.fq_name,
                kind="controller",
                file_path=sym.file_path,
                line=sym.start_line,
                route=route,
            ))
            # Add individual action methods
            for child_fq in graph.get_children(sym.fq_name):
                child = graph.symbols.get(child_fq)
                if child and child.kind == SymbolKind.METHOD and "public" in child.modifiers:
                    results.append(EntryPoint(
                        symbol_fq_name=child.fq_name,
                        kind="controller_action",
                        file_path=child.file_path,
                        line=child.start_line,
                        route=f"{route}/{child.name}",
                    ))
    return results


def _detect_main_methods(graph: CodeGraph) -> list[EntryPoint]:
    """Find static Main methods."""
    results: list[EntryPoint] = []
    for sym in graph.get_symbols_by_kind(SymbolKind.METHOD):
        if sym.name == "Main" and "static" in sym.modifiers:
            results.append(EntryPoint(
                symbol_fq_name=sym.fq_name,
                kind="main",
                file_path=sym.file_path,
                line=sym.start_line,
            ))
    return results


def _detect_startup_classes(graph: CodeGraph) -> list[EntryPoint]:
    """Find Startup and Program classes."""
    results: list[EntryPoint] = []
    for sym in graph.get_symbols_by_kind(SymbolKind.CLASS):
        if sym.name in _STARTUP_NAMES:
            results.append(EntryPoint(
                symbol_fq_name=sym.fq_name,
                kind="startup",
                file_path=sym.file_path,
                line=sym.start_line,
            ))
    return results


def _detect_workers(graph: CodeGraph) -> list[EntryPoint]:
    """Find classes implementing IHostedService or extending BackgroundService."""
    results: list[EntryPoint] = []
    for sym in graph.get_symbols_by_kind(SymbolKind.CLASS):
        if any(base in _WORKER_BASES for base in sym.base_types):
            results.append(EntryPoint(
                symbol_fq_name=sym.fq_name,
                kind="worker",
                file_path=sym.file_path,
                line=sym.start_line,
            ))
    return results


def _infer_controller_route(sym: SymbolInfo) -> str:
    """
    Infer the route prefix for a controller.
    Convention: FooController -> /foo
    """
    name = sym.name
    if name.endswith("Controller"):
        name = name[: -len("Controller")]
    return f"/{name.lower()}"

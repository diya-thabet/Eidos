"""
Parser registry -- maps language identifiers to concrete parsers.

The registry is populated lazily on first access so that missing optional
tree-sitter grammars do not crash the application at import time.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.analysis.base_parser import LanguageParser

logger = logging.getLogger(__name__)

_registry: dict[str, LanguageParser] = {}
_initialised = False


def _init_registry() -> None:
    global _initialised  # noqa: PLW0603
    if _initialised:
        return
    _initialised = True

    # C# -- always available (core dependency)
    try:
        from app.analysis.csharp_parser_adapter import CSharpParser

        _registry["csharp"] = CSharpParser()
        logger.debug("Registered parser: csharp")
    except Exception:
        logger.warning("C# parser unavailable (tree-sitter-c-sharp missing?)")

    # Java -- optional
    try:
        from app.analysis.java_parser import JavaParser

        _registry["java"] = JavaParser()
        logger.debug("Registered parser: java")
    except Exception:
        logger.info("Java parser unavailable (tree-sitter-java missing?)")

    # Python -- optional
    try:
        from app.analysis.python_parser import PythonParser

        _registry["python"] = PythonParser()
        logger.debug("Registered parser: python")
    except Exception:
        logger.info("Python parser unavailable (tree-sitter-python missing?)")

    # TypeScript -- optional
    try:
        from app.analysis.typescript_parser import TSXParser, TypeScriptParser

        _registry["typescript"] = TypeScriptParser()
        _registry["tsx"] = TSXParser()
        logger.debug("Registered parser: typescript, tsx")
    except Exception:
        logger.info("TypeScript parser unavailable (tree-sitter-typescript missing?)")

    # Go -- optional
    try:
        from app.analysis.go_parser import GoParser

        _registry["go"] = GoParser()
        logger.debug("Registered parser: go")
    except Exception:
        logger.info("Go parser unavailable (tree-sitter-go missing?)")

    # Rust -- optional
    try:
        from app.analysis.rust_parser import RustParser

        _registry["rust"] = RustParser()
        logger.debug("Registered parser: rust")
    except Exception:
        logger.info("Rust parser unavailable (tree-sitter-rust missing?)")

    # C -- optional
    try:
        from app.analysis.c_parser import CParser

        _registry["c"] = CParser()
        logger.debug("Registered parser: c")
    except Exception:
        logger.info("C parser unavailable (tree-sitter-c missing?)")

    # C++ -- optional
    try:
        from app.analysis.cpp_parser import CppParser

        _registry["cpp"] = CppParser()
        logger.debug("Registered parser: cpp")
    except Exception:
        logger.info("C++ parser unavailable (tree-sitter-cpp missing?)")

    # ----- Add future language parsers here -----


def get_parser(language: str) -> LanguageParser | None:
    """Return the parser for *language*, or None if unsupported."""
    _init_registry()
    return _registry.get(language)


def supported_languages() -> set[str]:
    """Return the set of currently registered language identifiers."""
    _init_registry()
    return set(_registry.keys())

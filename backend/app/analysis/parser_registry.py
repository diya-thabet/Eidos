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

    # ----- Add future language parsers here -----


def get_parser(language: str) -> LanguageParser | None:
    """Return the parser for *language*, or None if unsupported."""
    _init_registry()
    return _registry.get(language)


def supported_languages() -> set[str]:
    """Return the set of currently registered language identifiers."""
    _init_registry()
    return set(_registry.keys())

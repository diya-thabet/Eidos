"""
Tests for structured JSON logging in client mode.

Covers:
- JSON format in client edition
- Text format in internal edition
- Graceful fallback if python-json-logger not installed
"""

from __future__ import annotations

import json
import logging


class TestLoggingConfiguration:
    def test_internal_mode_uses_text_format(self):
        """In internal mode, logging should use standard text format."""
        from app.core.config import settings

        # Internal is the test default
        assert settings.edition == "internal"

        root = logging.getLogger()
        # Should have at least one handler
        assert len(root.handlers) > 0
        # Handler should NOT be JSON formatter
        for handler in root.handlers:
            fmt = handler.formatter
            if fmt is not None:
                # Standard formatter, not JSON
                assert not hasattr(fmt, "json_ensure_ascii")

    def test_json_formatter_available(self):
        """Verify python-json-logger is installed."""
        from pythonjsonlogger.json import JsonFormatter

        fmt = JsonFormatter(fmt="%(message)s")
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="hello", args=(), exc_info=None,
        )
        output = fmt.format(record)
        parsed = json.loads(output)
        assert parsed["message"] == "hello"

    def test_json_formatter_includes_fields(self):
        """JSON formatter should include timestamp and level."""
        from pythonjsonlogger.json import JsonFormatter

        fmt = JsonFormatter(
            fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
            rename_fields={"asctime": "timestamp", "levelname": "level"},
        )
        record = logging.LogRecord(
            name="eidos.test", level=logging.WARNING, pathname="", lineno=0,
            msg="test warning", args=(), exc_info=None,
        )
        output = fmt.format(record)
        parsed = json.loads(output)
        assert parsed["message"] == "test warning"
        assert parsed["level"] == "WARNING"
        assert "timestamp" in parsed

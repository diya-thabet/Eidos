import os
import tempfile
from pathlib import Path

from app.core.ingestion import detect_language, hash_file, scan_files


def test_detect_language():
    assert detect_language("Program.cs") == "csharp"
    assert detect_language("app.json") == "json"
    assert detect_language("Startup.csproj") == "xml"
    assert detect_language("readme.txt") is None
    assert detect_language("schema.sql") == "sql"


def test_hash_file():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".cs") as f:
        f.write(b"using System;")
        f.flush()
        h = hash_file(Path(f.name))
        assert len(h) == 64  # sha256 hex
    os.unlink(f.name)


def test_scan_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        # Create some files
        (root / "Program.cs").write_text("class Program {}", encoding="utf-8")
        (root / "appsettings.json").write_text("{}", encoding="utf-8")
        (root / "image.png").write_bytes(b"\x89PNG")  # should be skipped (no language)
        (root / "readme.txt").write_text("hello")  # skipped

        # Create a bin dir that should be skipped
        (root / "bin").mkdir()
        (root / "bin" / "Debug.cs").write_text("junk", encoding="utf-8")

        files = scan_files(root)
        paths = {f["path"] for f in files}
        assert "Program.cs" in paths
        assert "appsettings.json" in paths
        assert "image.png" not in paths
        assert "readme.txt" not in paths
        assert "bin/Debug.cs" not in paths

        for f in files:
            assert f["language"] is not None
            assert len(f["hash"]) == 64
            assert f["size_bytes"] > 0

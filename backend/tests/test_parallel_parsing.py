"""
Tests for parallel file parsing (P3.12).

Covers:
- Sequential parsing for small file sets
- Parallel parsing for large file sets
- _parse_single_file isolation
- Mixed parseable/non-parseable files
- Empty file list
- Worker count configuration
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.analysis.models import FileAnalysis
from app.analysis.pipeline import (
    _MAX_WORKERS,
    _parse_parallel,
    _parse_sequential,
    _parse_single_file,
    analyze_snapshot_files,
)


@pytest.fixture
def temp_repo():
    """Create a temp directory with sample source files."""
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        # Create Python files
        for i in range(5):
            f = repo / f"mod{i}.py"
            f.write_text(f"class Foo{i}:\n    pass\n\ndef bar{i}():\n    pass\n")
        # Create a non-parseable file
        (repo / "readme.md").write_text("# Hello")
        # Create nested file
        (repo / "sub").mkdir()
        (repo / "sub" / "deep.py").write_text("def deep(): pass\n")
        yield repo


@pytest.fixture
def file_records():
    """Standard file records for 5 Python files."""
    return [
        {"path": f"mod{i}.py", "language": "python", "hash": f"h{i}", "size_bytes": 50}
        for i in range(5)
    ]


@pytest.fixture
def large_file_records():
    """25 Python file records to trigger parallel parsing."""
    return [
        {"path": f"mod{i}.py", "language": "python", "hash": f"h{i}", "size_bytes": 50}
        for i in range(25)
    ]


class TestSequentialParsing:
    def test_parses_all_python_files(self, temp_repo, file_records):
        analyses = _parse_sequential(temp_repo, file_records)
        assert len(analyses) == 5
        assert all(isinstance(a, FileAnalysis) for a in analyses)

    def test_skips_missing_files(self, temp_repo):
        records = [{"path": "nonexistent.py", "language": "python", "hash": "x", "size_bytes": 0}]
        analyses = _parse_sequential(temp_repo, records)
        assert len(analyses) == 0

    def test_empty_list_returns_empty(self, temp_repo):
        analyses = _parse_sequential(temp_repo, [])
        assert analyses == []

    def test_skips_unknown_language(self, temp_repo):
        records = [{"path": "readme.md", "language": "markdown", "hash": "x", "size_bytes": 10}]
        analyses = _parse_sequential(temp_repo, records)
        assert len(analyses) == 0


class TestParallelParsing:
    def test_parses_files_in_parallel(self, temp_repo, file_records):
        analyses = _parse_parallel(temp_repo, file_records)
        assert len(analyses) == 5

    def test_parallel_results_match_sequential(self, temp_repo, file_records):
        seq = _parse_sequential(temp_repo, file_records)
        par = _parse_parallel(temp_repo, file_records)
        # Same number of results
        assert len(seq) == len(par)
        # Same symbols found
        seq_symbols = {s.fq_name for a in seq for s in a.symbols}
        par_symbols = {s.fq_name for a in par for s in a.symbols}
        assert seq_symbols == par_symbols

    def test_handles_missing_files_gracefully(self, temp_repo):
        records = [
            {"path": "mod0.py", "language": "python", "hash": "h0", "size_bytes": 50},
            {"path": "ghost.py", "language": "python", "hash": "h1", "size_bytes": 50},
        ]
        analyses = _parse_parallel(temp_repo, records)
        assert len(analyses) == 1


class TestParseSingleFile:
    def test_parses_valid_python(self, temp_repo):
        result = _parse_single_file(str(temp_repo), "mod0.py", "python")
        assert result is not None
        assert isinstance(result, FileAnalysis)

    def test_returns_none_for_missing(self, temp_repo):
        result = _parse_single_file(str(temp_repo), "nope.py", "python")
        assert result is None

    def test_returns_none_for_unknown_language(self, temp_repo):
        result = _parse_single_file(str(temp_repo), "readme.md", "brainfuck")
        assert result is None


class TestAnalyzeSnapshotFiles:
    def test_small_repo_uses_sequential(self, temp_repo, file_records):
        """Files <= 20 should use sequential parsing."""
        graph = analyze_snapshot_files(temp_repo, file_records)
        assert len(graph.symbols) > 0

    def test_non_parseable_files_filtered(self, temp_repo):
        records = [
            {"path": "mod0.py", "language": "python", "hash": "h0", "size_bytes": 50},
            {"path": "readme.md", "language": "markdown", "hash": "h1", "size_bytes": 10},
        ]
        graph = analyze_snapshot_files(temp_repo, records)
        # Only Python file should produce symbols
        assert all("readme" not in s for s in graph.symbols)

    def test_empty_records_returns_empty_graph(self, temp_repo):
        graph = analyze_snapshot_files(temp_repo, [])
        assert len(graph.symbols) == 0
        assert len(graph.edges) == 0

    def test_worker_count_is_bounded(self):
        assert 1 <= _MAX_WORKERS <= 8

from __future__ import annotations

import hashlib
import logging
import os
import shutil
from pathlib import Path

import git

from app.core.config import settings

logger = logging.getLogger(__name__)

# Extensions we index (MVP: C# focus + common config)
LANGUAGE_MAP: dict[str, str] = {
    ".cs": "csharp",
    ".csx": "csharp",
    ".csproj": "xml",
    ".sln": "solution",
    ".json": "json",
    ".xml": "xml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
    ".sql": "sql",
    ".config": "xml",
    ".props": "xml",
    ".targets": "xml",
}

# Skip these directories
SKIP_DIRS = {".git", "bin", "obj", "node_modules", ".vs", "packages", "TestResults", "artifacts"}

# Max single file size to index (1 MB)
MAX_FILE_SIZE = 1_048_576


def clone_repo(url: str, branch: str, dest: Path, commit_sha: str | None = None) -> str:
    """Clone a repo and checkout the requested commit. Returns the resolved SHA."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    logger.info("Cloning %s (branch=%s) -> %s", url, branch, dest)
    repo = git.Repo.clone_from(url, str(dest), branch=branch, depth=1 if not commit_sha else 0)

    if commit_sha:
        repo.git.checkout(commit_sha)
        return commit_sha

    return repo.head.commit.hexsha


def detect_language(path: str) -> str | None:
    ext = os.path.splitext(path)[1].lower()
    return LANGUAGE_MAP.get(ext)


def hash_file(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_files(repo_dir: Path) -> list[dict]:
    """Walk the repo and return file metadata for indexable files."""
    results: list[dict] = []
    for root, dirs, files in os.walk(repo_dir):
        # Prune skipped directories in-place
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            filepath = Path(root) / name
            rel_path = filepath.relative_to(repo_dir).as_posix()
            lang = detect_language(name)
            if lang is None:
                continue
            try:
                size = filepath.stat().st_size
            except OSError:
                continue
            if size > MAX_FILE_SIZE or size == 0:
                continue
            results.append(
                {
                    "path": rel_path,
                    "language": lang,
                    "hash": hash_file(filepath),
                    "size_bytes": size,
                }
            )
    logger.info("Scanned %d indexable files in %s", len(results), repo_dir)
    return results


def repo_clone_path(repo_id: str, commit_sha: str) -> Path:
    return Path(settings.repos_data_dir) / repo_id / commit_sha

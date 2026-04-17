"""
Tests for data retention / clone cleanup.

Covers: cleanup after indexing, cleanup all repo clones,
disabled cleanup, missing directories.
"""

from unittest.mock import patch

from app.core.retention import cleanup_all_repo_clones, cleanup_clone


class TestCleanupClone:
    def test_removes_directory(self, tmp_path):
        clone_dir = tmp_path / "repo1" / "snap1"
        clone_dir.mkdir(parents=True)
        (clone_dir / "file.cs").write_text("code")

        with patch("app.core.retention.settings") as ms:
            ms.delete_clones_after_indexing = True
            ms.repos_data_dir = str(tmp_path)
            result = cleanup_clone("repo1", "snap1")

        assert result is True
        assert not clone_dir.exists()

    def test_disabled_does_nothing(self, tmp_path):
        clone_dir = tmp_path / "repo1" / "snap1"
        clone_dir.mkdir(parents=True)

        with patch("app.core.retention.settings") as ms:
            ms.delete_clones_after_indexing = False
            ms.repos_data_dir = str(tmp_path)
            result = cleanup_clone("repo1", "snap1")

        assert result is False
        assert clone_dir.exists()

    def test_missing_directory_returns_false(self, tmp_path):
        with patch("app.core.retention.settings") as ms:
            ms.delete_clones_after_indexing = True
            ms.repos_data_dir = str(tmp_path)
            result = cleanup_clone("repo1", "nonexistent")

        assert result is False


class TestCleanupAllRepoClones:
    def test_removes_repo_dir(self, tmp_path):
        repo_dir = tmp_path / "repo1"
        repo_dir.mkdir()
        (repo_dir / "snap1").mkdir()
        (repo_dir / "snap2").mkdir()

        with patch("app.core.retention.settings") as ms:
            ms.repos_data_dir = str(tmp_path)
            result = cleanup_all_repo_clones("repo1")

        assert result == 1
        assert not repo_dir.exists()

    def test_missing_repo_dir(self, tmp_path):
        with patch("app.core.retention.settings") as ms:
            ms.repos_data_dir = str(tmp_path)
            result = cleanup_all_repo_clones("nonexistent")

        assert result == 0

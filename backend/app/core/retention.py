"""
Data retention policy.

Handles cleanup of cloned repository data after indexing completes.
Configurable via ``EIDOS_DELETE_CLONES_AFTER_INDEXING``.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


def cleanup_clone(repo_id: str, snapshot_id: str) -> bool:
    """
    Delete the local clone directory for a snapshot.

    Returns True if the directory was removed, False if it didn't
    exist or deletion failed.
    """
    if not settings.delete_clones_after_indexing:
        return False

    clone_dir = Path(settings.repos_data_dir) / repo_id / snapshot_id
    if not clone_dir.exists():
        return False

    try:
        shutil.rmtree(clone_dir)
        logger.info("Cleaned up clone: %s", clone_dir)
        return True
    except OSError as exc:
        logger.warning("Failed to clean up clone %s: %s", clone_dir, exc)
        return False


def cleanup_all_repo_clones(repo_id: str) -> int:
    """
    Delete all clone directories for a repo (e.g. on repo deletion).

    Returns the number of directories removed.
    """
    repo_dir = Path(settings.repos_data_dir) / repo_id
    if not repo_dir.exists():
        return 0

    count = 0
    try:
        shutil.rmtree(repo_dir)
        count = 1
        logger.info("Cleaned up all clones for repo %s", repo_id)
    except OSError as exc:
        logger.warning("Failed to clean up repo clones %s: %s", repo_dir, exc)
    return count

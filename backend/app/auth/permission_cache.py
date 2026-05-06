"""
Permission caching layer.

Provides an in-memory TTL cache for user permission lookups
to avoid repeated DB queries on every request.
"""

from __future__ import annotations

import time
from typing import Any


class _PermissionCache:
    """Simple TTL cache for permission data.

    Thread-safe for async usage (single-threaded event loop).
    """

    def __init__(self, ttl: int = 300, maxsize: int = 10000) -> None:
        self._ttl = ttl
        self._maxsize = maxsize
        self._cache: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        """Get a cached value. Returns None if expired or missing."""
        entry = self._cache.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            del self._cache[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        """Store a value with TTL."""
        # Evict if at capacity
        if len(self._cache) >= self._maxsize:
            self._evict_expired()
            if len(self._cache) >= self._maxsize:
                # Remove oldest 10%
                keys = list(self._cache.keys())
                for k in keys[: len(keys) // 10]:
                    del self._cache[k]

        self._cache[key] = (time.monotonic() + self._ttl, value)

    def invalidate(self, key: str) -> None:
        """Remove a specific key."""
        self._cache.pop(key, None)

    def invalidate_user(self, user_id: str) -> None:
        """Remove all cached entries for a user."""
        to_remove = [k for k in self._cache if k.startswith(f"user:{user_id}:")]
        for k in to_remove:
            del self._cache[k]

    def invalidate_repo(self, repo_id: str) -> None:
        """Remove all cached entries related to a repo."""
        to_remove = [k for k in self._cache if f":repo:{repo_id}" in k]
        for k in to_remove:
            del self._cache[k]

    def clear(self) -> None:
        """Clear entire cache."""
        self._cache.clear()

    def _evict_expired(self) -> None:
        """Remove all expired entries."""
        now = time.monotonic()
        expired = [k for k, (exp, _) in self._cache.items() if now > exp]
        for k in expired:
            del self._cache[k]

    @property
    def size(self) -> int:
        """Current number of entries."""
        return len(self._cache)

    @property
    def stats(self) -> dict[str, int]:
        """Cache statistics."""
        self._evict_expired()
        return {"size": len(self._cache), "maxsize": self._maxsize, "ttl": self._ttl}


# Global singleton
permission_cache = _PermissionCache(ttl=300, maxsize=10000)


def _repo_access_key(user_id: str, repo_id: str) -> str:
    return f"user:{user_id}:repo:{repo_id}:access"


def _role_scopes_key(user_id: str) -> str:
    return f"user:{user_id}:role_scopes"

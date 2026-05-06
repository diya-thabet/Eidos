"""
Tests for RBAC Phase 6: Permission Caching.

Tests the cache layer itself and integration with require_repo_access.
"""

from __future__ import annotations

import time

from app.auth.permission_cache import (
    _PermissionCache,
    _repo_access_key,
    permission_cache,
)


class TestPermissionCacheUnit:

    def setup_method(self):
        self.cache = _PermissionCache(ttl=2, maxsize=100)

    def test_set_and_get(self):
        self.cache.set("k1", True)
        assert self.cache.get("k1") is True

    def test_missing_key(self):
        assert self.cache.get("nonexistent") is None

    def test_ttl_expiry(self):
        cache = _PermissionCache(ttl=0, maxsize=10)
        cache.set("k1", True)
        # TTL=0 means immediate expiry
        time.sleep(0.01)
        assert cache.get("k1") is None

    def test_invalidate_key(self):
        self.cache.set("k1", True)
        self.cache.invalidate("k1")
        assert self.cache.get("k1") is None

    def test_invalidate_user(self):
        self.cache.set("user:u1:repo:r1:access", True)
        self.cache.set("user:u1:repo:r2:access", True)
        self.cache.set("user:u2:repo:r1:access", True)
        self.cache.invalidate_user("u1")
        assert self.cache.get("user:u1:repo:r1:access") is None
        assert self.cache.get("user:u1:repo:r2:access") is None
        assert self.cache.get("user:u2:repo:r1:access") is True

    def test_invalidate_repo(self):
        self.cache.set("user:u1:repo:r1:access", True)
        self.cache.set("user:u2:repo:r1:access", True)
        self.cache.set("user:u1:repo:r2:access", True)
        self.cache.invalidate_repo("r1")
        assert self.cache.get("user:u1:repo:r1:access") is None
        assert self.cache.get("user:u2:repo:r1:access") is None
        assert self.cache.get("user:u1:repo:r2:access") is True

    def test_clear(self):
        self.cache.set("a", 1)
        self.cache.set("b", 2)
        self.cache.clear()
        assert self.cache.size == 0

    def test_maxsize_eviction(self):
        cache = _PermissionCache(ttl=60, maxsize=10)
        for i in range(15):
            cache.set(f"k{i}", i)
        assert cache.size <= 10

    def test_stats(self):
        self.cache.set("k1", True)
        stats = self.cache.stats
        assert stats["size"] == 1
        assert stats["maxsize"] == 100
        assert stats["ttl"] == 2

    def test_repo_access_key(self):
        key = _repo_access_key("user1", "repo1")
        assert "user1" in key
        assert "repo1" in key


class TestGlobalCache:

    def test_singleton_exists(self):
        assert permission_cache is not None
        assert permission_cache.stats["ttl"] == 300

    def test_set_get_clear(self):
        permission_cache.set("test_key", "val")
        assert permission_cache.get("test_key") == "val"
        permission_cache.invalidate("test_key")
        assert permission_cache.get("test_key") is None

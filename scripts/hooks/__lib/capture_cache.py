#!/usr/bin/env python3
"""Capture result cache for handoff system.

This module provides a time-based cache for capture operation results,
reducing redundant subprocess calls during handoff capture.

Cache entries expire after TTL (default: 5 minutes).
"""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Cache TTL in seconds (5 minutes)
CACHE_TTL = 300


class CaptureCache:
    """Time-based cache for capture operation results.

    Caches capture results by key (capture_type, project_root, path_hash)
    with automatic expiration after TTL.

    Example:
        >>> cache = CaptureCache()
        >>> result = cache.get("git_state", "/path/to/project", "abc123")
        >>> if result is None:
        ...     result = capture_git_state("/path/to/project")
        ...     cache.set("git_state", "/path/to/project", "abc123", result)
    """

    def __init__(self, ttl: int = CACHE_TTL) -> None:
        """Initialize capture cache.

        Args:
            ttl: Time-to-live for cache entries in seconds (default: 300)
        """
        self._cache: dict[str, dict] = {}
        self._ttl = ttl

    def get(self, key: str) -> dict | None:
        """Get cached result if available and not expired.

        Args:
            key: Cache key (use generate_key() to create)

        Returns:
            Cached result dict or None if:
            - Key not found
            - Entry expired (age > TTL)
            - Cache data corrupted

        Example:
            >>> result = cache.get("git_state:/path/to/project:abc123")
            >>> if result:
            ...     print(f"Cached: {result}")
        """
        try:
            entry = self._cache.get(key)
            if entry is None:
                return None

            # Check if entry has expired
            age = time.time() - entry.get("timestamp", 0)
            if age > self._ttl:
                logger.debug(
                    f"[CaptureCache] Cache entry expired: {key} (age: {age:.1f}s)"
                )
                # Remove expired entry
                del self._cache[key]
                return None

            logger.debug(f"[CaptureCache] Cache hit: {key} (age: {age:.1f}s)")
            return entry.get("data")

        except Exception as e:
            # Cache failures should never block capture
            logger.warning(f"[CaptureCache] Error reading cache for {key}: {e}")
            return None

    def set(self, key: str, value: dict) -> None:
        """Cache result with current timestamp.

        Args:
            key: Cache key (use generate_key() to create)
            value: Result dict to cache

        Example:
            >>> cache.set("git_state:/path/to/project:abc123", {"branch": "main"})
        """
        try:
            self._cache[key] = {
                "data": value,
                "timestamp": time.time(),
            }
            logger.debug(f"[CaptureCache] Cached result: {key}")
        except Exception as e:
            # Cache failures should never block capture
            logger.warning(f"[CaptureCache] Error caching result for {key}: {e}")

    def clear(self) -> None:
        """Clear all cached entries.

        Example:
            >>> cache.clear()
        """
        try:
            self._cache.clear()
            logger.debug("[CaptureCache] Cache cleared")
        except Exception as e:
            logger.warning(f"[CaptureCache] Error clearing cache: {e}")

    @staticmethod
    def generate_key(
        capture_type: str, project_root: str | Path, path_hash: str
    ) -> str:
        """Generate cache key for capture operation.

        Args:
            capture_type: Type of capture (e.g., "git_state", "dependency_state")
            project_root: Project root path
            path_hash: Hash of additional context (e.g., file paths, dependencies)

        Returns:
            Cache key string

        Example:
            >>> key = CaptureCache.generate_key("git_state", "/path/to/project", "abc123")
            >>> print(key)
            'git_state:/path/to/project:abc123'
        """
        return f"{capture_type}:{project_root}:{path_hash}"

    @staticmethod
    def hash_path(path: str | Path) -> str:
        """Generate hash of path for cache key.

        Args:
            path: Path to hash

        Returns:
            Hexadecimal hash string

        Example:
            >>> hash_str = CaptureCache.hash_path("/path/to/file.py")
        """
        path_str = str(path)
        return hashlib.md5(path_str.encode()).hexdigest()[:8]

    @staticmethod
    def hash_paths(paths: list[str | Path]) -> str:
        """Generate combined hash of multiple paths for cache key.

        Args:
            paths: List of paths to hash

        Returns:
            Combined hexadecimal hash string

        Example:
            >>> hash_str = CaptureCache.hash_paths(["/path/to/file1.py", "/path/to/file2.py"])
        """
        combined = "\0".join(str(p) for p in sorted(paths))
        return hashlib.md5(combined.encode()).hexdigest()[:8]

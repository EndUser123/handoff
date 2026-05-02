#!/usr/bin/env python3
"""Terminal-scoped file registry for handoff active_files tracking.

Provides multi-terminal isolated file access tracking with TTL-based staleness prevention.
Each terminal maintains its own file registry, ensuring no cross-terminal contamination.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TTL_HOURS = 24
MAX_FILES = 20


class TerminalFileRegistry:
    """Per-terminal registry of recently accessed files.

    Multi-terminal isolation:
    - Each terminal has its own {terminal_id}_files.json file
    - No shared mutable state between terminals
    - Each terminal only sees files IT accessed

    Stale-data immunity:
    - TTL-based expiration (24 hours default)
    - Old entries auto-expire on read
    - Fresh data always available
    """

    def __init__(
        self, project_root: Path, terminal_id: str, ttl_hours: int = DEFAULT_TTL_HOURS
    ):
        self._validate_terminal_id(terminal_id)
        self.project_root = project_root
        self.terminal_id = terminal_id
        self.ttl_hours = ttl_hours
        self.registry_dir = project_root / ".claude" / "state" / "handoff"
        self.registry_file = self.registry_dir / f"{terminal_id}_files.json"

    @staticmethod
    def _validate_terminal_id(terminal_id: str) -> None:
        from scripts.hooks.__lib.validation_utils import validate_terminal_id
        validate_terminal_id(terminal_id)

    def record_access(self, file_path: str) -> None:
        """Record file access with timestamp.

        Args:
            file_path: Path to file that was accessed
        """
        try:
            registry = self._load_registry()
            now = datetime.now(timezone.utc).isoformat()
            registry[file_path] = {
                "last_access": now,
                "access_count": registry.get(file_path, {}).get("access_count", 0) + 1,
            }
            self._save_registry(registry)
            logger.debug(
                "[TerminalFileRegistry] Recorded access to %s for terminal %s",
                file_path,
                self.terminal_id,
            )
        except Exception as exc:
            logger.warning(
                "[TerminalFileRegistry] Failed to record access: %s",
                exc,
            )

    def get_recent_files(self, max_files: int = MAX_FILES) -> list[str]:
        """Get files accessed within TTL, sorted by recency.

        Args:
            max_files: Maximum number of files to return

        Returns:
            List of file paths, most recent first
        """
        try:
            registry = self._load_registry()
            cutoff = datetime.now(timezone.utc) - timedelta(hours=self.ttl_hours)

            recent = [
                (path, data["last_access"], data.get("access_count", 0))
                for path, data in registry.items()
                if datetime.fromisoformat(data["last_access"]) > cutoff
            ]
            # Sort by last_access descending, then by access_count
            recent.sort(key=lambda x: (x[1], x[2]), reverse=True)
            return [path for path, _, _ in recent[:max_files]]
        except Exception as exc:
            logger.warning(
                "[TerminalFileRegistry] Failed to get recent files: %s",
                exc,
            )
            return []

    def _load_registry(self) -> dict[str, Any]:
        """Load registry from file, creating if needed."""
        try:
            self.registry_dir.mkdir(parents=True, exist_ok=True)
            if not self.registry_file.exists():
                return {}
            with open(self.registry_file, encoding="utf-8") as handle:
                data = json.load(handle)
                if not isinstance(data, dict):
                    return {}
                return data
        except json.JSONDecodeError:
            logger.warning(
                "[TerminalFileRegistry] Corrupted registry file, starting fresh"
            )
            return {}
        except Exception as exc:
            logger.warning(
                "[TerminalFileRegistry] Failed to load registry: %s",
                exc,
            )
            return {}

    def _save_registry(self, registry: dict[str, Any]) -> None:
        """Save registry to file atomically (thread-safe via FileLock)."""
        import tempfile

        try:
            self.registry_dir.mkdir(parents=True, exist_ok=True)
            lock_file = self.registry_file.with_suffix(".lock")
            # SNAPSHOT-005: FileLock prevents concurrent _save_registry calls from losing data
            from scripts.hooks.__lib.snapshot_store import FileLock

            with FileLock(lock_file, timeout=5.0):
                fd, temp_path = tempfile.mkstemp(
                    suffix=".tmp",
                    dir=str(self.registry_dir),
                    prefix=f"{self.terminal_id}_files_",
                )
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as handle:
                        json.dump(registry, handle, indent=2, ensure_ascii=False)
                    # Atomic rename
                    Path(temp_path).replace(self.registry_file)
                except Exception:
                    # Clean up temp file on error
                    try:
                        os.unlink(temp_path)
                    except OSError:
                        pass
                    raise
        except Exception as exc:
            logger.error(
                "[TerminalFileRegistry] Failed to save registry: %s",
                exc,
            )

    def cleanup_expired(self) -> int:
        """Remove expired entries from registry.

        Returns:
            Number of entries removed
        """
        try:
            registry = self._load_registry()
            cutoff = datetime.now(timezone.utc) - timedelta(hours=self.ttl_hours)
            original_count = len(registry)

            registry = {
                path: data
                for path, data in registry.items()
                if datetime.fromisoformat(data["last_access"]) > cutoff
            }

            removed = original_count - len(registry)
            if removed > 0:
                self._save_registry(registry)
                logger.info(
                    "[TerminalFileRegistry] Cleaned up %d expired entries for terminal %s",
                    removed,
                    self.terminal_id,
                )
            return removed
        except Exception as exc:
            logger.warning(
                "[TerminalFileRegistry] Failed to cleanup expired: %s",
                exc,
            )
            return 0


# Required for atomic write

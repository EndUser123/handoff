"""
Handoff configuration - paths, retention policies, and defaults.

Provides utility functions for common patterns:
- utcnow_iso(): Current UTC time as ISO string
- load_json_file(): Load JSON with error handling
- save_json_file(): Save JSON with atomic write
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Allow importing from scripts/hooks/__lib/ for shared utilities
if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


logger = logging.getLogger(__name__)

# Project root (defaults to current working directory for portability)
# HANDOFF_PROJECT_ROOT env var can override for testing
PROJECT_ROOT = Path(os.getenv("HANDOFF_PROJECT_ROOT", str(Path.cwd()))).resolve()

# Handoff storage directories
HANDOFF_DIR = PROJECT_ROOT / ".claude" / "handoffs"
TRASH_DIR = HANDOFF_DIR / "trash"

# Retention policies
# CLEANUP_DAYS: Delete handoff documents older than this (from /hod skill)
# Default 90 days per /hod spec - handoffs are session-bridging artifacts,
# not permanent records. After 90 days, context is stale and relevant
# decisions should be captured in CKS/patterns.
CLEANUP_DAYS = int(os.getenv("HANDOFF_RETENTION_DAYS", "90"))
MAX_VERSIONS = 20  # Keep maximum 20 versions per task

# Timeout for stuck task release
TIMEOUT_MINUTES = 45  # Release tasks in_progress longer than this

# Lock settings
LOCK_TIMEOUT_SECONDS = 5.0  # File lock acquisition timeout

# Retry settings for atomic write operations
MAX_RETRIES = 5  # Maximum retry attempts for atomic write operations
RETRY_BASE_DELAY_SECONDS = 0.005  # Base delay for exponential backoff (5ms)

# File lock polling settings
LOCK_CHECK_INTERVAL_SECONDS = 0.1  # Interval between lock acquisition attempts (100ms)
LOCK_CHECKS_PER_SECOND = (
    10  # Number of lock checks per second (1 / LOCK_CHECK_INTERVAL_SECONDS)
)
STALE_LOCK_AGE_SECONDS = 10.0  # Age after which a lock is considered stale (10 seconds)


def get_handoff_dir(project_root: Path | None = None) -> Path:
    """
    Get handoff directory for a project.

    Args:
        project_root: Root directory (defaults to PROJECT_ROOT)

    Returns:
        Path to handoff storage directory
    """
    if project_root:
        return (project_root / ".claude" / "handoffs").resolve()
    return HANDOFF_DIR


def ensure_directories() -> None:
    """Create handoff directories if they don't exist."""
    HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
    TRASH_DIR.mkdir(parents=True, exist_ok=True)


def utcnow_iso() -> str:
    """
    Get current UTC time as ISO 8601 string.

    Returns:
        Current UTC time in ISO format (e.g., "2025-01-15T10:30:00+00:00")

    Example:
        >>> utcnow_iso()
        '2025-01-15T10:30:00+00:00'
    """
    return datetime.now(UTC).isoformat()


def load_json_file(file_path: Path) -> dict[str, Any] | None:
    """
    Load JSON file with error handling.

    Args:
        file_path: Path to JSON file

    Returns:
        Parsed dict or None if file doesn't exist or is invalid

    Note:
        - Returns None for missing files (not an error)
        - Returns None for invalid JSON (logs error)
        - Use this when file existence is optional
    """
    try:
        if not file_path.exists():
            return None
        result = json.loads(file_path.read_text(encoding="utf-8"))
        if isinstance(result, dict):
            return result
        return None
    except (json.JSONDecodeError, OSError) as e:
        logger.debug(f"[Config] Could not load JSON file {file_path}: {e}")
        # Log error but don't raise - caller decides if None is fatal
        import logging

        logging.getLogger(__name__).warning(f"Error loading {file_path}: {e}")
        return None


def save_json_file(file_path: Path, data: dict[str, Any]) -> bool:
    """
    Save dict to JSON file with error handling.

    Args:
        file_path: Path to write (creates parent dirs)
        data: Dict to serialize

    Returns:
        True if successful, False otherwise

    Note:
        - Creates parent directories automatically
        - Uses atomic write (temp file + rename)
        - Returns False on error (doesn't raise)
    """
    import tempfile

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write: temp file + rename
        fd, temp_path = tempfile.mkstemp(suffix=".tmp", dir=str(file_path.parent))
        try:
            with open(fd, "w", encoding="utf-8") as f:
                f.write(json.dumps(data, indent=2))
            Path(temp_path).replace(file_path)
            return True
        except OSError as replace_error:
            logger.debug(
                f"[Config] Could not replace target file, cleaning up: {replace_error}"
            )
            try:
                Path(temp_path).unlink()
            except OSError as unlink_error:
                logger.debug(f"[Config] Could not unlink temp file: {unlink_error}")
            raise
    except (OSError, TypeError) as e:
        logger.error(f"[Config] Error saving {file_path}: {e}")
        return False


def cleanup_old_handoffs(project_root: Path | None = None) -> int:
    """
    Automatically clean up old handoff files based on retention policy.

    Implements COMP-001: Automatic cleanup during compaction.
    Deletes task tracker files and handoff envelope files older than CLEANUP_DAYS (default 90 days).
    This runs on EVERY compaction, not just when --cleanup flag is used.

    Args:
        project_root: Project root directory (defaults to PROJECT_ROOT)

    Returns:
        Number of files deleted

    Note:
        - Deletes *_tasks.json files from .claude/state/task_tracker
        - Deletes *_handoff.json files from .claude/state/handoff
        - Also deletes V1-format handoff files (fallback_*, unknown_handoff)
        - Uses file modification time (mtime) to determine age
        - Respects CLEANUP_DAYS configuration (default 90 days)
    """
    from datetime import UTC, datetime

    if project_root is None:
        project_root = _cleanup_resolve_project_root()

    deleted_count = 0

    # CRIT-007 FIX: Also clean up expired _handoff.json files, not just _tasks.json
    for state_subdir, pattern in [
        (Path(".claude") / "state" / "task_tracker", "*_tasks.json"),
        (Path(".claude") / "state" / "handoff", "*_handoff.json"),
    ]:
        state_dir = project_root / state_subdir
        if not state_dir.exists():
            continue

        cutoff_time = datetime.now(UTC).timestamp() - (CLEANUP_DAYS * 86400)

        for file_path in state_dir.glob(pattern):
            try:
                mtime = file_path.stat().st_mtime
                if mtime < cutoff_time:
                    file_path.unlink()
                    deleted_count += 1
                    age_days = (datetime.now(UTC).timestamp() - mtime) // 86400
                    logger.debug(
                        "[Config] Auto-deleted old handoff: %s (age: %d days)",
                        file_path.name,
                        age_days,
                    )
            except OSError:
                continue

    # Also clean up V1/legacy handoff files regardless of age (these have no checksum)
    handoff_dir = project_root / ".claude" / "state" / "handoff"
    if handoff_dir.exists():
        for file_path in handoff_dir.glob("*"):
            if not file_path.is_file() or file_path.suffix == ".lock":
                continue
            # Clean up known non-V2 files: fallback_*, unknown_handoff, env_* without checksum
            name = file_path.name
            if name.startswith("fallback_") or name.startswith("unknown_"):
                try:
                    file_path.unlink()
                    deleted_count += 1
                    logger.debug(
                        "[Config] Auto-deleted legacy handoff: %s", file_path.name
                    )
                except OSError:
                    continue

    if deleted_count > 0:
        logger.info(
            f"[Config] Auto-cleanup: Deleted {deleted_count} old handoff file(s) "
            f"(retention: {CLEANUP_DAYS} days)"
        )

    return deleted_count


def _cleanup_resolve_project_root() -> Path:
    """Resolve project root for cleanup, walking up from cwd to find .claude.

    When invoked from a skill subdirectory, Path.cwd() would return that
    subdirectory. Walk up to find the actual project root.
    """
    cwd = Path.cwd()
    current = cwd.resolve()
    for _ in range(10):
        if (current / ".claude").is_dir():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return cwd  # Fallback

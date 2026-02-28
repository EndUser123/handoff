"""
Handoff configuration - paths, retention policies, and defaults.

Zero dependencies - uses pathlib.Path and environment variables only.
"""

from __future__ import annotations

import os
from pathlib import Path

# Project root (defaults to P:/ for CSF environment)
PROJECT_ROOT = Path(os.getenv("HANDOFF_PROJECT_ROOT", "P:/")).resolve()

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
        return json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
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
        fd, temp_path = tempfile.mkstemp(
            suffix=".tmp", dir=str(file_path.parent)
        )
        try:
            with open(fd, "w", encoding="utf-8") as f:
                f.write(json.dumps(data, indent=2))
            Path(temp_path).replace(file_path)
            return True
        except OSError:
            try:
                Path(temp_path).unlink()
            except OSError:
                pass
            raise
    except (OSError, TypeError) as e:
        import logging
        logging.getLogger(__name__).error(f"Error saving {file_path}: {e}")
        return False

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

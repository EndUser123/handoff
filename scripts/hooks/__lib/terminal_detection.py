#!/usr/bin/env python3
"""
Terminal Detection Module - Compatibility Wrapper

This module provides a compatibility wrapper that imports terminal detection
from skill-guard, ensuring consistent terminal ID format across all systems.

IMPORTANT: This ensures handoff and skill enforcement use the SAME terminal IDs.
Previous version had incompatible implementations that broke skill enforcement.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _get_skill_guard_path() -> Path:
    """Get the path to skill-guard package."""
    # Try multiple possible locations for skill-guard
    current_file = Path(__file__)

    # Option 1: Relative to handoff package (packages/handoff/core/hooks/__lib/)
    # project_root should be P:/packages/
    project_root = current_file.parent.parent.parent.parent.parent
    skill_guard_paths = [
        project_root / "skill-guard" / "src",  # Fixed: removed extra "packages/"
        project_root / ".claude" / "hooks" / "skill-guard" / "src",
        current_file.parent.parent.parent.parent / "skill-guard",  # Fallback
    ]

    for path in skill_guard_paths:
        if (path / "skill_guard" / "utils" / "terminal_detection.py").exists():
            return path

    # If not found, raise import error with helpful message
    raise ImportError(
        f"skill-guard package not found. Tried:\n"
        f"  - {skill_guard_paths[0]}\n"
        f"  - {skill_guard_paths[1]}\n"
        f"  - {skill_guard_paths[2]}\n"
        f"Ensure skill-guard is installed in packages/ directory."
    )


# Add skill-guard to path and import
_skill_guard_path = _get_skill_guard_path()
if str(_skill_guard_path) not in sys.path:
    sys.path.insert(0, str(_skill_guard_path))

from skill_guard.utils.terminal_detection import (
    detect_terminal_id as _sg_detect_terminal_id,
)

# Re-export for backward compatibility
detect_terminal_id = _sg_detect_terminal_id


def resolve_terminal_key(terminal_id: str | None = None) -> str:
    """Resolve the terminal key for handoff file storage.

    This wrapper ensures the terminal ID is compatible with skill-guard's format.

    Args:
        terminal_id: Optional terminal ID (uses detected ID if not provided)

    Returns:
        Resolved terminal key string (sanitized for filename usage)

    Raises:
        ValueError: If terminal_id fails validation
    """
    if terminal_id is None:
        terminal_id = detect_terminal_id()

    # Validate terminal_id format
    if not terminal_id or not terminal_id.strip():
        raise ValueError("terminal_id cannot be empty or whitespace-only")

    if "\x00" in terminal_id:
        raise ValueError(
            f"terminal_id cannot contain null bytes (got: {repr(terminal_id)})"
        )

    if ".." in terminal_id or terminal_id.startswith("./"):
        raise ValueError(
            f"terminal_id cannot contain path traversal sequences (got: {terminal_id})"
        )

    if terminal_id.startswith("/") or terminal_id.startswith("\\"):
        raise ValueError(f"terminal_id cannot be an absolute path (got: {terminal_id})")

    # Sanitize terminal ID for filename (replace unsafe characters)
    # skill-guard uses format: {source}_{id} where source is "env" or "console"
    # These are already filename-safe, but we sanitize for safety
    safe_id = terminal_id.replace("/", "-").replace("\\", "-").replace(":", "-")
    return safe_id

#!/usr/bin/env python3
"""
Terminal Detection Module - Compatibility Wrapper

Lazy-imports terminal detection from skill-guard when available.
Falls back to a local implementation using the same priority order:
1. CLAUDE_TERMINAL_ID and other env vars
2. Windows WT_SESSION / GetConsoleWindow() handle
3. Empty string (callers must handle)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_TERMINAL_ENV_VARS = [
    "CLAUDE_TERMINAL_ID",
    "TERMINAL_ID",
    "TERM_ID",
    "SESSION_TERMINAL",
]

_sg_detect_terminal_id = None
_sg_resolved = False


def _try_import_skill_guard() -> None:
    """Attempt to import detect_terminal_id from skill-guard (once)."""
    global _sg_detect_terminal_id, _sg_resolved
    if _sg_resolved:
        return
    _sg_resolved = True

    current_file = Path(__file__)
    project_root = current_file.parent.parent.parent.parent.parent
    for candidate in (
        project_root / "skill-guard" / "src",
        project_root / ".claude" / "hooks" / "skill-guard" / "src",
        current_file.parent.parent.parent.parent / "skill-guard",
    ):
        marker = candidate / "skill_guard" / "utils" / "terminal_detection.py"
        if marker.exists():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            try:
                from skill_guard.utils.terminal_detection import (
                    detect_terminal_id as _impl,
                )
                _sg_detect_terminal_id = _impl
            except Exception:
                pass
            return


def _fallback_detect_terminal_id() -> str:
    """Fallback using env vars and Windows console handle."""
    for env_var in _TERMINAL_ENV_VARS:
        value = os.environ.get(env_var)
        if value:
            return f"env_{value}"
    if sys.platform == "win32":
        wt = os.environ.get("WT_SESSION")
        if wt:
            return f"console_{wt}"
        try:
            handle = __import__("ctypes").windll.kernel32.GetConsoleWindow()
            if handle:
                return f"console_{hex(handle)[2:]}"
        except Exception:
            pass
    return ""


def detect_terminal_id() -> str:
    """Detect terminal ID. Uses skill-guard when available, fallback otherwise."""
    _try_import_skill_guard()
    if _sg_detect_terminal_id is not None:
        return _sg_detect_terminal_id()
    return _fallback_detect_terminal_id()


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

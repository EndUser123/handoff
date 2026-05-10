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

import json
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


def get_verified_identity(session_id: str | None = None) -> dict | None:
    """Read and verify the global identity cache for the current terminal.

    This implements a 'Handshake' pattern: we only trust the cached identity
    if it matches our live session_id. This prevents using stale data from
    a previous session in the same terminal.
    """
    # 1. Start with the fastest heuristic-based ID (WT_SESSION)
    terminal_id = detect_terminal_id()
    if not terminal_id:
        return None

    # 2. Locate the identity.json file in the canonical artifacts root
    # Matching $CLAUDE_ROOT/hooks\SessionStart_identity_capture.py
    artifacts_root = Path("P:\\\\\\.claude/.artifacts")
    safe_tid = terminal_id.replace("/", "-").replace("\\", "-").replace(":", "-")
    identity_file = artifacts_root / safe_tid / "identity.json"

    if not identity_file.exists():
        return None

    # 3. THE HANDSHAKE: Verify against live session_id
    try:
        identity = json.loads(identity_file.read_text(encoding="utf-8"))
        if session_id:
            cached_sid = identity.get("claude", {}).get("session_id")
            if cached_sid and cached_sid != session_id:
                # Stale data: identity file belongs to a DIFFERENT session
                return None
        return identity
    except (json.JSONDecodeError, OSError):
        return None


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


def detect_terminal_id(session_id: str | None = None) -> str:
    """Detect terminal ID. Uses verified handshake if session_id provided, fallback otherwise."""
    if session_id:
        identity = get_verified_identity(session_id)
        if identity:
            tid = identity.get("terminal", {}).get("id")
            if tid:
                return tid

    _try_import_skill_guard()
    if _sg_detect_terminal_id is not None:
        return _sg_detect_terminal_id()
    return _fallback_detect_terminal_id()


def resolve_terminal_key(
    terminal_id: str | None = None, session_id: str | None = None
) -> str:
    """Resolve the terminal key for handoff file storage.

    Args:
        terminal_id: Optional terminal ID
        session_id: Optional session ID (enables verified handshake)

    Returns:
        Resolved terminal key string
    """
    if terminal_id is None:
        terminal_id = detect_terminal_id(session_id)

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

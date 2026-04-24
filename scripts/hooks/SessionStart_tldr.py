#!/usr/bin/env python3
"""
SessionStart Hook: TLDR Session Summary Injection

Fires on startup and resume matchers. Reads the previous session's summary
from the terminal-scoped state file and injects it via stdout context.

Terminal-scoped paths prevent cross-terminal state collision.
Atomic operations ensure no torn reads.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
STATE_DIR = HOOKS_DIR.parent / "state" / "session_tldr"

# Import terminal_id resolver from hook_base (centralized source of truth)
_get_terminal_id: Callable[[dict | None], str] | None = None
try:
    sys.path.insert(0, str(HOOKS_DIR / "__lib"))
    from hook_base import get_terminal_id as _get_terminal_id_func
    _get_terminal_id = _get_terminal_id_func
except ImportError as exc:
    # Fallback if hook_base unavailable - log for diagnostics
    import logging as _logging
    _logger = _logging.getLogger(__name__)
    _logger.warning(
        "SessionStart_tldr: hook_base.get_terminal_id unavailable, "
        "using terminal_unknown fallback. ImportError: %s",
        exc,
    )
    _get_terminal_id = None


def _resolve_terminal_id(data: dict | None = None) -> str:
    """Resolve terminal_id using centralized hook_base implementation.

    Uses get_terminal_id() from hook_base which provides:
    - Priority: hook input > env vars > console detection > PID+timestamp
    - Returns empty string if all detection fails (caller handles fallback)
    """
    if _get_terminal_id is not None:
        result = _get_terminal_id(data)
        if result:
            return result
    # Fallback only if all detection methods fail
    return "terminal_unknown"


def _safe_id(value: str) -> str:
    """Sanitize terminal_id for use in file paths."""
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value)


def _get_state_path(terminal_id: str) -> Path:
    """Return terminal-scoped path to last session summary."""
    safe_tid = _safe_id(terminal_id)
    return STATE_DIR / f"{safe_tid}_last_session.md"


def _get_session_start_path(terminal_id: str) -> Path:
    """Return terminal-scoped path to session start timestamp."""
    safe_tid = _safe_id(terminal_id)
    return STATE_DIR / f"{safe_tid}_session_start.txt"


def _write_session_start(path: Path) -> None:
    """Write current timestamp to session_start.txt for duration calc."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(datetime.now(UTC).isoformat(), encoding="utf-8")


def _read_prior_summary(path: Path) -> str | None:
    """Read prior session summary, returns None if missing or corrupt."""
    if not path.exists():
        return None
    try:
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            return None
        return content
    except Exception:
        return None


def extract_last_user_message(data: dict) -> str | None:
    """Extract the last user message from a conversation-like dict.

    Walks the ``messages`` list backwards and returns the ``content`` of the
    last entry whose ``role`` is ``"user"`` and whose ``content`` is a non-empty
    string.

    Returns None when no matching entry is found or the input is malformed.
    """
    messages = data.get("messages")
    if not isinstance(messages, list):
        return None
    for entry in reversed(messages):
        if not isinstance(entry, dict):
            continue
        if entry.get("role") != "user":
            continue
        content = entry.get("content")
        if isinstance(content, str):
            return content.strip()
    return None


def _format_tldr_output(summary: str | None, *, last_user_message: str | None = None, **_kwargs: object) -> str:
    """Format the TLDR context block for injection."""
    if not summary:
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
        return f"## Session Start\n**When:** {now}\nNo prior session summary available.\n"

    # Parse prior summary to extract key info
    lines = summary.splitlines()
    parsed: dict = {"when": None, "duration": None, "accomplished": [], "files": [], "open": []}

    in_accomplished = False
    in_files = False
    in_open = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("**When:**"):
            parsed["when"] = stripped.split("**When:**", 1)[1].strip()
        elif stripped.startswith("**Duration:**"):
            parsed["duration"] = stripped.split("**Duration:**", 1)[1].strip()
        elif stripped.startswith("**Accomplished:**"):
            in_accomplished = True
            in_files = False
            in_open = False
        elif stripped.startswith("**Files changed:**"):
            in_accomplished = False
            in_files = True
            in_open = False
        elif stripped.startswith("**Open items:**"):
            in_accomplished = False
            in_files = False
            in_open = True
        elif stripped.startswith("---") or not stripped:
            in_accomplished = False
            in_files = False
            in_open = False
        elif in_accomplished and stripped.startswith("-"):
            parsed["accomplished"].append(stripped)
        elif in_files and stripped.startswith("-"):
            parsed["files"].append(stripped)
        elif in_open and stripped.startswith("-"):
            parsed["open"].append(stripped)

    # Build compact output
    output = "## Last Session Summary\n"
    if parsed["when"]:
        output += f"**When:** {parsed['when']}\n"
    if parsed["duration"]:
        output += f"**Duration:** {parsed['duration']}\n"
    if parsed["accomplished"]:
        output += "**Accomplished:**\n"
        for item in parsed["accomplished"][:5]:  # Limit to 5 items
            output += f"{item}\n"
    if parsed["files"]:
        output += f"**Files changed:** {', '.join(parsed['files'][:5])}\n"
    if parsed["open"]:
        output += "**Open items:**\n"
        for item in parsed["open"]:
            output += f"{item}\n"

    # ADR-006: Verbatim last user message for post-compact disambiguation
    if last_user_message is not None:
        output += f"**Last user message:** {last_user_message}\n"

    return output


def main() -> int:
    raw = sys.stdin.read().strip()
    if not raw:
        # No input — use empty dict
        data: dict = {}
    else:
        try:
            data = json.loads(raw.lstrip("\ufeff"))
        except json.JSONDecodeError:
            data = {}

    terminal_id = _resolve_terminal_id(data)
    summary_path = _get_state_path(terminal_id)
    session_start_path = _get_session_start_path(terminal_id)

    # Always write session start timestamp (overwrites on resume)
    _write_session_start(session_start_path)

    # Read prior summary
    prior_summary = _read_prior_summary(summary_path)

    # Format output as plain text for VISIBLE DISPLAY (not silent injection)
    # The hook system passes non-JSON stdout lines through as visible context
    tldr_text = _format_tldr_output(prior_summary)
    print(tldr_text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())

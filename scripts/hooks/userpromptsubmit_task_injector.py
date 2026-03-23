"""Compaction Recovery — UserPromptSubmit hook.

Detects mid-session compaction events via a short-lived marker file written by
``PreCompact_handoff_capture.py`` immediately after saving the Handoff V2
envelope.  On the first user prompt after a compaction, this hook reads the
envelope and injects restoration context automatically — no explicit "read the
transcript" directive needed.

FLOW:
    PreCompact (PreCompact_handoff_capture.py)
        ↓ saves handoff envelope to state/handoff/{terminal_id}_handoff.json
        ↓ writes state/compaction_marker_{terminal_id}.json  <- NEW
    UserPromptSubmit (this hook)
        ↓ checks for compaction marker
        ↓ loads handoff envelope
        ↓ injects restoration context (one-shot)
        ↓ deletes marker

Gap closed: SessionStart fires at session *start* (including post-compact session
restart), but intra-session compactions have no automatic recovery injection.
This hook fills that gap by listening for the marker signal on every UPS event
and injecting exactly once.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from UserPromptSubmit_modules.base import HookContext, HookResult
from UserPromptSubmit_modules.registry import register_hook

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def _locate_hooks_state_dir() -> Path:
    """Return the hooks state directory regardless of whether this file is
    invoked directly or via a symlink from .claude/hooks/.

    PreCompact writes markers to ``<project_root>/.claude/hooks/state/``.
    We must read from the same location.  Walking up from cwd is reliable
    because Claude Code always runs hooks with cwd = project root.
    """
    # Walk up from cwd (= project root when run by Claude Code)
    cwd = Path.cwd()
    candidate = cwd / ".claude" / "hooks" / "state"
    if candidate.parent.is_dir():
        return candidate
    # Fallback: walk ancestor dirs
    for parent in cwd.parents:
        candidate = parent / ".claude" / "hooks" / "state"
        if candidate.parent.is_dir():
            return candidate
    # Last resort: hooks dir relative to this file (works when run directly
    # from within the hooks tree)
    return Path(__file__).resolve().parents[3] / ".claude" / "hooks" / "state"


STATE_DIR = _locate_hooks_state_dir()

_MARKER_PREFIX = "compaction_marker_"
# TTL is a safety valve only — the one-shot deletion is the primary guard.
_MARKER_TTL_SECONDS = 3600  # 1 hour

_ENABLED_ENV = "COMPACTION_RECOVERY_ENABLED"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_terminal_id(context: HookContext) -> str:
    """Extract terminal ID from hook context."""
    return (
        context.data.get("terminal_id")
        or context.data.get("terminalId")
        or context.data.get("CLAUDE_TERMINAL_ID")
        or os.environ.get("CLAUDE_TERMINAL_ID")
        or "default"
    )


def _marker_path(terminal_id: str) -> Path:
    """Return path to the compaction marker file for this terminal."""
    safe_id = re.sub(r"[^a-zA-Z0-9_.\-]+", "_", str(terminal_id))
    return STATE_DIR / f"{_MARKER_PREFIX}{safe_id}.json"


def _load_marker(terminal_id: str) -> dict | None:
    """Load the compaction marker; return None if absent, unreadable, or expired."""
    path = _marker_path(terminal_id)
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as fh:
            marker = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None

    ts = float(marker.get("timestamp", 0.0))
    if (time.time() - ts) > _MARKER_TTL_SECONDS:
        _clear_marker(terminal_id)
        return None

    return marker


def _clear_marker(terminal_id: str) -> None:
    """Delete the compaction marker (one-shot injection guard)."""
    try:
        _marker_path(terminal_id).unlink(missing_ok=True)
    except OSError:
        pass


def _load_envelope(handoff_path: str) -> dict | None:
    """Load the Handoff V2 envelope JSON; return None on any error."""
    path = Path(handoff_path)
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _build_recovery_message(envelope: dict) -> str:
    """Format a concise restoration context block from a Handoff V2 envelope."""
    snapshot = envelope.get("resume_snapshot", {})
    goal: str = snapshot.get("goal", "Unknown")
    current_task: str = snapshot.get("current_task", "Unknown")
    active_files: list[str] = snapshot.get("active_files", [])
    pending_ops: list[dict] = snapshot.get("pending_operations", [])
    next_step: str = snapshot.get("next_step", "")
    transcript_path: str = snapshot.get("transcript_path", "")

    lines = [
        "CONTEXT RESTORED — mid-session compaction detected\n",
        f"Goal: {goal}",
        f"Current Task: {current_task}",
    ]

    if active_files:
        lines.append("Active Files:")
        for f in active_files[:5]:
            lines.append(f"  - {f}")

    if pending_ops:
        lines.append("Pending Operations:")
        for op in pending_ops[:3]:
            op_type = op.get("type", "op")
            target = op.get("target", "unknown")
            lines.append(f"  - {op_type}: {target}")

    if next_step:
        lines.append(f"Next Step: {next_step}")

    # CONTEXT-001: Inject recent user context from transcript
    # This preserves user clarifications and refinements across compactions
    # SEC-001 FIX: Validate envelope before using transcript_path to prevent path traversal
    if transcript_path:
        from scripts.hooks.__lib.handoff_v2 import (
            HandoffValidationError,
            _extract_and_format_user_context,
            validate_envelope,
        )

        # Validate envelope before using any fields from it (path traversal protection)
        try:
            validate_envelope(envelope)
        except HandoffValidationError:
            # Invalid envelope - skip context injection, safe defaults only
            pass
        else:
            user_context = _extract_and_format_user_context(
                transcript_path, max_messages=15
            )
            if user_context:
                lines.extend(["", user_context])

        lines.append(
            "Transcript: <session transcript> — read this for full pre-compaction context if needed"
        )

    lines.append(
        "\n(Auto-injected from handoff snapshot. Continue from the state above.)"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Hook entry point
# ---------------------------------------------------------------------------


@register_hook("handoff_task_injector", priority=1.0)
def handoff_task_injector_hook(context: HookContext) -> HookResult:
    """Inject Handoff V2 restoration context on the first prompt after compaction.

    ``PreCompact_handoff_capture.py`` writes a compaction marker immediately
    after saving the handoff envelope.  This hook detects that marker, loads
    the envelope, builds a restoration message, injects it once, then deletes
    the marker so subsequent prompts are unaffected.
    """
    enabled = os.environ.get(_ENABLED_ENV, "true").lower()
    if enabled not in ("1", "true", "yes"):
        return HookResult.empty()

    terminal_id = _get_terminal_id(context)
    marker = _load_marker(terminal_id)
    if marker is None:
        return HookResult.empty()

    handoff_path = marker.get("handoff_path", "")
    # Always clear the marker — inject at most once regardless of outcome.
    _clear_marker(terminal_id)

    if not handoff_path:
        return HookResult.empty()

    envelope = _load_envelope(handoff_path)
    if envelope is None:
        return HookResult.empty()

    message = _build_recovery_message(envelope)
    return HookResult(context=message, tokens=len(message) // 4)

"""
PreCompact_commitment_tracker.py - Save commitment checkpoint before compaction.

Runs BEFORE compaction erases context:
1. Reads current transcript state
2. Calls CommitmentTracker.scan_transcript()
3. Calls CommitmentTracker.check_completion() for each
4. Saves checkpoint to ~/.claude/.checkpoints/gto-commitments-{terminal_id}.json

Checkpoint is read by SessionStart_commitment_tracker.py on post-compaction resume.

Feature-gated by PROACTIVE_COMMITMENT_TRACKER_ENABLED.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Add __lib to path for commitment_tracker import
_CLAUDE_HOOKS_LIB = Path("P:/.claude/hooks/__lib")
if str(_CLAUDE_HOOKS_LIB) not in sys.path:
    sys.path.insert(0, str(_CLAUDE_HOOKS_LIB))

from commitment_tracker import CommitmentTracker

# Feature flag check
_ENABLED = os.environ.get("PROACTIVE_COMMITMENT_TRACKER_ENABLED", "").lower() in (
    "1",
    "true",
    "yes",
)


def main() -> None:
    """Main entry point for PreCompact router."""
    if not _ENABLED:
        sys.exit(0)

    raw_input = sys.stdin.read().strip()
    if not raw_input:
        sys.exit(0)

    try:
        raw_input = raw_input.lstrip("\ufeff")
        data = json.loads(raw_input)
    except json.JSONDecodeError:
        sys.exit(0)

    try:
        terminal_id = _extract_terminal_id(data)
        if not terminal_id:
            sys.exit(0)

        transcript = _extract_transcript(data)
        if not transcript:
            sys.exit(0)

        session_id = _extract_session_id(data)

        tracker = CommitmentTracker()
        commitments = tracker.scan_transcript(transcript, session_id=session_id)

        # Check completion status for each commitment
        uncompleted = []
        for commitment in commitments:
            updated = tracker.check_completion(commitment, transcript)
            if not updated.completed:
                uncompleted.append(updated)

        if uncompleted:
            tracker.save_checkpoint(uncompleted, terminal_id)

    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("PreCompact commitment tracker failed: %s", exc)
        pass

    sys.exit(0)


def _extract_terminal_id(data: dict) -> str:
    """Extract terminal_id from hook data."""
    terminal = data.get("terminal_id", "")
    if terminal:
        return str(terminal)

    session = data.get("session", {})
    if isinstance(session, dict):
        terminal = session.get("terminal_id", "")
        if terminal:
            return str(terminal)

    terminal = os.environ.get("CLAUDE_TERMINAL_ID", "")
    if terminal:
        return terminal

    return ""


def _extract_session_id(data: dict) -> str:
    """Extract session_id from hook data."""
    session = data.get("session_id", "")
    if session:
        return str(session)

    session_obj = data.get("session")
    if isinstance(session_obj, dict):
        for key in ("id", "session_id", "sessionId"):
            val = session_obj.get(key)
            if val:
                return str(val)

    return ""


def _extract_transcript(data: dict) -> list[dict]:
    """Extract transcript from hook data."""
    transcript = data.get("transcript", [])
    if isinstance(transcript, list):
        return transcript

    handoff = data.get("handoff_envelope", {})
    if isinstance(handoff, dict):
        transcript = handoff.get("transcript", [])
        if isinstance(transcript, list):
            return transcript

    return []


if __name__ == "__main__":
    main()

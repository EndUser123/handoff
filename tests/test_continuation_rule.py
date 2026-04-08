"""Tests for continuation_rule in compact-restore messages.

Verifies that the continuation_rule properly frames restored goals as inference,
not fact — preventing confabulation during session recovery.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add package root to sys.path for imports
_package_root = Path(__file__).resolve().parents[1]
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from core.hooks.__lib.handoff_v2 import build_restore_message_compact


def test_continuation_rule_frames_goal_as_inference():
    """The continuation_rule must explicitly instruct to frame goals as inference, not fact.

    This prevents the LLM from stating "The task was X" with false confidence.
    Instead, it should say "Based on the session handoff, we were working on X."
    """
    payload = {
        "resume_snapshot": {
            "goal": "rebuild sessions-index from JSONL files",
            "current_task": "testing JSONL parsing",
            "progress_state": "in_progress",
            "progress_percent": 50,
            "next_step": "verify JSONL schema",
            "blockers": [],
            "active_files": ["packages/handoff/scripts/hooks/__lib/handoff_v2.py"],
            "pending_operations": [],
        }
    }

    message = build_restore_message_compact(payload)

    # Must contain the key phrase "Based on the session handoff"
    assert "Based on the session handoff" in message, (
        "continuation_rule must explicitly reference 'session handoff' "
        "to frame goals as inference"
    )

    # Must contain "inference" to emphasize the epistemic status
    assert "inference" in message, (
        "continuation_rule must explicitly state the goal is an inference, not a recording"
    )

    # Must explicitly instruct AGAINST using "The task was" language
    # The rule should say "not 'The task was X'" as a negative example
    assert "not 'The task was X'" in message, (
        "continuation_rule must explicitly instruct against fact-stating language "
        "like 'The task was X'"
    )

    # Must still prevent asking user to restate context
    assert "Do not ask the user to restate context" in message or "Do not ask the user to re-explain context" in message, (
        "continuation_rule must still prevent asking user to restate existing context"
    )


def test_continuation_rule_prevents_passive_aggressive_deflection():
    """The continuation_rule must not contain language that encourages deflection.

    "whatever you said it was" is passive-aggressive deflection, not acknowledgment.
    The rule should encourage direct acknowledgment when corrected.
    """
    payload = {
        "resume_snapshot": {
            "goal": "test goal",
            "current_task": "test task",
            "progress_state": "pending",
            "progress_percent": 0,
            "next_step": "start",
            "blockers": [],
            "active_files": [],
            "pending_operations": [],
        }
    }

    message = build_restore_message_compact(payload)

    # This is a negative test — verify we don't have problematic patterns
    # The continuation_rule should encourage professional acknowledgment
    # rather than deflection
    assert "whatever" not in message.lower(), (
        "continuation_rule must not contain 'whatever' which enables deflection"
    )


def test_compact_restore_format_unchanged():
    """The overall compact-restore format must remain stable.

    Only the continuation_rule line changes — all other structure stays the same.
    """
    payload = {
        "resume_snapshot": {
            "goal": "test goal",
            "current_task": "test task",
            "progress_state": "in_progress",
            "progress_percent": 75,
            "next_step": "finish",
            "blockers": [],
            "active_files": ["test.py"],
            "pending_operations": [],
        }
    }

    message = build_restore_message_compact(payload)

    # Verify core format is intact
    assert "<compact-restore>" in message
    assert "status: restored" in message
    assert "goal:" in message
    assert "current_task:" in message
    assert "progress_state:" in message
    assert "progress_percent:" in message
    assert "next_step:" in message
    assert "continuation_rule:" in message
    assert "</compact-restore>" in message

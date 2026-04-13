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


def test_previous_session_does_not_leak_path():
    """previous_session must use placeholder, never raw transcript_path.

    SEC-004: Path traversal vulnerability — internal directory structure
    must not be exposed in restore messages.
    """
    payload = {
        "resume_snapshot": {
            "goal": "test goal",
            "current_task": "test task",
            "progress_state": "in_progress",
            "progress_percent": 50,
            "next_step": "continue",
            "blockers": [],
            "active_files": [],
            "pending_operations": [],
            "transcript_path": "C:\\Users\\brsth\\.claude\\projects\\P--\\very-long-session-id.jsonl",
        }
    }

    message = build_restore_message_compact(payload)

    # Must use placeholder, not raw path
    assert "<session transcript>" in message, (
        "previous_session must use placeholder '<session transcript>', "
        "not raw transcript_path"
    )
    # Must NOT contain any actual path components from the transcript_path
    assert "C:\\Users" not in message, "Must not leak Windows user path"
    assert ".jsonl" not in message, "Must not leak transcript file extension"
    assert "brsth" not in message, "Must not leak username from transcript_path"


def test_prior_transcript_path_none_is_handled():
    """prior_transcript_path=None is handled gracefully (first session, no chain)."""
    payload = {
        "resume_snapshot": {
            "goal": "first session",
            "current_task": "start",
            "progress_state": "in_progress",
            "progress_percent": 0,
            "next_step": "begin",
            "blockers": [],
            "active_files": [],
            "pending_operations": [],
            "transcript_path": "C:\\transcripts\\first.jsonl",
            "prior_transcript_path": None,
        }
    }

    message = build_restore_message_compact(payload)

    # Must still use placeholder (SEC-004 applies regardless of prior_transcript_path)
    assert "<session transcript>" in message
    # prior_transcript_path=None must not cause any formatting issues
    assert "</compact-restore>" in message


def test_transcript_chain_preserves_full_path_in_envelope():
    """Full transcript_path is preserved in envelope for chain walking.

    The transcript_path field must be stored in the envelope (not masked) so that
    chain-walking code can read actual transcripts. Only the restore message output
    is masked with '<session transcript>' placeholder.
    """
    from core.hooks.__lib.handoff_v2 import build_envelope, build_resume_snapshot

    snapshot = build_resume_snapshot(
        terminal_id="console_chain",
        source_session_id="session-b",
        goal="continue prior work",
        current_task="testing chain",
        progress_percent=50,
        progress_state="in_progress",
        blockers=[],
        active_files=[],
        pending_operations=[],
        next_step="verify chain",
        decision_refs=[],
        evidence_refs=[],
        transcript_path="C:\\transcripts\\session_b.jsonl",
        prior_transcript_path="C:\\transcripts\\session_a.jsonl",
        message_intent="instruction",
    )
    envelope = build_envelope(
        resume_snapshot=snapshot,
        decision_register=[],
        evidence_index=[],
    )

    # transcript_path must be present for chain walking
    assert envelope["resume_snapshot"]["transcript_path"] == "C:\\transcripts\\session_b.jsonl"
    # prior_transcript_path link must be present for chain traversal
    assert envelope["resume_snapshot"]["prior_transcript_path"] == "C:\\transcripts\\session_a.jsonl"


def test_transcript_chain_walks_via_prior_transcript_path():
    """Walking a 3-session chain via prior_transcript_path links.

    Chain: session_c → prior → session_b → prior → session_a → None
    Walking should produce: [session_c.jsonl, session_b.jsonl, session_a.jsonl]
    """
    from core.hooks.__lib.handoff_v2 import build_envelope, build_resume_snapshot

    # Build three envelopes simulating a 3-session chain
    snapshot_a = build_resume_snapshot(
        terminal_id="console_chain",
        source_session_id="session-a",
        goal="initial task",
        current_task="start",
        progress_percent=0,
        progress_state="pending",
        blockers=[],
        active_files=[],
        pending_operations=[],
        next_step="begin",
        decision_refs=[],
        evidence_refs=[],
        transcript_path="C:\\transcripts\\session_a.jsonl",
        prior_transcript_path=None,
        message_intent="instruction",
    )
    envelope_a = build_envelope(resume_snapshot=snapshot_a, decision_register=[], evidence_index=[])

    snapshot_b = build_resume_snapshot(
        terminal_id="console_chain",
        source_session_id="session-b",
        goal="continue prior work",
        current_task="testing",
        progress_percent=50,
        progress_state="in_progress",
        blockers=[],
        active_files=[],
        pending_operations=[],
        next_step="verify",
        decision_refs=[],
        evidence_refs=[],
        transcript_path="C:\\transcripts\\session_b.jsonl",
        prior_transcript_path="C:\\transcripts\\session_a.jsonl",
        message_intent="instruction",
    )
    envelope_b = build_envelope(resume_snapshot=snapshot_b, decision_register=[], evidence_index=[])

    snapshot_c = build_resume_snapshot(
        terminal_id="console_chain",
        source_session_id="session-c",
        goal="complete prior work",
        current_task="final testing",
        progress_percent=90,
        progress_state="in_progress",
        blockers=[],
        active_files=[],
        pending_operations=[],
        next_step="finish",
        decision_refs=[],
        evidence_refs=[],
        transcript_path="C:\\transcripts\\session_c.jsonl",
        prior_transcript_path="C:\\transcripts\\session_b.jsonl",
        message_intent="instruction",
    )
    envelope_c = build_envelope(resume_snapshot=snapshot_c, decision_register=[], evidence_index=[])

    # Simulate chain walking: resolve prior_transcript_path → load that transcript → repeat
    # In production this is done by reading the prior handoff file and extracting transcript_path
    chain_paths = []
    current = envelope_c
    for _ in range(3):  # max 3 hops to prevent infinite loop
        snap = current["resume_snapshot"]
        chain_paths.append(snap["transcript_path"])
        prior = snap.get("prior_transcript_path")
        if prior is None:
            break
        # In production: load next envelope from prior path
        # Here we simulate by mapping prior path to the next envelope in our test chain
        prior_map = {
            "C:\\transcripts\\session_b.jsonl": envelope_b,
            "C:\\transcripts\\session_a.jsonl": envelope_a,
        }
        current = prior_map.get(prior, {"resume_snapshot": {"prior_transcript_path": None}})

    assert chain_paths == [
        "C:\\transcripts\\session_c.jsonl",
        "C:\\transcripts\\session_b.jsonl",
        "C:\\transcripts\\session_a.jsonl",
    ]


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

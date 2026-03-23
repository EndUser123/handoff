#!/usr/bin/env python3
"""Tests for V2 restore and stale-hint message formatting."""

from __future__ import annotations

from core.hooks.__lib.handoff_v2 import (
    build_envelope,
    build_restore_message,
    build_resume_snapshot,
    build_stale_hint,
)


def _sample_payload():
    snapshot = build_resume_snapshot(
        terminal_id="console_demo",
        source_session_id="source-1",
        goal="Finish the restore rewrite",
        current_task="Patch SessionStart_handoff_restore.py",
        progress_percent=65,
        progress_state="in_progress",
        blockers=[],
        active_files=["P:/packages/handoff/core/hooks/SessionStart_handoff_restore.py"],
        pending_operations=[
            {
                "type": "edit",
                "target": "SessionStart_handoff_restore.py",
                "state": "in_progress",
            }
        ],
        next_step="Run the focused restore tests.",
        decision_refs=["dec_1"],
        evidence_refs=["ev_1"],
        transcript_path="P:/tmp/transcript.jsonl",
        message_intent="instruction",
    )
    return build_envelope(
        resume_snapshot=snapshot,
        decision_register=[
            {
                "id": "dec_1",
                "kind": "constraint",
                "summary": "Never auto-restore stale snapshots",
                "details": "Only restore fresh pending snapshots from the current terminal.",
                "priority": "critical",
                "applies_when": "Every SessionStart after compact",
                "source_refs": ["ev_1"],
            }
        ],
        evidence_index=[
            {
                "id": "ev_1",
                "type": "transcript",
                "label": "compact transcript",
                "path": "P:/tmp/transcript.jsonl",
            }
        ],
    )


def test_build_restore_message_contains_core_sections():
    message = build_restore_message(_sample_payload())

    assert "SESSION HANDOFF V2" in message
    assert "Goal: Finish the restore rewrite" in message
    assert "Current Task: Patch SessionStart_handoff_restore.py" in message
    assert "Active Decisions:" in message
    assert "Never auto-restore stale snapshots" in message


def test_build_stale_hint_exposes_only_metadata():
    payload = _sample_payload()
    message = build_stale_hint(payload, "snapshot expired")

    assert "HANDOFF NOT RESTORED" in message
    assert "Snapshot Created:" in message
    assert "Source Session:" in message
    assert "Goal:" not in message

#!/usr/bin/env python3
"""Tests for deterministic V2 checksum computation."""

from __future__ import annotations

from copy import deepcopy

from core.hooks.__lib.handoff_v2 import (
    build_envelope,
    build_resume_snapshot,
    compute_checksum,
)


def _payload():
    snapshot = build_resume_snapshot(
        terminal_id="console_checksum",
        source_session_id="session-1",
        goal="Test checksum stability",
        current_task="Test checksum stability",
        progress_percent=50,
        progress_state="in_progress",
        blockers=[],
        active_files=["checksum.py"],
        pending_operations=[],
        next_step="Verify checksum output",
        decision_refs=[],
        evidence_refs=["ev_1"],
        transcript_path="P:/tmp/transcript.jsonl",
        message_intent="instruction",
    )
    return build_envelope(
        resume_snapshot=snapshot,
        decision_register=[],
        evidence_index=[
            {
                "id": "ev_1",
                "type": "transcript",
                "label": "transcript",
                "path": "P:/tmp/transcript.jsonl",
            }
        ],
    )


def test_compute_checksum_is_stable_for_same_payload():
    payload = _payload()
    assert compute_checksum(payload) == compute_checksum(payload)


def test_compute_checksum_ignores_mutable_status_metadata():
    payload = _payload()
    updated = deepcopy(payload)
    updated["resume_snapshot"]["consumed_at"] = "2026-03-12T00:00:00+00:00"
    updated["resume_snapshot"]["consumed_by_session_id"] = "restore-session"

    assert compute_checksum(payload) == compute_checksum(updated)


def test_compute_checksum_changes_when_core_payload_changes():
    payload = _payload()
    updated = deepcopy(payload)
    updated["resume_snapshot"]["goal"] = "Different goal"

    assert compute_checksum(payload) != compute_checksum(updated)

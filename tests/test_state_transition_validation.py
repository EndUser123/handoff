#!/usr/bin/env python3
"""Tests for state transition validation in mark_snapshot_status()."""

from __future__ import annotations

import pytest

from core.hooks.__lib.handoff_v2 import (
    SNAPSHOT_CONSUMED,
    SNAPSHOT_PENDING,
    SNAPSHOT_REJECTED_INVALID,
    SNAPSHOT_REJECTED_STALE,
    SnapshotValidationError,
    build_envelope,
    build_resume_snapshot,
    mark_snapshot_status,
)


def _pending_snapshot() -> dict:
    """Create a snapshot in pending state."""
    snapshot = build_resume_snapshot(
        terminal_id="console_test",
        source_session_id="source",
        goal="test goal",
        current_task="test",
        progress_percent=50,
        progress_state="in_progress",
        blockers=[],
        active_files=[],
        pending_operations=[],
        next_step="Continue",
        decision_refs=[],
        evidence_refs=[],
        transcript_path="P:/fake/transcript.jsonl",
        message_intent="instruction",
    )
    # Override with a fake path for testing (validation happens in save_handoff)
    return build_envelope(
        resume_snapshot=snapshot,
        decision_register=[],
        evidence_index=[],
    )


def test_valid_transition_pending_to_consumed():
    """Test pending -> consumed is allowed."""
    payload = _pending_snapshot()
    result = mark_snapshot_status(
        payload, status=SNAPSHOT_CONSUMED, session_id="new_session"
    )
    assert result["resume_snapshot"]["status"] == SNAPSHOT_CONSUMED
    assert "consumed_at" in result["resume_snapshot"]
    assert result["resume_snapshot"]["consumed_by_session_id"] == "new_session"


def test_valid_transition_pending_to_rejected_stale():
    """Test pending -> rejected_stale is allowed."""
    payload = _pending_snapshot()
    result = mark_snapshot_status(
        payload,
        status=SNAPSHOT_REJECTED_STALE,
        session_id="new_session",
        reason="transcript changed",
    )
    assert result["resume_snapshot"]["status"] == SNAPSHOT_REJECTED_STALE
    assert "rejected_at" in result["resume_snapshot"]
    assert result["resume_snapshot"]["rejection_reason"] == "transcript changed"


def test_valid_transition_pending_to_rejected_invalid():
    """Test pending -> rejected_invalid is allowed."""
    payload = _pending_snapshot()
    result = mark_snapshot_status(
        payload,
        status=SNAPSHOT_REJECTED_INVALID,
        session_id="new_session",
        reason="checksum mismatch",
    )
    assert result["resume_snapshot"]["status"] == SNAPSHOT_REJECTED_INVALID


def test_invalid_transition_from_consumed_to_pending():
    """Test consumed -> pending is NOT allowed (terminal state)."""
    payload = _pending_snapshot()
    consumed = mark_snapshot_status(payload, status=SNAPSHOT_CONSUMED, session_id="s1")

    with pytest.raises(SnapshotValidationError, match="invalid state transition"):
        mark_snapshot_status(consumed, status=SNAPSHOT_PENDING, session_id="s2")


def test_invalid_transition_from_rejected_stale_to_consumed():
    """Test rejected_stale -> consumed is NOT allowed (terminal state)."""
    payload = _pending_snapshot()
    rejected = mark_snapshot_status(
        payload, status=SNAPSHOT_REJECTED_STALE, session_id="s1", reason="stale"
    )

    with pytest.raises(SnapshotValidationError, match="invalid state transition"):
        mark_snapshot_status(rejected, status=SNAPSHOT_CONSUMED, session_id="s2")


def test_invalid_transition_to_unknown_status():
    """Test transition to unknown status is rejected."""
    payload = _pending_snapshot()

    with pytest.raises(SnapshotValidationError, match="invalid target status"):
        mark_snapshot_status(payload, status="unknown_status", session_id="s2")


def test_double_rejection_is_invalid():
    """Test rejected_stale -> rejected_invalid is NOT allowed."""
    payload = _pending_snapshot()
    rejected_stale = mark_snapshot_status(
        payload, status=SNAPSHOT_REJECTED_STALE, session_id="s1", reason="stale"
    )

    with pytest.raises(SnapshotValidationError, match="invalid state transition"):
        mark_snapshot_status(
            rejected_stale, status=SNAPSHOT_REJECTED_INVALID, session_id="s2"
        )

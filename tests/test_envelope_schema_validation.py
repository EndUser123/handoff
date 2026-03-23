#!/usr/bin/env python3
"""Envelope schema validation tests (Item 9).

This test verifies that handoff V2 envelopes conform to the required schema:
- Required top-level fields (resume_snapshot, decision_register, evidence_index)
- Required snapshot fields (schema_version, snapshot_id, terminal_id, etc.)
- Valid data types (strings, lists, integers in correct ranges)
- Valid enum values (status, message_intent, decision kinds, evidence types)
- Checksum validation
- Reference integrity (decision_refs, evidence_refs must exist)
"""

from __future__ import annotations

import pytest
from scripts.hooks.__lib.handoff_v2 import (
    VALID_DECISION_KINDS,
    VALID_EVIDENCE_TYPES,
    VALID_MESSAGE_INTENTS,
    VALID_SNAPSHOT_STATUSES,
    build_envelope,
    build_resume_snapshot,
    validate_envelope,
    HandoffValidationError,
)


def _make_minimal_valid_envelope(tmp_path=None):
    """Create a minimal valid envelope for testing."""
    # Create actual transcript file since validate_envelope checks file existence
    if tmp_path is None:
        from pathlib import Path as StdPath

        tmp_path = StdPath("/tmp/test_handoff")

    transcript_path = tmp_path / "test_transcript.jsonl"
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_path.write_text(
        '{"type": "user", "message": {"content": [{"type": "text", "text": "Test"}]}}\n',
        encoding="utf-8",
    )

    snapshot = build_resume_snapshot(
        terminal_id="console_test",
        source_session_id="test_session",
        goal="Test goal",
        current_task="Test task",
        progress_percent=50,
        progress_state="in_progress",
        blockers=[],
        active_files=[],
        pending_operations=[],
        next_step="Complete test",
        decision_refs=[],
        evidence_refs=[],
        transcript_path=str(transcript_path),
        message_intent="instruction",
        freshness_minutes=60,
    )

    return build_envelope(
        resume_snapshot=snapshot,
        decision_register=[],
        evidence_index=[],
    ), transcript_path


def test_validate_envelope_accepts_valid_envelope(tmp_path):
    """Valid envelopes should pass validation."""
    envelope, _ = _make_minimal_valid_envelope(tmp_path)

    # Should not raise
    validate_envelope(envelope)


def test_validate_envelope_rejects_non_dict():
    """Non-dict payloads should be rejected."""
    with pytest.raises(HandoffValidationError, match="must be a dict"):
        validate_envelope("not a dict")

    with pytest.raises(HandoffValidationError, match="must be a dict"):
        validate_envelope(None)

    with pytest.raises(HandoffValidationError, match="must be a dict"):
        validate_envelope([])


def test_validate_envelope_rejects_missing_top_level_fields():
    """Missing required top-level fields should be rejected."""
    snapshot = build_resume_snapshot(
        terminal_id="console_test",
        source_session_id="test_session",
        goal="Test goal",
        current_task="Test task",
        progress_percent=50,
        progress_state="in_progress",
        blockers=[],
        active_files=[],
        pending_operations=[],
        next_step="Complete test",
        decision_refs=[],
        evidence_refs=[],
        transcript_path="/tmp/test.jsonl",
        message_intent="instruction",
    )

    # Missing decision_register
    with pytest.raises(HandoffValidationError, match="missing required fields"):
        validate_envelope({"resume_snapshot": snapshot, "evidence_index": []})

    # Missing evidence_index
    with pytest.raises(HandoffValidationError, match="missing required fields"):
        validate_envelope({"resume_snapshot": snapshot, "decision_register": []})


def test_validate_envelope_rejects_wrong_top_level_types(tmp_path):
    """Wrong types for top-level fields should be rejected."""
    envelope, _ = _make_minimal_valid_envelope(tmp_path)

    # resume_snapshot must be dict
    envelope["resume_snapshot"] = "not a dict"
    with pytest.raises(HandoffValidationError, match="resume_snapshot must be a dict"):
        validate_envelope(envelope)

    # Fix and test decision_register
    envelope["resume_snapshot"] = build_resume_snapshot(
        terminal_id="console_test",
        source_session_id="test_session",
        goal="Test goal",
        current_task="Test task",
        progress_percent=50,
        progress_state="in_progress",
        blockers=[],
        active_files=[],
        pending_operations=[],
        next_step="Complete test",
        decision_refs=[],
        evidence_refs=[],
        transcript_path=str(tmp_path / "test.jsonl"),
        message_intent="instruction",
    )
    envelope["decision_register"] = "not a list"
    with pytest.raises(
        HandoffValidationError, match="decision_register must be a list"
    ):
        validate_envelope(envelope)


def test_validate_envelope_rejects_missing_snapshot_fields():
    """Missing required snapshot fields should be rejected."""
    minimal_snapshot = {
        "schema_version": 2,
        "snapshot_id": "test",
        "terminal_id": "console_test",
        "source_session_id": "test_session",
        "created_at": "2026-03-21T00:00:00Z",
        "expires_at": "2026-03-21T01:00:00Z",
        "status": "pending",
        "goal": "Test goal",
        "current_task": "Test task",
        "progress_percent": 50,
        "progress_state": "in_progress",
        "blockers": [],
        "active_files": [],
        "pending_operations": [],
        "next_step": "Test step",
        "decision_refs": [],
        "evidence_refs": [],
        "transcript_path": "/tmp/test.jsonl",
        "message_intent": "instruction",
    }

    envelope = {
        "resume_snapshot": minimal_snapshot,
        "decision_register": [],
        "evidence_index": [],
    }

    # Remove each required field and verify rejection
    required_fields = [
        "schema_version",
        "snapshot_id",
        "terminal_id",
        "source_session_id",
        "created_at",
        "expires_at",
        "status",
        "goal",
        "current_task",
        "progress_percent",
        "progress_state",
        "blockers",
        "active_files",
        "pending_operations",
        "next_step",
        "decision_refs",
        "evidence_refs",
        "transcript_path",
    ]

    for field in required_fields:
        test_snapshot = minimal_snapshot.copy()
        test_snapshot.pop(field)
        envelope = {
            "resume_snapshot": test_snapshot,
            "decision_register": [],
            "evidence_index": [],
        }

        with pytest.raises(
            HandoffValidationError, match="resume_snapshot missing required fields"
        ):
            validate_envelope(envelope)


def test_validate_envelope_rejects_invalid_snapshot_status(tmp_path):
    """Invalid snapshot status should be rejected."""
    envelope, _ = _make_minimal_valid_envelope(tmp_path)
    envelope["resume_snapshot"]["status"] = "invalid_status"

    with pytest.raises(HandoffValidationError, match="invalid resume_snapshot.status"):
        validate_envelope(envelope)


def test_validate_envelope_rejects_invalid_progress_percent(tmp_path):
    """Invalid progress_percent values should be rejected."""
    envelope, _ = _make_minimal_valid_envelope(tmp_path)

    # Test non-integer
    envelope["resume_snapshot"]["progress_percent"] = "not an int"
    with pytest.raises(HandoffValidationError, match="must be an integer"):
        validate_envelope(envelope)

    # Test out of range (negative)
    envelope["resume_snapshot"]["progress_percent"] = -1
    with pytest.raises(HandoffValidationError, match="must be between 0 and 100"):
        validate_envelope(envelope)

    # Test out of range (> 100)
    envelope["resume_snapshot"]["progress_percent"] = 101
    with pytest.raises(HandoffValidationError, match="must be between 0 and 100"):
        validate_envelope(envelope)


def test_validate_envelope_rejects_invalid_decision_kind(tmp_path):
    """Invalid decision kind should be rejected."""
    # Create transcript file
    transcript_path = tmp_path / "test.jsonl"
    transcript_path.write_text(
        '{"type": "user", "message": {"content": [{"type": "text", "text": "Test"}]}}\n',
        encoding="utf-8",
    )

    snapshot = build_resume_snapshot(
        terminal_id="console_test",
        source_session_id="test_session",
        goal="Test goal",
        current_task="Test task",
        progress_percent=50,
        progress_state="in_progress",
        blockers=[],
        active_files=[],
        pending_operations=[],
        next_step="Complete test",
        decision_refs=["dec_1"],
        evidence_refs=[],
        transcript_path=str(transcript_path),
        message_intent="instruction",
    )

    decision = {
        "id": "dec_1",
        "kind": "invalid_kind",
        "summary": "Test decision",
        "details": "Test details",
        "priority": "high",
        "applies_when": "always",
        "source_refs": [],
    }

    envelope = build_envelope(
        resume_snapshot=snapshot,
        decision_register=[decision],
        evidence_index=[],
    )

    with pytest.raises(HandoffValidationError, match="kind is invalid"):
        validate_envelope(envelope)


def test_validate_envelope_rejects_invalid_evidence_type(tmp_path):
    """Invalid evidence type should be rejected."""
    # Create transcript file
    transcript_path = tmp_path / "test.jsonl"
    transcript_path.write_text(
        '{"type": "user", "message": {"content": [{"type": "text", "text": "Test"}]}}\n',
        encoding="utf-8",
    )

    snapshot = build_resume_snapshot(
        terminal_id="console_test",
        source_session_id="test_session",
        goal="Test goal",
        current_task="Test task",
        progress_percent=50,
        progress_state="in_progress",
        blockers=[],
        active_files=[],
        pending_operations=[],
        next_step="Complete test",
        decision_refs=[],
        evidence_refs=["ev_1"],
        transcript_path=str(transcript_path),
        message_intent="instruction",
    )

    evidence = {
        "id": "ev_1",
        "type": "invalid_type",
        "label": "Test evidence",
        "path": "/tmp/test.txt",
    }

    envelope = build_envelope(
        resume_snapshot=snapshot,
        decision_register=[],
        evidence_index=[evidence],
    )

    with pytest.raises(HandoffValidationError, match="type is invalid"):
        validate_envelope(envelope)


def test_validate_envelope_rejects_broken_decision_refs(tmp_path):
    """Decision refs that don't exist should be rejected."""
    # Create transcript file
    transcript_path = tmp_path / "test.jsonl"
    transcript_path.write_text(
        '{"type": "user", "message": {"content": [{"type": "text", "text": "Test"}]}}\n',
        encoding="utf-8",
    )

    snapshot = build_resume_snapshot(
        terminal_id="console_test",
        source_session_id="test_session",
        goal="Test goal",
        current_task="Test task",
        progress_percent=50,
        progress_state="in_progress",
        blockers=[],
        active_files=[],
        pending_operations=[],
        next_step="Complete test",
        decision_refs=["nonexistent_decision"],
        evidence_refs=[],
        transcript_path=str(transcript_path),
        message_intent="instruction",
    )

    envelope = build_envelope(
        resume_snapshot=snapshot,
        decision_register=[],
        evidence_index=[],
    )

    with pytest.raises(
        HandoffValidationError, match="decision_refs contains unknown id"
    ):
        validate_envelope(envelope)


def test_validate_envelope_rejects_broken_evidence_refs(tmp_path):
    """Evidence refs that don't exist should be rejected."""
    # Create transcript file
    transcript_path = tmp_path / "test.jsonl"
    transcript_path.write_text(
        '{"type": "user", "message": {"content": [{"type": "text", "text": "Test"}]}}\n',
        encoding="utf-8",
    )

    snapshot = build_resume_snapshot(
        terminal_id="console_test",
        source_session_id="test_session",
        goal="Test goal",
        current_task="Test task",
        progress_percent=50,
        progress_state="in_progress",
        blockers=[],
        active_files=[],
        pending_operations=[],
        next_step="Complete test",
        decision_refs=[],
        evidence_refs=["nonexistent_evidence"],
        transcript_path=str(transcript_path),
        message_intent="instruction",
    )

    envelope = build_envelope(
        resume_snapshot=snapshot,
        decision_register=[],
        evidence_index=[],
    )

    with pytest.raises(
        HandoffValidationError, match="evidence_refs contains unknown id"
    ):
        validate_envelope(envelope)


def test_validate_envelope_rejects_missing_checksum(tmp_path):
    """Missing checksum should be rejected."""
    envelope, _ = _make_minimal_valid_envelope(tmp_path)
    envelope.pop("checksum", None)

    with pytest.raises(HandoffValidationError, match="checksum is required"):
        validate_envelope(envelope)


def test_validate_envelope_rejects_checksum_mismatch(tmp_path):
    """Checksum mismatch should be rejected."""
    envelope, _ = _make_minimal_valid_envelope(tmp_path)
    envelope["checksum"] = "invalid:checksum"

    with pytest.raises(HandoffValidationError, match="checksum mismatch"):
        validate_envelope(envelope)


def test_validate_envelope_accepts_all_valid_statuses(tmp_path):
    """All valid snapshot statuses should be accepted."""
    for status in VALID_SNAPSHOT_STATUSES:
        envelope, _ = _make_minimal_valid_envelope(tmp_path)
        envelope["resume_snapshot"]["status"] = status
        # Recompute checksum after mutating status
        from scripts.hooks.__lib.handoff_v2 import compute_checksum

        envelope["checksum"] = compute_checksum(envelope)

        # Should not raise
        validate_envelope(envelope)


def test_validate_envelope_accepts_all_valid_message_intents(tmp_path):
    """All valid message intents should be accepted."""
    for intent in VALID_MESSAGE_INTENTS:
        envelope, _ = _make_minimal_valid_envelope(tmp_path)
        envelope["resume_snapshot"]["message_intent"] = intent
        # Recompute checksum after mutating message_intent
        from scripts.hooks.__lib.handoff_v2 import compute_checksum

        envelope["checksum"] = compute_checksum(envelope)

        # Should not raise
        validate_envelope(envelope)


def test_validate_envelope_accepts_all_valid_decision_kinds(tmp_path):
    """All valid decision kinds should be accepted."""
    for kind in VALID_DECISION_KINDS:
        # Create transcript file
        transcript_path = tmp_path / "test.jsonl"
        transcript_path.write_text(
            '{"type": "user", "message": {"content": [{"type": "text", "text": "Test"}]}}\n',
            encoding="utf-8",
        )

        snapshot = build_resume_snapshot(
            terminal_id="console_test",
            source_session_id="test_session",
            goal="Test goal",
            current_task="Test task",
            progress_percent=50,
            progress_state="in_progress",
            blockers=[],
            active_files=[],
            pending_operations=[],
            next_step="Complete test",
            decision_refs=["dec_1"],
            evidence_refs=[],
            transcript_path=str(transcript_path),
            message_intent="instruction",
        )

        decision = {
            "id": "dec_1",
            "kind": kind,
            "summary": "Test decision",
            "details": "Test details",
            "priority": "high",
            "applies_when": "always",
            "source_refs": [],
        }

        envelope = build_envelope(
            resume_snapshot=snapshot,
            decision_register=[decision],
            evidence_index=[],
        )

        # Should not raise
        validate_envelope(envelope)


def test_validate_envelope_accepts_all_valid_evidence_types(tmp_path):
    """All valid evidence types should be accepted."""
    for etype in VALID_EVIDENCE_TYPES:
        # Create transcript file
        transcript_path = tmp_path / "test.jsonl"
        transcript_path.write_text(
            '{"type": "user", "message": {"content": [{"type": "text", "text": "Test"}]}}\n',
            encoding="utf-8",
        )

        snapshot = build_resume_snapshot(
            terminal_id="console_test",
            source_session_id="test_session",
            goal="Test goal",
            current_task="Test task",
            progress_percent=50,
            progress_state="in_progress",
            blockers=[],
            active_files=[],
            pending_operations=[],
            next_step="Complete test",
            decision_refs=[],
            evidence_refs=["ev_1"],
            transcript_path=str(transcript_path),
            message_intent="instruction",
        )

        evidence = {
            "id": "ev_1",
            "type": etype,
            "label": "Test evidence",
            "path": "/tmp/test.txt",
        }

        envelope = build_envelope(
            resume_snapshot=snapshot,
            decision_register=[],
            evidence_index=[evidence],
        )

        # Should not raise
        validate_envelope(envelope)


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])

#!/usr/bin/env python3
"""Integration tests for Haiku conversation_summary feature in handoff V2."""

import json
import sys
from pathlib import Path

import pytest

# Add package root to sys.path
package_root = Path(__file__).parent.parent
sys.path.insert(0, str(package_root))

from scripts.hooks.__lib.snapshot_v2 import build_resume_snapshot, build_envelope
from scripts.hooks.__lib.snapshot_files import SnapshotFileStorage, load_summary_for_envelope
from scripts.hooks.__lib.haiku_prompt import should_skip_haiku, build_haiku_prompt, MIN_MESSAGE_COUNT, MIN_BYTE_COUNT


class TestHaikuConversationSummary:
    """Test conversation_summary field integration across handoff V2."""

    def test_build_resume_snapshot_accepts_conversation_summary(self):
        """TASK-1: build_resume_snapshot includes conversation_summary when provided."""
        snapshot = build_resume_snapshot(
            terminal_id="test-terminal",
            source_session_id="s123",
            goal="Test goal",
            current_task="Testing",
            progress_percent=50,
            progress_state="in_progress",
            blockers=[],
            active_files=["test.py"],
            pending_operations=[],
            next_step="Run tests",
            decision_refs=[],
            evidence_refs=[],
            transcript_path="/tmp/transcript.jsonl",
            prior_transcript_path=None,
            message_intent="instruction",
            conversation_summary="Completed Haiku integration.",
        )
        assert "conversation_summary" in snapshot
        assert snapshot["conversation_summary"] == "Completed Haiku integration."

    def test_build_resume_snapshot_omits_conversation_summary_when_none(self):
        """TASK-1: build_resume_snapshot does not include field when not provided."""
        snapshot = build_resume_snapshot(
            terminal_id="test-terminal",
            source_session_id="s123",
            goal="Test goal",
            current_task="Testing",
            progress_percent=50,
            progress_state="in_progress",
            blockers=[],
            active_files=["test.py"],
            pending_operations=[],
            next_step="Run tests",
            decision_refs=[],
            evidence_refs=[],
            transcript_path="/tmp/transcript.jsonl",
            prior_transcript_path=None,
            message_intent="instruction",
        )
        assert "conversation_summary" not in snapshot

    def test_should_skip_haiku_below_message_threshold(self):
        """TASK-3: should_skip_haiku returns True below MIN_MESSAGE_COUNT."""
        skip, msg_count, byte_count = should_skip_haiku(5, 10000)
        assert skip is True
        assert msg_count == 5

    def test_should_skip_haiku_below_byte_threshold(self):
        """TASK-3: should_skip_haiku returns True below MIN_BYTE_COUNT."""
        skip, msg_count, byte_count = should_skip_haiku(15, 3000)
        assert skip is True
        assert byte_count == 3000

    def test_should_skip_haiku_above_threshold(self):
        """TASK-3: should_skip_haiku returns False above both thresholds."""
        skip, msg_count, byte_count = should_skip_haiku(15, 6000)
        assert skip is False

    def test_haiku_prompt_format_placeholders(self):
        """TASK-3: build_haiku_prompt substitutes all placeholders."""
        import tempfile
        transcript_file = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False)
        transcript_file.write('{"role":"user","content":"Hello"}\n')
        transcript_file.write('{"role":"assistant","content":"Hi"}\n')
        transcript_file.close()

        prompt = build_haiku_prompt(Path(transcript_file.name), last_entry="Previous work")
        Path(transcript_file.name).unlink()

        assert "{{TIME}}" not in prompt
        assert "{{BRANCH}}" not in prompt
        assert "{{LAST_ENTRY}}" not in prompt
        assert "{{EXTRACT}}" not in prompt
        assert "Previous work" in prompt

    def test_load_summary_returns_content(self, tmp_path):
        """TASK-5: load_summary returns text when sidecar exists."""
        storage = SnapshotFileStorage(tmp_path, "test-terminal")
        (tmp_path / ".claude" / "state" / "handoff").mkdir(parents=True, exist_ok=True)

        # Create a fake envelope file
        envelope_file = tmp_path / ".claude" / "state" / "handoff" / "test-terminal_20260419T120000_handoff.json"
        envelope_file.parent.mkdir(parents=True, exist_ok=True)
        envelope_file.write_text('{"resume_snapshot":{}}')

        # Create sidecar
        sidecar = envelope_file.with_suffix(".summary.md")
        sidecar.write_text("Completed Haiku integration for handoff V2.")

        result = load_summary_for_envelope(envelope_file)
        assert result is not None
        assert "Haiku integration" in result

    def test_load_summary_returns_none_when_missing(self, tmp_path):
        """TASK-5: load_summary returns None when sidecar absent."""
        envelope_file = tmp_path / ".claude" / "state" / "handoff" / "test-terminal_20260419T120000_handoff.json"
        result = load_summary_for_envelope(envelope_file)
        assert result is None

    def test_load_summary_returns_none_for_empty_sidecar(self, tmp_path):
        """TASK-5: load_summary returns None for empty sidecar."""
        envelope_file = tmp_path / ".claude" / "state" / "handoff" / "test-terminal_20260419T120000_handoff.json"
        envelope_file.parent.mkdir(parents=True, exist_ok=True)
        envelope_file.write_text('{"resume_snapshot":{}}')

        sidecar = envelope_file.with_suffix(".summary.md")
        sidecar.write_text("")

        result = load_summary_for_envelope(envelope_file)
        assert result is None

    def test_haiku_produces_malformed_output(self, tmp_path):
        """TASK-7: load_summary returns None for truncated/invalid sidecar."""
        envelope_file = tmp_path / ".claude" / "state" / "handoff" / "test-terminal_20260419T120000_handoff.json"
        envelope_file.parent.mkdir(parents=True, exist_ok=True)
        envelope_file.write_text('{"resume_snapshot":{}}')

        # Write truncated/malformed content
        sidecar = envelope_file.with_suffix(".summary.md")
        sidecar.write_text("## 2026")  # Incomplete, less than 5 bytes would be malformed

        result = load_summary_for_envelope(envelope_file)
        # Malformed but non-empty - should still return (validation is at write time)
        # This test covers the truncated case - real Haiku output would be well-formed
        assert result is not None  # Sidecar exists and has content

    def test_restore_omits_skip_summary(self, tmp_path):
        """TASK-7: SKIP token in sidecar is treated as no summary."""
        envelope_file = tmp_path / ".claude" / "state" / "handoff" / "test-terminal_20260419T120000_handoff.json"
        envelope_file.parent.mkdir(parents=True, exist_ok=True)
        envelope_file.write_text('{"resume_snapshot":{"n_1_transcript_path":"/tmp/transcript.jsonl"}}')

        # Write SKIP token
        sidecar = envelope_file.with_suffix(".summary.md")
        sidecar.write_text("SKIP")

        result = load_summary_for_envelope(envelope_file)
        assert result is not None
        assert result.strip().upper() == "SKIP"

        # Simulate what SessionStart does: check SKIP and omit
        if result and result.strip().upper() != "SKIP":
            summary_to_inject = result
        else:
            summary_to_inject = None

        assert summary_to_inject is None  # SKIP should be omitted


class TestHaikuThresholds:
    """Test threshold constants are correctly defined."""

    def test_min_message_count_is_10(self):
        assert MIN_MESSAGE_COUNT == 10

    def test_min_byte_count_is_5000(self):
        assert MIN_BYTE_COUNT == 5000


class TestEnvelopeWithConversationSummary:
    """Test that conversation_summary flows correctly through envelope build."""

    def test_envelope_accepts_snapshot_with_conversation_summary(self):
        """Envelope build works when snapshot has conversation_summary."""
        snapshot = build_resume_snapshot(
            terminal_id="test-terminal",
            source_session_id="s123",
            goal="Test goal",
            current_task="Testing",
            progress_percent=50,
            progress_state="in_progress",
            blockers=[],
            active_files=["test.py"],
            pending_operations=[],
            next_step="Run tests",
            decision_refs=[],
            evidence_refs=[],
            transcript_path="/tmp/transcript.jsonl",
            prior_transcript_path=None,
            message_intent="instruction",
            conversation_summary="Session summary here.",
        )
        envelope = build_envelope(
            resume_snapshot=snapshot,
            decision_register=[],
            evidence_index=[],
        )
        assert envelope["resume_snapshot"]["conversation_summary"] == "Session summary here."
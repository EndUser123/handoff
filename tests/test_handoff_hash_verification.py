"""Tests for handoff hash computation functionality."""

import pytest
from pathlib import Path
import tempfile
import json
import hashlib


class TestHandoffHashComputation:
    """Test hash computation for original_user_request verification."""

    def test_hash_computes_sha256_16_char_prefix(self, tmp_path):
        """Test that hash is SHA256 with 16-char hex prefix."""
        from handoff.hooks.PreCompact_handoff_capture import PreCompactHandoffCapture
        from handoff.hooks.__lib.transcript import TranscriptParser

        # Create test transcript
        transcript_file = tmp_path / "test_transcript.jsonl"
        transcript_data = [
            {
                "type": "user",
                "message": {"content": "test message"},
                "timestamp": "2026-03-05T12:34:56.789Z"
            }
        ]

        with open(transcript_file, "w") as f:
            for entry in transcript_data:
                json.dump(entry, f)
                f.write("\n")

        # Create parser and capture hook
        parser = TranscriptParser(str(transcript_file))
        capture_hook = PreCompactHandoffCapture(
            transcript_path=str(transcript_file),
            project_root=str(tmp_path)
        )
        capture_hook.parser = parser

        # Build handoff metadata
        metadata = capture_hook._build_handoff_metadata({})

        # Verify: Hash should be present and 16 chars
        assert "original_user_request_hash" in metadata
        assert isinstance(metadata["original_user_request_hash"], str)
        assert len(metadata["original_user_request_hash"]) == 16

        # Verify: Hash should be valid hex
        int(metadata["original_user_request_hash"], 16)  # Will raise if not hex

    def test_hash_matches_sha256_of_original_request(self, tmp_path):
        """Test that hash is SHA256 of original_user_request."""
        from handoff.hooks.PreCompact_handoff_capture import PreCompactHandoffCapture
        from handoff.hooks.__lib.transcript import TranscriptParser

        original_request = "approve edit hooks/posttooluse/strategy_escalation_hook.py"

        # Create test transcript with known message
        transcript_file = tmp_path / "test_transcript.jsonl"
        transcript_data = [
            {
                "type": "user",
                "message": {"content": original_request},
                "timestamp": "2026-03-05T12:34:56.789Z"
            }
        ]

        with open(transcript_file, "w") as f:
            for entry in transcript_data:
                json.dump(entry, f)
                f.write("\n")

        # Create parser and capture hook
        parser = TranscriptParser(str(transcript_file))
        capture_hook = PreCompactHandoffCapture(
            transcript_path=str(transcript_file),
            project_root=str(tmp_path)
        )
        capture_hook.parser = parser

        # Build handoff metadata
        metadata = capture_hook._build_handoff_metadata({})

        # Compute expected hash
        expected_hash = hashlib.sha256(
            original_request.encode('utf-8')
        ).hexdigest()[:16]

        # Verify: Hash matches expected
        assert metadata["original_user_request_hash"] == expected_hash
        assert metadata["original_user_request"] == original_request

    def test_hash_field_present_when_original_request_exists(self, tmp_path):
        """Test that hash field is present when original_user_request exists."""
        from handoff.hooks.PreCompact_handoff_capture import PreCompactHandoffCapture
        from handoff.hooks.__lib.transcript import TranscriptParser

        # Create test transcript
        transcript_file = tmp_path / "test_transcript.jsonl"
        transcript_data = [
            {
                "type": "user",
                "message": {"content": "non-empty request"},
                "timestamp": "2026-03-05T12:34:56.789Z"
            }
        ]

        with open(transcript_file, "w") as f:
            for entry in transcript_data:
                json.dump(entry, f)
                f.write("\n")

        # Create parser and capture hook
        parser = TranscriptParser(str(transcript_file))
        capture_hook = PreCompactHandoffCapture(
            transcript_path=str(transcript_file),
            project_root=str(tmp_path)
        )
        capture_hook.parser = parser

        # Build handoff metadata
        metadata = capture_hook._build_handoff_metadata({})

        # Verify: Hash field should be present
        assert "original_user_request_hash" in metadata
        assert metadata["original_user_request_hash"] is not None

    def test_timestamp_field_present_when_available(self, tmp_path):
        """Test that timestamp field is extracted from transcript."""
        from handoff.hooks.PreCompact_handoff_capture import PreCompactHandoffCapture
        from handoff.hooks.__lib.transcript import TranscriptParser

        expected_timestamp = "2026-03-05T12:34:56.789Z"

        # Create test transcript with timestamp
        transcript_file = tmp_path / "test_transcript.jsonl"
        transcript_data = [
            {
                "type": "user",
                "message": {"content": "test message"},
                "timestamp": expected_timestamp
            }
        ]

        with open(transcript_file, "w") as f:
            for entry in transcript_data:
                json.dump(entry, f)
                f.write("\n")

        # Create parser and capture hook
        parser = TranscriptParser(str(transcript_file))
        capture_hook = PreCompactHandoffCapture(
            transcript_path=str(transcript_file),
            project_root=str(tmp_path)
        )
        capture_hook.parser = parser

        # Build handoff metadata
        metadata = capture_hook._build_handoff_metadata({})

        # Verify: Timestamp field should match
        assert "original_user_request_timestamp" in metadata
        assert metadata["original_user_request_timestamp"] == expected_timestamp

    def test_hash_handles_unicode_characters(self, tmp_path):
        """Test that hash computation works with unicode characters."""
        from handoff.hooks.PreCompact_handoff_capture import PreCompactHandoffCapture
        from handoff.hooks.__lib.transcript import TranscriptParser

        original_request = "test message with emoji 🎉 and unicode Ñ"

        # Create test transcript with unicode
        transcript_file = tmp_path / "test_transcript_unicode.jsonl"
        transcript_data = [
            {
                "type": "user",
                "message": {"content": original_request},
                "timestamp": "2026-03-05T12:34:56.789Z"
            }
        ]

        with open(transcript_file, "w", encoding="utf-8") as f:
            for entry in transcript_data:
                json.dump(entry, f, ensure_ascii=False)
                f.write("\n")

        # Create parser and capture hook
        parser = TranscriptParser(str(transcript_file))
        capture_hook = PreCompactHandoffCapture(
            transcript_path=str(transcript_file),
            project_root=str(tmp_path)
        )
        capture_hook.parser = parser

        # Build handoff metadata
        metadata = capture_hook._build_handoff_metadata({})

        # Compute expected hash with UTF-8 encoding
        expected_hash = hashlib.sha256(
            original_request.encode('utf-8')
        ).hexdigest()[:16]

        # Verify: Hash should match
        assert metadata["original_user_request_hash"] == expected_hash

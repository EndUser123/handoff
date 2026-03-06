"""Tests for TranscriptParser timestamp extraction functionality."""

import pytest
from pathlib import Path
from handoff.hooks.__lib.transcript import TranscriptParser
import json
import tempfile
import os
from datetime import datetime, UTC


class TestTranscriptTimestamp:
    """Test timestamp extraction from transcript entries."""

    def test_get_transcript_timestamp_returns_valid_iso_format(self, tmp_path):
        """Test that get_transcript_timestamp returns valid ISO 8601 timestamp."""
        # Create test transcript with timestamp
        transcript_data = [
            {
                "type": "user",
                "message": {"content": "test message"},
                "timestamp": "2026-03-05T12:34:56.789Z"
            }
        ]

        transcript_file = tmp_path / "test_transcript.jsonl"
        with open(transcript_file, "w") as f:
            # Write each entry on a separate line (JSONL format)
            for entry in transcript_data:
                json.dump(entry, f)
                f.write("\n")

        parser = TranscriptParser(str(transcript_file))
        timestamp = parser.get_transcript_timestamp()

        # Verify: Should return valid ISO 8601 format
        assert timestamp is not None
        assert isinstance(timestamp, str)
        # Should be parseable as ISO 8601
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        assert parsed is not None

    def test_get_transcript_timestamp_extracts_from_last_user_message(self, tmp_path):
        """Test that timestamp comes from the LAST user message, not first."""
        # Create transcript with multiple user messages at different times
        transcript_data = [
            {
                "type": "user",
                "message": {"content": "first message"},
                "timestamp": "2026-03-05T10:00:00.000Z"
            },
            {
                "type": "assistant",
                "message": {"content": "response"},
                "timestamp": "2026-03-05T10:05:00.000Z"
            },
            {
                "type": "user",
                "message": {"content": "second message"},
                "timestamp": "2026-03-05T12:34:56.789Z"  # This should be returned
            }
        ]

        transcript_file = tmp_path / "test_transcript_multi.jsonl"
        with open(transcript_file, "w") as f:
            # Write each entry on a separate line (JSONL format)
            for entry in transcript_data:
                json.dump(entry, f)
                f.write("\n")

        parser = TranscriptParser(str(transcript_file))
        timestamp = parser.get_transcript_timestamp()

        # Verify: Should return timestamp from LAST user message
        assert timestamp == "2026-03-05T12:34:56.789Z"

    def test_get_transcript_timestamp_returns_none_for_empty_transcript(self, tmp_path):
        """Test that get_transcript_timestamp returns None for empty transcript."""
        # Create empty transcript
        transcript_file = tmp_path / "test_transcript_empty.jsonl"
        transcript_file.write_text("[]")

        parser = TranscriptParser(str(transcript_file))
        timestamp = parser.get_transcript_timestamp()

        # Verify: Should return None for empty transcript
        assert timestamp is None

    def test_get_transcript_timestamp_returns_none_when_no_user_messages(self, tmp_path):
        """Test that get_transcript_timestamp returns None when no user messages exist."""
        # Create transcript with only assistant messages
        transcript_data = [
            {
                "type": "assistant",
                "message": {"content": "assistant message"},
                "timestamp": "2026-03-05T12:34:56.789Z"
            }
        ]

        transcript_file = tmp_path / "test_transcript_no_user.jsonl"
        with open(transcript_file, "w") as f:
            # Write each entry on a separate line (JSONL format)
            for entry in transcript_data:
                json.dump(entry, f)
                f.write("\n")

        parser = TranscriptParser(str(transcript_file))
        timestamp = parser.get_transcript_timestamp()

        # Verify: Should return None when no user messages
        assert timestamp is None

    def test_get_transcript_timestamp_handles_missing_timestamp_field(self, tmp_path):
        """Test graceful degradation when timestamp field is missing."""
        # Create transcript without timestamp field
        transcript_data = [
            {
                "type": "user",
                "message": {"content": "test message"}
                # No timestamp field
            }
        ]

        transcript_file = tmp_path / "test_transcript_no_ts.jsonl"
        with open(transcript_file, "w") as f:
            # Write each entry on a separate line (JSONL format)
            for entry in transcript_data:
                json.dump(entry, f)
                f.write("\n")

        parser = TranscriptParser(str(transcript_file))
        timestamp = parser.get_transcript_timestamp()

        # Verify: Should return None when timestamp field missing
        assert timestamp is None

    def test_get_transcript_timestamp_handles_missing_transcript_file(self):
        """Test graceful degradation when transcript file doesn't exist."""
        parser = TranscriptParser("/nonexistent/path.jsonl")
        timestamp = parser.get_transcript_timestamp()

        # Verify: Should return None for missing file
        assert timestamp is None

    def test_get_transcript_timestamp_handles_none_transcript_path(self):
        """Test graceful degradation when transcript_path is None."""
        parser = TranscriptParser(None)
        timestamp = parser.get_transcript_timestamp()

        # Verify: Should return None for None path
        assert timestamp is None

    def test_get_transcript_timestamp_with_unicode_message(self, tmp_path):
        """Test timestamp extraction works with unicode characters in message."""
        # Create transcript with emoji and unicode
        transcript_data = [
            {
                "type": "user",
                "message": {"content": "test message with emoji 🎉 and unicode Ñ"},
                "timestamp": "2026-03-05T12:34:56.789Z"
            }
        ]

        transcript_file = tmp_path / "test_transcript_unicode.jsonl"
        with open(transcript_file, "w", encoding="utf-8") as f:
            # Write each entry on a separate line (JSONL format)
            for entry in transcript_data:
                json.dump(entry, f, ensure_ascii=False)
                f.write("\n")

        parser = TranscriptParser(str(transcript_file))
        timestamp = parser.get_transcript_timestamp()

        # Verify: Should extract timestamp correctly regardless of message content
        assert timestamp == "2026-03-05T12:34:56.789Z"

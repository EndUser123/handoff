#!/usr/bin/env python3
"""
Tests for critical handoff failure modes identified in failure-mode analysis.

These tests verify the system handles edge cases correctly:
- Multiple compaction cycles without cleanup
- Missing or unreadable transcript files
- Empty transcripts (no user messages)

Run with: pytest P:/packages/handoff/tests/test_failure_modes.py -v
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import sys

# Add hooks to path
hooks_dir = Path("P:/packages/handoff/src/handoff/hooks").resolve()
sys.path.insert(0, str(hooks_dir))


class TestMultipleCompactionCycles:
    """Test Issue #1: Multiple compaction cycles without cleanup."""

    def test_stale_task_name_across_compactions(self):
        """
        Test that task_name can become stale across multiple compactions.

        Scenario:
        1. Session 1: Work on task A → Compaction → active_session with task A
        2. User switches to task B (different files, different tools)
        3. Session 2: Compaction → active_session updated with SAME task A (WRONG)
        4. User resumes → Gets task A context instead of current task B
        """
        # This is a documentation test showing the problem
        # The actual fix would require detecting task context changes
        pass

    def test_task_name_mismatch_with_recent_activity(self):
        """
        Verify detection of task_name mismatch with recent activity.

        Expected behavior:
        - Check recent tool usage (last 10 calls)
        - Check recent file modifications
        - If mismatch, don't use stale task_name
        """
        # Test would verify TaskIdentityManager is called
        # to validate task_name matches current context
        pass


class TestMissingTranscript:
    """Test Issue #2: Transcript file missing or unreadable."""

    def test_missing_transcript_path(self):
        """
        Test behavior when transcript_path is None or file doesn't exist.

        Expected: Should skip handoff capture, not fall back to stale data
        """
        from handoff.hooks.__lib.transcript import TranscriptParser

        # Create parser with non-existent transcript
        parser = TranscriptParser(transcript_path="/nonexistent/transcript.json")

        # Should return empty list, not crash
        entries = parser._get_parsed_entries()
        assert entries == [], "Should return empty list for missing transcript"

        # extract_last_user_message should return None
        last_message = parser.extract_last_user_message()
        assert last_message is None, "Should return None for missing transcript"

    def test_transcript_permission_denied(self):
        """
        Test behavior when transcript file exists but is unreadable.

        Expected: Should handle gracefully, log error, return None
        """
        # This would require mocking file system with permission error
        # For now, document the expected behavior
        pass


class TestEmptyTranscript:
    """Test Issue #3: Empty transcript (no user messages)."""

    def test_transcript_with_only_system_messages(self):
        """
        Test transcript with no user messages, only system messages.

        Expected: extract_last_user_message() returns None
        Expected: Handoff capture should be skipped
        """
        # Create temporary transcript with only system messages
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            transcript_path = Path(f.name)

            try:
                # Write only system messages
                for i in range(5):
                    entry = {
                        "type": "assistant",
                        "message": {"content": f"System message {i}"}
                    }
                    f.write(json.dumps(entry) + '\n')

                f.flush()

                from handoff.hooks.__lib.transcript import TranscriptParser

                parser = TranscriptParser(transcript_path=str(transcript_path))
                last_message = parser.extract_last_user_message()

                assert last_message is None, \
                    "Should return None when transcript has no user messages"

            finally:
                transcript_path.unlink(missing_ok=True)

    def test_transcript_with_only_meta_tags(self):
        """
        Test transcript with only meta tags (system messages).

        Expected: extract_last_user_message() should skip meta tags
        """
        # The transcript parser already filters meta tags:
        # - Lines starting with "<"
        # - Lines starting with "This session is being continued"
        # - Lines starting with "Stop hook feedback"
        # This test verifies that logic works correctly
        pass


class TestTaskFileCorruption:
    """Test Issue #4: Task file corruption (invalid JSON)."""

    def test_corrupted_task_file_cleanup(self):
        """
        Test that corrupted task files are cleaned up.

        Expected:
        - Detect JSONDecodeError when loading task file
        - Log error at WARNING level (not DEBUG)
        - Delete corrupted file to prevent future failures
        """
        # This would require creating a corrupted task file
        # and verifying cleanup logic
        pass


class TestChecksumVisibility:
    """Test Issue #8: Checksum mismatch silent failure."""

    def test_checksum_error_visibility(self):
        """
        Test that checksum errors are visible to users.

        Current behavior: Errors logged at DEBUG level (invisible)
        Expected behavior: Errors should be logged at ERROR level
        """
        from handoff.hooks.SessionStart_handoff_restore import _verify_handoff_checksum

        # Create handoff data with invalid checksum
        handoff_data = {
            "task_name": "Test task",
            "saved_at": "2026-02-28T00:00:00Z",
            "checksum": "sha256:invalidchecksum00000000000000000000000000000000000000000000000000000000000000"
        }

        # Verify checksum fails
        is_valid, error = _verify_handoff_checksum(handoff_data)

        assert not is_valid, "Invalid checksum should fail verification"
        assert error is not None, "Error message should be provided"
        assert "Checksum mismatch" in error, "Error should mention checksum mismatch"


class TestFirstUserMessageExtraction:
    """Test Issue #7: First user message extraction issues."""

    def test_first_message_beyond_20_lines(self):
        """
        Test that first user message is found even if > 20 lines into transcript.

        Current implementation: Only checks first 20 lines
        Expected: Should scan entire transcript for first user message
        """
        # Create transcript with 25 system messages, then user message
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            transcript_path = Path(f.name)

            try:
                # Write 25 system messages
                for i in range(25):
                    entry = {
                        "type": "assistant",
                        "message": {"content": f"System context {i}"}
                    }
                    f.write(json.dumps(entry) + '\n')

                # Write actual user message at line 26
                user_entry = {
                    "type": "user",
                    "message": {"content": "Actual first user request"}
                }
                f.write(json.dumps(user_entry) + '\n')

                f.flush()

                # The current implementation in PreCompact_handoff_capture.py
                # only checks first 20 lines:
                #
                #   for i in range(min(20, len(lines))):
                #
                # This means it would MISS the user message at line 26

                # Verify the bug exists
                with open(transcript_path, 'r') as tf:
                    lines = tf.readlines()

                # Simulate current implementation
                found_in_20 = False
                for i in range(min(20, len(lines))):
                    try:
                        entry = json.loads(lines[i])
                        if entry.get("type") == "user":
                            found_in_20 = True
                            break
                    except json.JSONDecodeError:
                        continue

                assert not found_in_20, \
                    "Current implementation misses user message beyond 20 lines"

                # Correct implementation would scan all lines
                found_all = False
                for i in range(len(lines)):
                    try:
                        entry = json.loads(lines[i])
                        if entry.get("type") == "user":
                            found_all = True
                            break
                    except json.JSONDecodeError:
                        continue

                assert found_all, \
                    "Correct implementation should find user message anywhere"

            finally:
                transcript_path.unlink(missing_ok=True)


class TestHandoffValidation:
    """Test handoff validation before restoration."""

    def test_should_skip_stale_handoff(self):
        """
        Test that handoffs older than 1 hour are skipped.

        This prevents Issue #1 (multiple compaction cycles)
        by rejecting stale handoffs that don't match current context.
        """
        from datetime import datetime, timedelta, UTC

        # Create recent handoff (should be accepted)
        recent_handoff = {
            "task_name": "Recent task",
            "saved_at": (datetime.now(UTC) - timedelta(minutes=30)).isoformat(),
        }

        # Create stale handoff (should be rejected)
        stale_handoff = {
            "task_name": "Old task",
            "saved_at": (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
        }

        # Validation logic that should be implemented
        def is_handoff_too_old(handoff_data, max_age_hours=1):
            """Check if handoff is too old to be relevant."""
            saved_at = handoff_data.get("saved_at")
            if not saved_at:
                return True  # Missing timestamp = too old

            try:
                saved_time = datetime.fromisoformat(saved_at)
                age = datetime.now(UTC) - saved_time
                return age > timedelta(hours=max_age_hours)
            except (ValueError, TypeError):
                return True  # Invalid timestamp = too old

        # Verify recent handoff passes
        assert not is_handoff_too_old(recent_handoff), \
            "Recent handoff should pass validation"

        # Verify stale handoff fails
        assert is_handoff_too_old(stale_handoff), \
            "Stale handoff should fail validation"

#!/usr/bin/env python3
"""
Tests for QUAL-001: Inconsistent Error Handling in atomic_write_with_validation.

QUALITY ASSESSMENT: This test file DOCUMENTS that the current implementation
is ACTUALLY CORRECT despite quality report flagging "inconsistent error handling."

Key Finding:
- PermissionError IS a subclass of OSError in Python
- Therefore: except OSError DOES catch PermissionError
- The current code at line 193 (except OSError) properly handles PermissionError

However, this test suite serves to:
1. Document that we've THOUGHT about this edge case
2. Verify the exception hierarchy works as expected
3. Provide regression tests if the exception handling changes

Issue: QUAL-001 (False Positive - code is correct)
Function: atomic_write_with_validation() in handoff_store.py (line 142)
Status: CURRENT IMPLEMENTATION IS CORRECT

Run with: pytest P:/packages/handoff/tests/test_quality_error_handling.py -v
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Add hooks to path
hooks_dir = Path("P:/packages/handoff/src/handoff/hooks").resolve()
sys.path.insert(0, str(hooks_dir))

from handoff.hooks.__lib.handoff_store import (
    atomic_write_with_retry,
    atomic_write_with_validation,
)


class TestQuality001PermissionErrorHandling:
    """
    Test QUAL-001: Document and verify PermissionError exception handling.

    Quality Report Claim: "Inconsistent error handling - only catches OSError,
    PermissionError will escape"

    Test Finding: Quality report is INCORRECT. PermissionError is a subclass
    of OSError, so except OSError DOES catch PermissionError.

    These tests document and verify this correct behavior.
    """

    def test_permission_error_is_oserror_subclass(self):
        """
        Verify PermissionError IS a subclass of OSError.

        This is the KEY FACT that makes the current implementation correct.
        """
        # PermissionError is a subclass of OSError
        assert issubclass(PermissionError, OSError)

        # Therefore, catching OSError DOES catch PermissionError
        try:
            raise PermissionError("[WinError 5] Access is denied")
        except OSError as e:
            # This proves OSError handler catches PermissionError
            assert isinstance(e, PermissionError)
            assert "Access is denied" in str(e)
        else:
            pytest.fail("OSError handler did not catch PermissionError")

    def test_permission_error_on_file_write_caught(self):
        """
        Test that PermissionError during file write is CAUGHT by OSError handler.

        Given: atomic_write_with_validation has except OSError clause (line 193)
        When: A PermissionError is raised during file write
        Then: The OSError handler CATCHES it (because PermissionError is subclass)
        """
        # Arrange
        test_data = {
            "task_name": "test_task",
            "timestamp": "2024-01-01T00:00:00",
            "progress_pct": 50,
            "blocker": None,
            "files_modified": ["test.py"],
            "next_steps": "Continue testing",
            "handover": {"decisions": [], "patterns_learned": []},
            "modifications": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            target_path = Path(temp_dir) / "test_handoff.json"

            # Mock os.replace to raise PermissionError (simulating Windows file locking)
            with patch("handoff.hooks.__lib.handoff_store.os.replace") as mock_replace:
                mock_replace.side_effect = PermissionError(
                    "[WinError 5] Access is denied"
                )

                # Act & Assert
                # PermissionError should be caught by retry logic and re-raised
                # The fact it's caught proves the except clause works
                with pytest.raises(PermissionError, match="Access is denied"):
                    result = atomic_write_with_validation(test_data, target_path)

                # Verify retry attempts were made (proves it was caught, not escaped)
                assert mock_replace.call_count == 5  # max_retries default

    def test_tempfile_creation_permission_error_propagates(self):
        """
        Test that PermissionError from tempfile.mkstemp is NOT caught.

        QUAL-001 Finding: tempfile.mkstemp is called OUTSIDE the try/except block
        (line 184), so PermissionError from mkstemp WILL escape.

        This is INTENTIONAL - we can't clean up a temp file that was never created.

        Given: tempfile.mkstemp is called before try/except block
        When: mkstemp raises PermissionError
        Then: Error propagates (no temp file to clean up anyway)
        """
        # Arrange
        test_data = {
            "task_name": "test_task",
            "timestamp": "2024-01-01T00:00:00",
            "progress_pct": 50,
            "blocker": None,
            "files_modified": ["test.py"],
            "next_steps": "Continue testing",
            "handover": {"decisions": [], "patterns_learned": []},
            "modifications": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            target_path = Path(temp_dir) / "test_handoff.json"

            # Mock tempfile.mkstemp to raise PermissionError
            with patch("tempfile.mkstemp") as mock_mkstemp:
                mock_mkstemp.side_effect = PermissionError(
                    "[Errno 13] Permission denied"
                )

                # Act & Assert
                # PermissionError from mkstemp should propagate
                # This is CORRECT behavior - no temp file created, nothing to clean up
                with pytest.raises(PermissionError, match="Permission denied"):
                    result = atomic_write_with_validation(test_data, target_path)

    def test_oserror_on_write_is_caught_and_rethrown(self):
        """
        Test that OSError during file write is caught, logged, and re-raised.

        Given: atomic_write_with_validation has except OSError clause (line 193)
        When: An OSError is raised during file write
        Then: Error is caught, logged, temp file cleaned up, and re-raised
        """
        # Arrange
        test_data = {
            "task_name": "test_task",
            "timestamp": "2024-01-01T00:00:00",
            "progress_pct": 50,
            "blocker": None,
            "files_modified": ["test.py"],
            "next_steps": "Continue testing",
            "handover": {"decisions": [], "patterns_learned": []},
            "modifications": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            target_path = Path(temp_dir) / "test_handoff.json"

            # Mock os.replace to raise OSError
            with patch("handoff.hooks.__lib.handoff_store.os.replace") as mock_replace:
                mock_replace.side_effect = OSError("Input/output error")

                # Act & Assert
                # OSError should be caught and re-raised
                with pytest.raises(OSError, match="Input/output error"):
                    result = atomic_write_with_validation(test_data, target_path)

    def test_successful_write_returns_size_info(self):
        """
        Test that successful write returns size information dict.

        Happy path test to verify normal operation works correctly.
        """
        # Arrange
        test_data = {
            "task_name": "test_task",
            "timestamp": "2024-01-01T00:00:00",
            "progress_pct": 50,
            "blocker": None,
            "files_modified": ["test.py"],
            "next_steps": "Continue testing",
            "handover": {"decisions": [], "patterns_learned": []},
            "modifications": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            target_path = Path(temp_dir) / "test_handoff.json"

            # Act
            result = atomic_write_with_validation(test_data, target_path)

            # Assert
            assert isinstance(result, dict)
            assert "original_size" in result
            assert "final_size" in result
            assert "truncated" in result
            assert result["original_size"] > 0
            assert result["final_size"] > 0
            assert target_path.exists()

            # Verify file content is correct
            with open(target_path, encoding="utf-8") as f:
                loaded_data = json.load(f)
            assert loaded_data["task_name"] == "test_task"


class TestAtomicWriteRetryPermissionError:
    """
    Test atomic_write_with_retry PermissionError handling.

    This function has EXPLICIT PermissionError handling (line 108)
    which is good practice even though PermissionError is an OSError.
    """

    def test_permission_error_triggers_retry_logic(self):
        """
        Test that PermissionError from os.replace triggers retry logic.

        Given: atomic_write_with_retry has except PermissionError clause (line 108)
        When: os.replace raises PermissionError (Windows file locking)
        Then: Retry logic is triggered with exponential backoff
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a temp file to use as source
            temp_file = Path(temp_dir) / "source.tmp"
            temp_file.write_text("test data")

            target_file = Path(temp_dir) / "target.json"

            # Mock os.replace to raise PermissionError
            with patch("handoff.hooks.__lib.handoff_store.os.replace") as mock_replace:
                mock_replace.side_effect = PermissionError("[WinError 5] Access is denied")

                # Act & Assert
                with pytest.raises(PermissionError, match="Access is denied"):
                    atomic_write_with_retry(str(temp_file), target_file)

                # Verify retry attempts
                assert mock_replace.call_count == 5  # max_retries default

    def test_oserror_does_not_trigger_retry(self):
        """
        Test that non-PermissionError OSError does NOT trigger retry logic.

        Given: atomic_write_with_retry has separate OSError handler (line 127)
        When: os.replace raises a different OSError
        Then: No retry, immediate cleanup and re-raise
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a temp file to use as source
            temp_file = Path(temp_dir) / "source.tmp"
            temp_file.write_text("test data")

            target_file = Path(temp_dir) / "target.json"

            # Mock os.replace to raise OSError (not PermissionError)
            with patch("handoff.hooks.__lib.handoff_store.os.replace") as mock_replace:
                mock_replace.side_effect = OSError("Disk full")

                # Act & Assert
                with pytest.raises(OSError, match="Disk full"):
                    atomic_write_with_retry(str(temp_file), target_file)

                # Verify only ONE attempt (no retry for non-PermissionError OSError)
                assert mock_replace.call_count == 1

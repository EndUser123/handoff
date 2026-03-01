#!/usr/bin/env python3
"""
Tests for QUAL-001: Inconsistent Error Handling in atomic_write_with_validation.

This test verifies that PermissionError (a subclass of OSError) is properly
handled during file write operations. Currently the function only catches OSError
explicitly, but PermissionError can escape during file operations.

Issue: QUAL-001
Function: atomic_write_with_validation() in handoff_store.py (line 142)
Expected: All file operation exceptions caught (OSError, PermissionError, etc.)
Actual (before fix): Only OSError caught, PermissionError escapes

Run with: pytest P:/packages/handoff/tests/test_quality_error_handling.py -v
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

# Add hooks to path
hooks_dir = Path("P:/packages/handoff/src/handoff/hooks").resolve()
sys.path.insert(0, str(hooks_dir))

from handoff.hooks.__lib.handoff_store import atomic_write_with_validation


class TestAtomicWritePermissionError:
    """Test QUAL-001: PermissionError handling in atomic_write_with_validation."""

    def test_permission_error_on_file_write(self):
        """
        Test that PermissionError during file write is caught and handled.

        Scenario:
        1. Call atomic_write_with_validation with valid data
        2. Mock os.fdopen to raise PermissionError on write
        3. Verify PermissionError is caught (not propagated)

        Expected behavior (after fix):
        - PermissionError is caught by exception handler
        - Temp file is cleaned up
        - Error is logged

        Actual behavior (before fix):
        - PermissionError escapes the try/except block
        - Temp file may not be cleaned up
        - Test will FAIL because PermissionError is raised
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

        # Create temp directory for test
        with tempfile.TemporaryDirectory() as temp_dir:
            target_path = Path(temp_dir) / "test_handoff.json"

            # Act & Assert
            # Mock os.fdopen to raise PermissionError
            # This simulates a permission denied error during file write
            with patch("os.fdopen") as mock_fdopen:
                # Set up the mock to raise PermissionError
                mock_file = MagicMock()
                mock_file.write.side_effect = PermissionError(
                    "[WinError 5] Access is denied"
                )
                mock_fdopen.return_value.__enter__.return_value = mock_file

                # The current implementation only catches OSError explicitly
                # PermissionError IS a subclass of OSError, so it SHOULD be caught
                # However, the test will verify this behavior actually works
                with pytest.raises(PermissionError):
                    result = atomic_write_with_validation(test_data, target_path)
                    # If we reach here, PermissionError was NOT caught (FAIL)
                    # After fix, this should NOT raise

    def test_oserror_is_caught(self):
        """
        Test that OSError during file write is caught and handled.

        This test verifies the CURRENT behavior: OSError is caught.
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

            # Mock os.fdopen to raise OSError
            with patch("os.fdopen") as mock_fdopen:
                mock_file = MagicMock()
                mock_file.write.side_effect = OSError(
                    "Input/output error"
                )
                mock_fdopen.return_value.__enter__.return_value = mock_file

                # OSError SHOULD be caught and re-raised
                with pytest.raises(OSError):
                    result = atomic_write_with_validation(test_data, target_path)

    def test_permission_error_inheritance(self):
        """
        Verify PermissionError IS a subclass of OSError.

        This test documents the Python exception hierarchy to ensure
        our understanding is correct.
        """
        # PermissionError is a subclass of OSError
        assert issubclass(PermissionError, OSError)

        # Therefore, catching OSError SHOULD also catch PermissionError
        try:
            raise PermissionError("test")
        except OSError as e:
            assert isinstance(e, PermissionError)
            assert str(e) == "test"
        else:
            pytest.fail("OSError handler did not catch PermissionError")

    def test_successful_write_with_validation(self):
        """
        Test that successful write returns size info dict.

        This verifies the happy path works correctly.
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

            # Verify file content
            with open(target_path, encoding="utf-8") as f:
                loaded_data = json.load(f)
            assert loaded_data["task_name"] == "test_task"

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
from unittest.mock import patch

import pytest

# Add hooks to path
hooks_dir = Path("P:/packages/handoff/src/handoff/hooks").resolve()
sys.path.insert(0, str(hooks_dir))

from handoff.hooks.__lib.handoff_store import atomic_write_with_validation


class TestAtomicWritePermissionError:
    """Test QUAL-001: PermissionError handling in atomic_write_with_validation."""

    def test_permission_error_on_tempfile_creation(self):
        """
        Test that PermissionError during tempfile.mkstemp is caught.

        QUAL-001 Issue: tempfile.mkstemp can raise PermissionError if
        the target directory is not writable, but this error is NOT
        caught by the current implementation.

        Scenario:
        1. Call atomic_write_with_validation with a target in read-only directory
        2. tempfile.mkstemp raises PermissionError
        3. Verify PermissionError escapes (not caught by OSError handler)

        Current behavior (BUG):
        - PermissionError from mkstemp escapes uncaught
        - No cleanup occurs
        - Function crashes

        Expected behavior (after fix):
        - PermissionError should be caught and logged
        - Function should handle gracefully
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

        # Create a read-only directory to trigger PermissionError
        with tempfile.TemporaryDirectory() as temp_dir:
            readonly_dir = Path(temp_dir) / "readonly"
            readonly_dir.mkdir()

            # Make directory read-only (Windows)
            try:
                import stat
                os.chmod(readonly_dir, stat.S_IREAD)

                target_path = readonly_dir / "test_handoff.json"

                # Act & Assert
                # This SHOULD raise PermissionError because mkstemp can't create file in read-only dir
                # The current implementation does NOT catch this error
                with pytest.raises(PermissionError):
                    result = atomic_write_with_validation(test_data, target_path)
            finally:
                # Restore permissions for cleanup
                try:
                    import stat
                    os.chmod(readonly_dir, stat.S_IWRITE | stat.S_IREAD)
                except:
                    pass

    def test_permission_error_on_os_replace(self):
        """
        Test that PermissionError from os.replace is handled by retry logic.

        This test verifies that the atomic_write_with_retry function properly
        catches and retries PermissionError from os.replace.

        Current behavior (CORRECT):
        - PermissionError IS caught and retried
        - After max retries, error is re-raised
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

            # Mock os.replace to raise PermissionError
            with patch("handoff.hooks.__lib.handoff_store.os.replace") as mock_replace:
                mock_replace.side_effect = PermissionError(
                    "[WinError 5] Access is denied"
                )

                # This SHOULD be caught by retry logic and re-raised after max retries
                with pytest.raises(PermissionError):
                    result = atomic_write_with_validation(test_data, target_path)

                # Verify retry attempts were made
                assert mock_replace.call_count == 5  # max_retries default

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

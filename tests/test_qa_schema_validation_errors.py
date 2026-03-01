#!/usr/bin/env python3
"""
Test for QA-001: Silent Failures in Schema Validation.

This test verifies that schema validation failures in the SessionStart
handoff restoration hook are logged and reported to users, not silent.

Issue: When handoff data fails schema validation (missing required fields),
the hook currently returns 0 silently without logging or informing the user.
This makes debugging difficult when handoff data is corrupted.

Expected behavior:
- Schema validation failures should be logged at WARNING level
- User-visible error message should be output
- Return 0 to allow session start (don't block)

Run with: pytest P:/packages/handoff/tests/test_qa_schema_validation_errors.py -v
"""

import json
import logging
from pathlib import Path
from unittest.mock import patch


class TestQASchemaValidationErrors:
    """Tests for QA-001: Schema validation error reporting."""

    def test_schema_validation_missing_field_logs_warning(self, caplog):
        """
        Test that schema validation failures are logged.

        Given: Handoff data with missing required field 'task_name'
        When: Schema validation runs
        Then: A WARNING should be logged (not silent)
        """
        # Arrange
        from handoff.hooks.SessionStart_handoff_restore import _validate_handoff_schema

        invalid_handoff = {
            "saved_at": "2026-03-01T10:00:00Z",
            # Missing: task_name (required field)
        }

        # Act
        with caplog.at_level(logging.WARNING):
            is_valid, error = _validate_handoff_schema(invalid_handoff)

        # Assert
        assert is_valid is False, "Validation should fail for missing required field"
        assert error is not None, "Error message should be provided"
        assert "task_name" in error, "Error should mention missing field"

        # CRITICAL ASSERTION: This will FAIL until bug is fixed
        # Currently the code returns 0 silently without logging
        assert any(
            "Missing required field" in record.message
            for record in caplog.records
        ), "Schema validation failure should be logged at WARNING level"

    def test_schema_validation_invalid_timestamp_logs_warning(self, caplog):
        """
        Test that invalid timestamp format is logged.

        Given: Handoff data with invalid timestamp format
        When: Schema validation runs
        Then: A WARNING should be logged about invalid timestamp
        """
        # Arrange
        from handoff.hooks.SessionStart_handoff_restore import _validate_handoff_schema

        invalid_handoff = {
            "task_name": "Test task",
            "saved_at": "not-a-valid-timestamp",  # Invalid ISO format
        }

        # Act
        with caplog.at_level(logging.WARNING):
            is_valid, error = _validate_handoff_schema(invalid_handoff)

        # Assert
        assert is_valid is False, "Validation should fail for invalid timestamp"
        assert error is not None, "Error message should be provided"
        assert "timestamp" in error.lower(), "Error should mention timestamp issue"

        # CRITICAL ASSERTION: This will FAIL until bug is fixed
        # Currently the code logs this but then returns silently
        assert any(
            "Invalid saved_at timestamp" in record.message
            for record in caplog.records
        ), "Invalid timestamp should be logged at WARNING level"

    def test_main_hook_returns_logs_on_schema_failure(self, caplog, tmp_path):
        """
        Test that main() function logs schema validation failures.

        Given: active_session task with invalid handoff data (missing field)
        When: The hook main() function runs
        Then: WARNING should be logged and user should be informed
        """
        # Arrange
        import sys

        # Add hooks directory to path
        hooks_dir = Path("P:/packages/handoff/src/handoff/hooks").resolve()
        if str(hooks_dir) not in sys.path:
            sys.path.insert(0, str(hooks_dir))


        # Create task tracker directory in temp location
        task_tracker_base = tmp_path / ".claude" / "state" / "task_tracker"
        task_tracker_base.mkdir(parents=True, exist_ok=True)

        terminal_id = "test_terminal_schema_fail"
        task_file = task_tracker_base / f"{terminal_id}_tasks.json"

        # Create handoff data with missing required field
        invalid_handoff = {
            "saved_at": "2026-03-01T10:00:00Z",
            # Missing: task_name (required field)
        }

        task_data = {
            "terminal_id": terminal_id,
            "tasks": {
                "active_session": {
                    "id": "active_session",
                    "subject": "Handoff with schema error",
                    "status": "pending",
                    "metadata": {
                        "handoff": invalid_handoff
                    }
                }
            }
        }

        with open(task_file, 'w') as f:
            json.dump(task_data, f)

        # Mock PROJECT_ROOT to point to temp directory
        with patch('SessionStart_handoff_restore.PROJECT_ROOT', tmp_path):
            # Import after patching
            from SessionStart_handoff_restore import main

            # Act
            with caplog.at_level(logging.WARNING):
                return_code = main()

            # Assert
            assert return_code == 0, "Should return 0 to allow session start"

            # CRITICAL ASSERTION: This will FAIL until bug is fixed
            # Currently the code returns 0 silently at line 752 without logging
            assert any(
                "Schema validation" in record.message or
                "Missing required field" in record.message or
                "handoff" in record.message.lower()
                for record in caplog.records
            ), "Schema validation failure should be logged"

            # CRITICAL ASSERTION: This will FAIL until bug is fixed
            # User should be informed about the validation failure
            # Currently nothing is printed to stdout
            assert any(
                "Schema validation" in record.message or
                "Missing required field" in record.message
                for record in caplog.records if record.levelno >= logging.WARNING
            ), "User should be informed about schema validation failure"

    def test_schema_validation_missing_saved_at_field(self, caplog):
        """
        Test that missing saved_at field is logged.

        Given: Handoff data with missing 'saved_at' field
        When: Schema validation runs
        Then: A WARNING should be logged
        """
        # Arrange
        from handoff.hooks.SessionStart_handoff_restore import _validate_handoff_schema

        invalid_handoff = {
            "task_name": "Test task",
            # Missing: saved_at (required field)
        }

        # Act
        with caplog.at_level(logging.WARNING):
            is_valid, error = _validate_handoff_schema(invalid_handoff)

        # Assert
        assert is_valid is False, "Validation should fail for missing saved_at"
        assert error is not None, "Error message should be provided"
        assert "saved_at" in error, "Error should mention saved_at field"

        # CRITICAL ASSERTION: This will FAIL until bug is fixed
        assert any(
            "Missing required field" in record.message
            for record in caplog.records
        ), "Missing required field should be logged at WARNING level"

    def test_valid_handoff_passes_validation(self):
        """
        Test that valid handoff data passes validation.

        Given: Handoff data with all required fields and valid timestamp
        When: Schema validation runs
        Then: Validation should succeed
        """
        # Arrange
        from handoff.hooks.SessionStart_handoff_restore import _validate_handoff_schema

        valid_handoff = {
            "task_name": "Test task",
            "saved_at": "2026-03-01T10:00:00Z",
        }

        # Act
        is_valid, error = _validate_handoff_schema(valid_handoff)

        # Assert
        assert is_valid is True, "Valid handoff should pass validation"
        assert error is None, "Error should be None for valid data"

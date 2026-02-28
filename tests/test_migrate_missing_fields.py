#!/usr/bin/env python3
"""Tests for migrate_old_handoff_to_checkpoint missing field handling.

These tests verify that migrating old handoff data to checkpoint format
handles missing optional fields with sensible defaults.

Run with: pytest tests/test_migrate_missing_fields.py -v
"""

from __future__ import annotations

from pathlib import Path

# Add handoff package to path
HANDOFF_PACKAGE = Path(__file__).parent.parent / "src"
if str(HANDOFF_PACKAGE) not in globals():
    import sys
    sys.path.insert(0, str(HANDOFF_PACKAGE))


class TestMigrateOldHandoffToCheckpointMissingFields:
    """Tests for missing field handling in migrate_old_handoff_to_checkpoint."""

    def test_missing_pending_operations_defaults_to_empty_list(self):
        """Test that missing pending_operations defaults to empty list.

        Given: Old handoff data without pending_operations field
        When: migrate_old_handoff_to_checkpoint is called
        Then: Result should have pending_operations as empty list
        """
        # Arrange
        from handoff.migrate import migrate_old_handoff_to_checkpoint

        old_handoff = {
            "task_name": "test_task",
            "progress_percent": 50,
            "saved_at": "2025-01-15T10:30:00Z"
            # Note: pending_operations is missing
        }

        # Act
        result = migrate_old_handoff_to_checkpoint(old_handoff)

        # Assert
        assert "pending_operations" in result
        assert result["pending_operations"] == []

    def test_missing_timestamp_defaults_to_saved_at(self):
        """Test that missing timestamp defaults to saved_at field.

        Given: Old handoff data without timestamp field
        When: migrate_old_handoff_to_checkpoint is called
        Then: Result should use saved_at as timestamp fallback
        """
        # Arrange
        from handoff.migrate import migrate_old_handoff_to_checkpoint

        old_handoff = {
            "task_name": "test_task",
            "progress_percent": 50,
            "saved_at": "2025-01-15T10:30:00Z"
            # Note: timestamp is missing
        }

        # Act
        result = migrate_old_handoff_to_checkpoint(old_handoff)

        # Assert
        assert "timestamp" in result
        assert result["timestamp"] == "2025-01-15T10:30:00Z"

    def test_missing_timestamp_and_saved_at_defaults_to_current_time(self):
        """Test that missing timestamp and saved_at defaults to current time.

        Given: Old handoff data without timestamp or saved_at fields
        When: migrate_old_handoff_to_checkpoint is called
        Then: Result should have a valid ISO timestamp
        """
        # Arrange
        from handoff.migrate import migrate_old_handoff_to_checkpoint

        old_handoff = {
            "task_name": "test_task",
            "progress_percent": 50
            # Note: Both timestamp and saved_at are missing
        }

        # Act
        result = migrate_old_handoff_to_checkpoint(old_handoff)

        # Assert
        assert "timestamp" in result
        assert result["timestamp"] is not None
        # Should be a valid ISO 8601 timestamp
        assert "T" in result["timestamp"] or result["timestamp"].count("-") >= 2

    def test_missing_metadata_defaults_to_empty_dict(self):
        """Test that missing metadata defaults to empty dict.

        Given: Old handoff data without metadata field
        When: migrate_old_handoff_to_checkpoint is called
        Then: Result should have metadata as empty dict
        """
        # Arrange
        from handoff.migrate import migrate_old_handoff_to_checkpoint

        old_handoff = {
            "task_name": "test_task",
            "progress_percent": 50,
            "saved_at": "2025-01-15T10:30:00Z"
            # Note: metadata is missing
        }

        # Act
        result = migrate_old_handoff_to_checkpoint(old_handoff)

        # Assert
        assert "metadata" in result
        assert result["metadata"] == {}

    def test_all_optional_fields_missing(self):
        """Test migration when all optional fields are missing.

        Given: Old handoff data with only required fields
        When: migrate_old_handoff_to_checkpoint is called
        Then: Result should have sensible defaults for all missing fields
        """
        # Arrange
        from handoff.migrate import migrate_old_handoff_to_checkpoint

        old_handoff = {
            "task_name": "minimal_task"
            # All optional fields missing: pending_operations, timestamp, metadata
        }

        # Act
        result = migrate_old_handoff_to_checkpoint(old_handoff)

        # Assert
        assert "pending_operations" in result
        assert result["pending_operations"] == []

        assert "timestamp" in result
        assert result["timestamp"] is not None

        assert "metadata" in result
        assert result["metadata"] == {}

        # Core fields should be preserved
        assert result["task_name"] == "minimal_task"

    def test_partial_metadata_preserved(self):
        """Test that partial metadata is preserved during migration.

        Given: Old handoff data with partial metadata
        When: migrate_old_handoff_to_checkpoint is called
        Then: Result should preserve existing metadata and add defaults for missing
        """
        # Arrange
        from handoff.migrate import migrate_old_handoff_to_checkpoint

        old_handoff = {
            "task_name": "test_task",
            "metadata": {
                "git_branch": "feature-branch"
                # Other metadata fields missing
            }
        }

        # Act
        result = migrate_old_handoff_to_checkpoint(old_handoff)

        # Assert
        assert "metadata" in result
        assert result["metadata"]["git_branch"] == "feature-branch"
        # Missing fields should have defaults
        assert "pending_operations" in result

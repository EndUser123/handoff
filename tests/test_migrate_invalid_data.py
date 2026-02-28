#!/usr/bin/env python3
"""Invalid data handling tests for migrate.py functions.

These tests verify that migration functions handle invalid data gracefully
and raise appropriate errors.

Test Categories:
1. None input handling
2. Empty dict handling
3. Dict missing required fields
4. Dict with wrong types

Run with: pytest P:/packages/handoff/tests/test_migrate_invalid_data.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Add handoff package to path
HANDOFF_PACKAGE = Path(__file__).parent.parent / "src"
if str(HANDOFF_PACKAGE) not in globals():
    import sys
    sys.path.insert(0, str(HANDOFF_PACKAGE))

from handoff.migrate import migrate_checkpoint_chain_fields


class TestMigrateCheckpointChainFieldsInvalidData:
    """Tests for migrate_checkpoint_chain_fields with invalid data."""

    def test_none_input_raises_type_error(self):
        """Test that None input raises TypeError.

        Given: None is passed as handoff_data
        When: migrate_checkpoint_chain_fields() is called
        Then: TypeError is raised
        """
        # Arrange & Act & Assert
        with pytest.raises(TypeError, match="expected dict or None"):
            migrate_checkpoint_chain_fields(None)

    def test_empty_dict_returns_valid_checkpoint(self):
        """Test that empty dict returns valid checkpoint with generated fields.

        Given: Empty dict is passed as handoff_data
        When: migrate_checkpoint_chain_fields() is called
        Then: Returns dict with checkpoint_id, parent_checkpoint_id, and chain_id
        """
        # Arrange
        empty_data = {}

        # Act
        result = migrate_checkpoint_chain_fields(empty_data)

        # Assert
        assert isinstance(result, dict)
        assert "checkpoint_id" in result
        assert "parent_checkpoint_id" in result
        assert "chain_id" in result
        assert result["parent_checkpoint_id"] is None
        assert isinstance(result["checkpoint_id"], str)
        assert isinstance(result["chain_id"], str)

    def test_dict_missing_all_required_fields_adds_them(self):
        """Test that dict missing required fields adds them.

        Given: Dict without checkpoint_id, parent_checkpoint_id, or chain_id
        When: migrate_checkpoint_chain_fields() is called
        Then: Adds all three fields with appropriate values
        """
        # Arrange
        incomplete_data = {"task_name": "test_task"}

        # Act
        result = migrate_checkpoint_chain_fields(incomplete_data)

        # Assert
        assert "checkpoint_id" in result
        assert "parent_checkpoint_id" in result
        assert "chain_id" in result
        assert result["parent_checkpoint_id"] is None
        assert len(result["checkpoint_id"]) > 0
        assert len(result["chain_id"]) > 0

    def test_dict_with_wrong_types_for_fields_raises_type_error(self):
        """Test that dict with wrong types for checkpoint fields raises TypeError.

        Given: Dict with checkpoint_id as int instead of str
        When: migrate_checkpoint_chain_fields() is called
        Then: TypeError is raised
        """
        # Arrange
        invalid_type_data = {
            "checkpoint_id": 12345,  # Should be str
            "task_name": "test_task"
        }

        # Act & Assert
        # This should fail because existing checkpoint_id should be validated
        with pytest.raises(TypeError, match="checkpoint_id must be str"):
            migrate_checkpoint_chain_fields(invalid_type_data)

    def test_dict_with_parent_checkpoint_id_wrong_type_raises_type_error(self):
        """Test that dict with wrong type for parent_checkpoint_id raises TypeError.

        Given: Dict with parent_checkpoint_id as str instead of None/str
        When: migrate_checkpoint_chain_fields() is called
        Then: TypeError is raised if type is invalid
        """
        # Arrange
        invalid_type_data = {
            "parent_checkpoint_id": ["invalid"],  # Should be str or None
            "task_name": "test_task"
        }

        # Act & Assert
        with pytest.raises(TypeError, match="parent_checkpoint_id must be str or None"):
            migrate_checkpoint_chain_fields(invalid_type_data)

    def test_dict_with_chain_id_wrong_type_raises_type_error(self):
        """Test that dict with wrong type for chain_id raises TypeError.

        Given: Dict with chain_id as int instead of str
        When: migrate_checkpoint_chain_fields() is called
        Then: TypeError is raised
        """
        # Arrange
        invalid_type_data = {
            "chain_id": 999,  # Should be str
            "task_name": "test_task"
        }

        # Act & Assert
        with pytest.raises(TypeError, match="chain_id must be str"):
            migrate_checkpoint_chain_fields(invalid_type_data)

    def test_idempotent_preserves_existing_fields(self):
        """Test that migration is idempotent - preserves existing fields.

        Given: Dict with all checkpoint chain fields already present
        When: migrate_checkpoint_chain_fields() is called twice
        Then: Fields remain unchanged on second call
        """
        # Arrange
        existing_id = "existing-checkpoint-123"
        existing_parent = "parent-checkpoint-456"
        existing_chain = "chain-789"

        complete_data = {
            "checkpoint_id": existing_id,
            "parent_checkpoint_id": existing_parent,
            "chain_id": existing_chain,
            "task_name": "test_task"
        }

        # Act
        result = migrate_checkpoint_chain_fields(complete_data)

        # Assert
        assert result["checkpoint_id"] == existing_id
        assert result["parent_checkpoint_id"] == existing_parent
        assert result["chain_id"] == existing_chain

    def test_adds_transcript_fields_when_missing(self):
        """Test that transcript fields are added when missing.

        Given: Dict without transcript_offset and transcript_entry_count
        When: migrate_checkpoint_chain_fields() is called
        Then: Adds both fields with 0 as default value
        """
        # Arrange
        data_without_transcript = {
            "task_name": "test_task"
        }

        # Act
        result = migrate_checkpoint_chain_fields(data_without_transcript)

        # Assert
        assert "transcript_offset" in result
        assert "transcript_entry_count" in result
        assert result["transcript_offset"] == 0
        assert result["transcript_entry_count"] == 0

    def test_preserves_existing_transcript_fields(self):
        """Test that existing transcript fields are preserved.

        Given: Dict with transcript_offset and transcript_entry_count already set
        When: migrate_checkpoint_chain_fields() is called
        Then: Existing values are preserved
        """
        # Arrange
        data_with_transcript = {
            "task_name": "test_task",
            "transcript_offset": 1234,
            "transcript_entry_count": 56
        }

        # Act
        result = migrate_checkpoint_chain_fields(data_with_transcript)

        # Assert
        assert result["transcript_offset"] == 1234
        assert result["transcript_entry_count"] == 56

    def test_does_not_modify_original_dict(self):
        """Test that migration does not modify the original dict.

        Given: Original handoff data dict
        When: migrate_checkpoint_chain_fields() is called
        Then: Original dict remains unchanged
        """
        # Arrange
        original_data = {"task_name": "test_task", "custom_field": "value"}
        original_copy = original_data.copy()

        # Act
        result = migrate_checkpoint_chain_fields(original_data)

        # Assert
        assert original_data == original_copy
        assert "checkpoint_id" not in original_data
        assert "checkpoint_id" in result

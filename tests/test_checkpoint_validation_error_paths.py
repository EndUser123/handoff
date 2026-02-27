#!/usr/bin/env python3
"""Error path tests for HandoffCheckpoint validation.

These tests verify that checksum validation and schema validation
properly reject invalid inputs.

Test Categories:
1. Missing checksum field raises error
2. Invalid checksum format (not "sha256:" prefix) raises error
3. Invalid hex characters in checksum raises error
4. Wrong checksum length (not 64 hex chars) raises error
5. Malformed JSON raises error
6. Missing required fields raises error

Run with: pytest P:/packages/handoff/tests/test_checkpoint_validation_error_paths.py -v
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

# Add handoff package to path
HANDOFF_PACKAGE = Path(__file__).parent.parent / "src"
if str(HANDOFF_PACKAGE) not in globals():
    import sys
    sys.path.insert(0, str(HANDOFF_PACKAGE))

from handoff.models import HandoffCheckpoint


class TestChecksumValidationErrorPaths:
    """Tests for checksum validation error paths."""

    @pytest.fixture
    def valid_checkpoint_data(self):
        """Provide valid checkpoint data for testing."""
        checkpoint_id = str(uuid4())
        chain_id = str(uuid4())
        return {
            "checkpoint_id": checkpoint_id,
            "parent_checkpoint_id": None,
            "chain_id": chain_id,
            "created_at": "2025-02-16T12:00:00Z",
            "transcript_offset": 0,
            "transcript_entry_count": 0,
            "task_name": "test task",
            "task_type": "informal",
            "progress_percent": 50,
            "blocker": None,
            "next_steps": "Complete the work",
            "git_branch": "main",
            "active_files": ["src/main.py"],
            "recent_tools": [],
            "transcript_path": "/transcript.json",
            "handover": None,
            "open_conversation_context": None,
            "visual_context": None,
            "resolved_issues": [],
            "modifications": [],
            "original_user_request": "test message",
            "first_user_request": "first message",
            "saved_at": "2025-02-16T12:00:00Z",
            "version": 1,
            "implementation_status": None,
            "pending_operations": [],
        }

    def test_missing_checksum_field_raises_error(self, valid_checkpoint_data):
        """Test that missing checksum field raises ValueError.

        Given: Valid checkpoint data without checksum field
        When: from_dict() is called
        Then: ValueError is raised with 'Missing required fields' message
        """
        # Arrange: Remove checksum from data (it's not in valid_checkpoint_data)
        data = valid_checkpoint_data.copy()

        # Act & Assert: Should raise ValueError for missing checksum
        with pytest.raises(ValueError, match="Missing required fields.*checksum"):
            HandoffCheckpoint.from_dict(data)

    def test_invalid_checksum_format_no_prefix_raises_error(self, valid_checkpoint_data):
        """Test that checksum without 'sha256:' prefix raises ValueError.

        Given: Valid checkpoint data with checksum missing 'sha256:' prefix
        When: from_dict() is called
        Then: ValueError is raised about invalid checksum format
        """
        # Arrange: Checksum without sha256: prefix
        data = valid_checkpoint_data.copy()
        data["checksum"] = "abc123def456..."

        # Act & Assert: Should raise ValueError for invalid format
        with pytest.raises(ValueError, match="Invalid checksum format.*must start with 'sha256:'"):
            HandoffCheckpoint.from_dict(data)

    def test_invalid_checksum_format_wrong_prefix_raises_error(self, valid_checkpoint_data):
        """Test that checksum with wrong prefix raises ValueError.

        Given: Valid checkpoint data with checksum using 'md5:' prefix instead of 'sha256:'
        When: from_dict() is called
        Then: ValueError is raised about invalid checksum format
        """
        # Arrange: Checksum with wrong prefix
        data = valid_checkpoint_data.copy()
        data["checksum"] = "md5:abc123def456"

        # Act & Assert: Should raise ValueError for invalid format
        with pytest.raises(ValueError, match="Invalid checksum format.*must start with 'sha256:'"):
            HandoffCheckpoint.from_dict(data)

    def test_invalid_checksum_hex_characters_raises_error(self, valid_checkpoint_data):
        """Test that checksum with invalid hex characters raises ValueError.

        Given: Valid checkpoint data with checksum containing non-hex characters
        When: from_dict() is called
        Then: ValueError is raised about invalid hex characters
        """
        # Arrange: Checksum with invalid hex characters (contains 'x', 'y', 'z')
        data = valid_checkpoint_data.copy()
        data["checksum"] = "sha256:abc123xyz789..."

        # Act & Assert: Should raise ValueError for invalid hex characters
        with pytest.raises(ValueError, match="Invalid checksum.*must contain only hexadecimal characters"):
            HandoffCheckpoint.from_dict(data)

    def test_invalid_checksum_too_short_raises_error(self, valid_checkpoint_data):
        """Test that checksum with less than 64 hex chars raises ValueError.

        Given: Valid checkpoint data with checksum having only 32 hex chars
        When: from_dict() is called
        Then: ValueError is raised about incorrect checksum length
        """
        # Arrange: Checksum with only 32 hex characters (should be 64)
        data = valid_checkpoint_data.copy()
        data["checksum"] = "sha256:" + "a" * 32

        # Act & Assert: Should raise ValueError for incorrect length
        with pytest.raises(ValueError, match="Invalid checksum.*must be 64 hexadecimal characters"):
            HandoffCheckpoint.from_dict(data)

    def test_invalid_checksum_too_long_raises_error(self, valid_checkpoint_data):
        """Test that checksum with more than 64 hex chars raises ValueError.

        Given: Valid checkpoint data with checksum having 128 hex chars
        When: from_dict() is called
        Then: ValueError is raised about incorrect checksum length
        """
        # Arrange: Checksum with 128 hex characters (should be 64)
        data = valid_checkpoint_data.copy()
        data["checksum"] = "sha256:" + "a" * 128

        # Act & Assert: Should raise ValueError for incorrect length
        with pytest.raises(ValueError, match="Invalid checksum.*must be 64 hexadecimal characters"):
            HandoffCheckpoint.from_dict(data)

    def test_valid_checksum_format_accepted(self, valid_checkpoint_data):
        """Test that valid checksum format is accepted.

        Given: Valid checkpoint data with properly formatted checksum
        When: from_dict() is called
        Then: HandoffCheckpoint is created successfully

        This test documents the valid format: 'sha256:' + 64 hex characters
        """
        # Arrange: Valid checksum format
        data = valid_checkpoint_data.copy()
        data["checksum"] = "sha256:" + "a" * 64

        # Act: Should succeed
        checkpoint = HandoffCheckpoint.from_dict(data)

        # Assert: Checkpoint created with correct checksum
        assert checkpoint.checksum == "sha256:" + "a" * 64


class TestSchemaValidationErrorPaths:
    """Tests for schema validation error paths (missing required fields)."""

    def test_missing_multiple_required_fields_raises_error(self):
        """Test that missing multiple required fields raises ValueError.

        Given: Checkpoint data missing several required fields
        When: from_dict() is called
        Then: ValueError is raised listing all missing fields
        """
        # Arrange: Data missing multiple required fields
        data = {
            "task_name": "test",
            # Missing: checkpoint_id, chain_id, created_at, task_type,
            #         progress_percent, next_steps, active_files,
            #         recent_tools, saved_at, version, checksum
        }

        # Act & Assert: Should raise ValueError listing missing fields
        with pytest.raises(ValueError, match="Missing required fields"):
            HandoffCheckpoint.from_dict(data)

    def test_missing_checkpoint_id_raises_error(self):
        """Test that missing checkpoint_id field raises ValueError.

        Given: Valid checkpoint data except checkpoint_id is missing
        When: from_dict() is called
        Then: ValueError is raised about missing checkpoint_id
        """
        # Arrange: Data missing checkpoint_id
        data = {
            "chain_id": str(uuid4()),
            "created_at": "2025-02-16T12:00:00Z",
            "task_name": "test",
            "task_type": "informal",
            "progress_percent": 50,
            "next_steps": "Continue",
            "active_files": [],
            "recent_tools": [],
            "saved_at": "2025-02-16T12:00:00Z",
            "version": 1,
            "checksum": "sha256:" + "a" * 64
        }

        # Act & Assert: Should raise ValueError
        with pytest.raises(ValueError, match="Missing required fields.*checkpoint_id"):
            HandoffCheckpoint.from_dict(data)

    def test_missing_chain_id_raises_error(self):
        """Test that missing chain_id field raises ValueError.

        Given: Valid checkpoint data except chain_id is missing
        When: from_dict() is called
        Then: ValueError is raised about missing chain_id
        """
        # Arrange: Data missing chain_id
        checkpoint_id = str(uuid4())
        data = {
            "checkpoint_id": checkpoint_id,
            "created_at": "2025-02-16T12:00:00Z",
            "task_name": "test",
            "task_type": "informal",
            "progress_percent": 50,
            "next_steps": "Continue",
            "active_files": [],
            "recent_tools": [],
            "saved_at": "2025-02-16T12:00:00Z",
            "version": 1,
            "checksum": "sha256:" + "a" * 64
        }

        # Act & Assert: Should raise ValueError
        with pytest.raises(ValueError, match="Missing required fields.*chain_id"):
            HandoffCheckpoint.from_dict(data)

    def test_missing_created_at_raises_error(self):
        """Test that missing created_at field raises ValueError.

        Given: Valid checkpoint data except created_at is missing
        When: from_dict() is called
        Then: ValueError is raised about missing created_at
        """
        # Arrange: Data missing created_at
        checkpoint_id = str(uuid4())
        chain_id = str(uuid4())
        data = {
            "checkpoint_id": checkpoint_id,
            "chain_id": chain_id,
            "task_name": "test",
            "task_type": "informal",
            "progress_percent": 50,
            "next_steps": "Continue",
            "active_files": [],
            "recent_tools": [],
            "saved_at": "2025-02-16T12:00:00Z",
            "version": 1,
            "checksum": "sha256:" + "a" * 64
        }

        # Act & Assert: Should raise ValueError
        with pytest.raises(ValueError, match="Missing required fields.*created_at"):
            HandoffCheckpoint.from_dict(data)

    def test_missing_saved_at_raises_error(self):
        """Test that missing saved_at field raises ValueError.

        Given: Valid checkpoint data except saved_at is missing
        When: from_dict() is called
        Then: ValueError is raised about missing saved_at
        """
        # Arrange: Data missing saved_at
        checkpoint_id = str(uuid4())
        chain_id = str(uuid4())
        data = {
            "checkpoint_id": checkpoint_id,
            "chain_id": chain_id,
            "created_at": "2025-02-16T12:00:00Z",
            "task_name": "test",
            "task_type": "informal",
            "progress_percent": 50,
            "next_steps": "Continue",
            "active_files": [],
            "recent_tools": [],
            "version": 1,
            "checksum": "sha256:" + "a" * 64
        }

        # Act & Assert: Should raise ValueError
        with pytest.raises(ValueError, match="Missing required fields.*saved_at"):
            HandoffCheckpoint.from_dict(data)

    def test_missing_version_raises_error(self):
        """Test that missing version field raises ValueError.

        Given: Valid checkpoint data except version is missing
        When: from_dict() is called
        Then: ValueError is raised about missing version
        """
        # Arrange: Data missing version
        checkpoint_id = str(uuid4())
        chain_id = str(uuid4())
        data = {
            "checkpoint_id": checkpoint_id,
            "chain_id": chain_id,
            "created_at": "2025-02-16T12:00:00Z",
            "task_name": "test",
            "task_type": "informal",
            "progress_percent": 50,
            "next_steps": "Continue",
            "active_files": [],
            "recent_tools": [],
            "saved_at": "2025-02-16T12:00:00Z",
            "checksum": "sha256:" + "a" * 64
        }

        # Act & Assert: Should raise ValueError
        with pytest.raises(ValueError, match="Missing required fields.*version"):
            HandoffCheckpoint.from_dict(data)

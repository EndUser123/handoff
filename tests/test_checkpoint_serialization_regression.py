#!/usr/bin/env python3
"""Regression tests for HandoffCheckpoint serialization/deserialization.

These tests verify that to_dict() and from_dict() correctly preserve all
HandoffCheckpoint fields during round-trip serialization.

Run with: pytest tests/test_checkpoint_serialization_regression.py -v
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

from handoff.models import HandoffCheckpoint, PendingOperation


class TestCheckpointSerializationToDict:
    """Tests for HandoffCheckpoint.to_dict() serialization."""

    def test_to_dict_serializes_all_core_fields(self):
        """
        Test that to_dict() serializes all required core fields.

        Given: A HandoffCheckpoint with all fields populated
        When: to_dict() is called
        Then: All core fields are present in the returned dict
        """
        checkpoint_id = str(uuid4())
        chain_id = str(uuid4())
        created_at = "2026-02-27T10:30:00Z"
        saved_at = "2026-02-27T10:30:00Z"

        checkpoint = HandoffCheckpoint(
            checkpoint_id=checkpoint_id,
            parent_checkpoint_id=None,
            chain_id=chain_id,
            created_at=created_at,
            transcript_offset=0,
            transcript_entry_count=5,
            task_name="Implement feature X",
            task_type="formal",
            progress_percent=50,
            blocker={"description": "Waiting for dependency"},
            next_steps="1. Write code\n2. Test",
            git_branch="feature-x",
            active_files=["src/main.py", "tests/test.py"],
            recent_tools=[{"name": "edit", "target": "src/main.py"}],
            transcript_path="/path/to/transcript.txt",
            handover={"decisions": ["Use pytest"]},
            open_conversation_context={"thread_id": "abc123"},
            visual_context={"description": "Dashboard visible"},
            resolved_issues=[{"id": "1", "description": "Bug fixed"}],
            modifications=[{"file": "src/main.py", "changes": 5}],
            original_user_request="Implement feature X",
            first_user_request="Implement feature X",
            saved_at=saved_at,
            version=1,
            implementation_status={"stage": "in_progress"},
            pending_operations=[
                PendingOperation(
                    type="edit",
                    target="src/main.py",
                    state="in_progress",
                    details={"line": 42}
                )
            ],
            checksum="abc123def456"
        )

        result = checkpoint.to_dict()

        # Verify all core fields are present
        assert result["checkpoint_id"] == checkpoint_id
        assert result["parent_checkpoint_id"] is None
        assert result["chain_id"] == chain_id
        assert result["created_at"] == created_at
        assert result["transcript_offset"] == 0
        assert result["transcript_entry_count"] == 5
        assert result["task_name"] == "Implement feature X"
        assert result["task_type"] == "formal"
        assert result["progress_percent"] == 50
        assert result["blocker"]["description"] == "Waiting for dependency"
        assert result["next_steps"] == "1. Write code\n2. Test"
        assert result["git_branch"] == "feature-x"
        assert result["active_files"] == ["src/main.py", "tests/test.py"]
        assert len(result["recent_tools"]) == 1
        assert result["transcript_path"] == "/path/to/transcript.txt"
        assert result["handover"]["decisions"] == ["Use pytest"]
        assert result["open_conversation_context"]["thread_id"] == "abc123"
        assert result["visual_context"]["description"] == "Dashboard visible"
        assert len(result["resolved_issues"]) == 1
        assert len(result["modifications"]) == 1
        assert result["original_user_request"] == "Implement feature X"
        assert result["first_user_request"] == "Implement feature X"
        assert result["saved_at"] == saved_at
        assert result["version"] == 1
        assert result["implementation_status"]["stage"] == "in_progress"
        assert result["checksum"] == "abc123def456"

    def test_to_dict_serializes_pending_operations(self):
        """
        Test that to_dict() correctly serializes PendingOperation objects.

        Given: A HandoffCheckpoint with multiple PendingOperation objects
        When: to_dict() is called
        Then: PendingOperation objects are converted to dicts correctly
        """
        checkpoint = HandoffCheckpoint(
            checkpoint_id=str(uuid4()),
            parent_checkpoint_id=None,
            chain_id=str(uuid4()),
            created_at="2026-02-27T10:30:00Z",
            transcript_offset=0,
            transcript_entry_count=0,
            task_name="Test task",
            task_type="informal",
            progress_percent=0,
            blocker=None,
            next_steps="Start work",
            git_branch=None,
            active_files=[],
            recent_tools=[],
            transcript_path=None,
            handover=None,
            open_conversation_context=None,
            visual_context=None,
            resolved_issues=[],
            modifications=[],
            original_user_request=None,
            first_user_request=None,
            saved_at="2026-02-27T10:30:00Z",
            version=1,
            implementation_status=None,
            pending_operations=[
                PendingOperation(
                    type="edit",
                    target="src/main.py",
                    state="in_progress",
                    details={"line": 42, "change": "add function"}
                ),
                PendingOperation(
                    type="test",
                    target="tests/test_main.py",
                    state="pending",
                    details={"test_name": "test_function"}
                ),
            ],
            checksum="checksum123"
        )

        result = checkpoint.to_dict()

        assert len(result["pending_operations"]) == 2
        assert result["pending_operations"][0]["type"] == "edit"
        assert result["pending_operations"][0]["target"] == "src/main.py"
        assert result["pending_operations"][0]["state"] == "in_progress"
        assert result["pending_operations"][0]["details"]["line"] == 42

        assert result["pending_operations"][1]["type"] == "test"
        assert result["pending_operations"][1]["target"] == "tests/test_main.py"
        assert result["pending_operations"][1]["state"] == "pending"


class TestCheckpointSerializationFromDict:
    """Tests for HandoffCheckpoint.from_dict() deserialization."""

    def test_from_dict_creates_checkpoint_with_all_fields(self):
        """
        Test that from_dict() creates a HandoffCheckpoint with all fields populated.

        Given: A dict containing all required HandoffCheckpoint fields
        When: from_dict() is called
        Then: A HandoffCheckpoint is created with all fields correctly set
        """
        checkpoint_id = str(uuid4())
        chain_id = str(uuid4())

        data = {
            "checkpoint_id": checkpoint_id,
            "parent_checkpoint_id": None,
            "chain_id": chain_id,
            "created_at": "2026-02-27T10:30:00Z",
            "transcript_offset": 100,
            "transcript_entry_count": 10,
            "task_name": "Fix bug in authentication",
            "task_type": "bugfix",
            "progress_percent": 75,
            "blocker": {"description": "API not responding"},
            "next_steps": "Debug API call\nAdd retry logic",
            "git_branch": "fix/auth-bug",
            "active_files": ["src/auth.py", "tests/test_auth.py"],
            "recent_tools": [
                {"name": "read", "file": "src/auth.py"},
                {"name": "edit", "file": "src/auth.py"}
            ],
            "transcript_path": "/transcripts/session1.txt",
            "handover": {"decisions": ["Use retry decorator"]},
            "open_conversation_context": {"user": "developer1"},
            "visual_context": {"visible": "error logs"},
            "resolved_issues": [
                {"id": "42", "description": "Fixed import error"}
            ],
            "modifications": [
                {"file": "src/auth.py", "lines_added": 10}
            ],
            "original_user_request": "Fix authentication bug",
            "first_user_request": "Fix authentication bug",
            "saved_at": "2026-02-27T10:30:00Z",
            "version": 1,
            "implementation_status": {"stage": "testing"},
            "pending_operations": [
                {
                    "type": "edit",
                    "target": "src/auth.py",
                    "state": "in_progress",
                    "details": {"line": 55}
                }
            ],
            "checksum": "validchecksum456"
        }

        checkpoint = HandoffCheckpoint.from_dict(data)

        assert checkpoint.checkpoint_id == checkpoint_id
        assert checkpoint.parent_checkpoint_id is None
        assert checkpoint.chain_id == chain_id
        assert checkpoint.created_at == "2026-02-27T10:30:00Z"
        assert checkpoint.transcript_offset == 100
        assert checkpoint.transcript_entry_count == 10
        assert checkpoint.task_name == "Fix bug in authentication"
        assert checkpoint.task_type == "bugfix"
        assert checkpoint.progress_percent == 75
        assert checkpoint.blocker["description"] == "API not responding"
        assert checkpoint.next_steps == "Debug API call\nAdd retry logic"
        assert checkpoint.git_branch == "fix/auth-bug"
        assert checkpoint.active_files == ["src/auth.py", "tests/test_auth.py"]
        assert len(checkpoint.recent_tools) == 2
        assert checkpoint.transcript_path == "/transcripts/session1.txt"
        assert checkpoint.handover["decisions"] == ["Use retry decorator"]
        assert checkpoint.open_conversation_context["user"] == "developer1"
        assert checkpoint.visual_context["visible"] == "error logs"
        assert len(checkpoint.resolved_issues) == 1
        assert len(checkpoint.modifications) == 1
        assert checkpoint.original_user_request == "Fix authentication bug"
        assert checkpoint.first_user_request == "Fix authentication bug"
        assert checkpoint.saved_at == "2026-02-27T10:30:00Z"
        assert checkpoint.version == 1
        assert checkpoint.implementation_status["stage"] == "testing"
        assert checkpoint.checksum == "validchecksum456"

    def test_from_dict_deserializes_pending_operations(self):
        """
        Test that from_dict() correctly deserializes PendingOperation dicts.

        Given: A dict with pending_operations containing dict entries
        When: from_dict() is called
        Then: PendingOperation objects are created correctly
        """
        data = {
            "checkpoint_id": str(uuid4()),
            "chain_id": str(uuid4()),
            "created_at": "2026-02-27T10:30:00Z",
            "transcript_offset": 0,
            "transcript_entry_count": 0,
            "task_name": "Test",
            "task_type": "informal",
            "progress_percent": 0,
            "blocker": None,
            "next_steps": "Start",
            "git_branch": None,
            "active_files": [],
            "recent_tools": [],
            "transcript_path": None,
            "handover": None,
            "open_conversation_context": None,
            "visual_context": None,
            "resolved_issues": [],
            "modifications": [],
            "original_user_request": None,
            "first_user_request": None,
            "saved_at": "2026-02-27T10:30:00Z",
            "version": 1,
            "implementation_status": None,
            "pending_operations": [
                {
                    "type": "command",
                    "target": "pytest tests/",
                    "state": "pending",
                    "details": {"timeout": 60}
                },
                {
                    "type": "skill",
                    "target": "/test-runner",
                    "state": "in_progress",
                    "details": {"args": "verbose"}
                }
            ],
            "checksum": "checksum789"
        }

        checkpoint = HandoffCheckpoint.from_dict(data)

        assert len(checkpoint.pending_operations) == 2
        assert isinstance(checkpoint.pending_operations[0], PendingOperation)
        assert checkpoint.pending_operations[0].type == "command"
        assert checkpoint.pending_operations[0].target == "pytest tests/"
        assert checkpoint.pending_operations[0].state == "pending"
        assert checkpoint.pending_operations[0].details["timeout"] == 60

        assert checkpoint.pending_operations[1].type == "skill"
        assert checkpoint.pending_operations[1].target == "/test-runner"
        assert checkpoint.pending_operations[1].state == "in_progress"

    def test_from_dict_missing_required_fields_raises_error(self):
        """
        Test that from_dict() raises ValueError when required fields are missing.

        Given: A dict missing required checkpoint_id field
        When: from_dict() is called
        Then: ValueError is raised with list of missing fields
        """
        data = {
            "chain_id": str(uuid4()),
            "created_at": "2026-02-27T10:30:00Z",
            "task_name": "Test",
            "task_type": "informal",
            "progress_percent": 0,
            "next_steps": "Start",
            "active_files": [],
            "recent_tools": [],
            "saved_at": "2026-02-27T10:30:00Z",
            "version": 1,
            "checksum": "checksum"
        }

        with pytest.raises(ValueError, match="Missing required fields"):
            HandoffCheckpoint.from_dict(data)

    def test_from_dict_empty_checksum_raises_error(self):
        """
        Test that from_dict() rejects empty checksum strings.

        Given: A dict with an empty checksum string
        When: from_dict() is called
        Then: ValueError is raised about invalid checksum
        """
        data = {
            "checkpoint_id": str(uuid4()),
            "chain_id": str(uuid4()),
            "created_at": "2026-02-27T10:30:00Z",
            "task_name": "Test",
            "task_type": "informal",
            "progress_percent": 0,
            "blocker": None,
            "next_steps": "Start",
            "git_branch": None,
            "active_files": [],
            "recent_tools": [],
            "transcript_path": None,
            "handover": None,
            "open_conversation_context": None,
            "visual_context": None,
            "resolved_issues": [],
            "modifications": [],
            "original_user_request": None,
            "first_user_request": None,
            "saved_at": "2026-02-27T10:30:00Z",
            "version": 1,
            "implementation_status": None,
            "pending_operations": [],
            "checksum": ""  # Invalid empty checksum
        }

        with pytest.raises(ValueError, match="checksum"):
            HandoffCheckpoint.from_dict(data)

    def test_from_dict_invalid_checksum_format_is_rejected(self):
        """
        Test that from_dict() validates checksum format (should be hex string).

        Given: A dict with a malformed checksum (e.g., containing spaces)
        When: from_dict() is called
        Then: ValueError is raised about invalid checksum format
        """
        data = {
            "checkpoint_id": str(uuid4()),
            "chain_id": str(uuid4()),
            "created_at": "2026-02-27T10:30:00Z",
            "task_name": "Test",
            "task_type": "informal",
            "progress_percent": 0,
            "blocker": None,
            "next_steps": "Start",
            "git_branch": None,
            "active_files": [],
            "recent_tools": [],
            "transcript_path": None,
            "handover": None,
            "open_conversation_context": None,
            "visual_context": None,
            "resolved_issues": [],
            "modifications": [],
            "original_user_request": None,
            "first_user_request": None,
            "saved_at": "2026-02-27T10:30:00Z",
            "version": 1,
            "implementation_status": None,
            "pending_operations": [],
            "checksum": "not a valid hex checksum!"  # Invalid characters
        }

        with pytest.raises(ValueError, match="checksum"):
            HandoffCheckpoint.from_dict(data)

    def test_from_dict_invalid_progress_percent_raises_error(self):
        """
        Test that from_dict() validates progress_percent is within 0-100 range.

        Given: A dict with progress_percent set to 150 (out of range)
        When: from_dict() is called
        Then: ValueError is raised about invalid progress_percent
        """
        data = {
            "checkpoint_id": str(uuid4()),
            "chain_id": str(uuid4()),
            "created_at": "2026-02-27T10:30:00Z",
            "task_name": "Test",
            "task_type": "informal",
            "progress_percent": 150,  # Invalid: must be 0-100
            "blocker": None,
            "next_steps": "Start",
            "git_branch": None,
            "active_files": [],
            "recent_tools": [],
            "transcript_path": None,
            "handover": None,
            "open_conversation_context": None,
            "visual_context": None,
            "resolved_issues": [],
            "modifications": [],
            "original_user_request": None,
            "first_user_request": None,
            "saved_at": "2026-02-27T10:30:00Z",
            "version": 1,
            "implementation_status": None,
            "pending_operations": [],
            "checksum": "valid_checksum_abc123"
        }

        with pytest.raises(ValueError, match="progress_percent"):
            HandoffCheckpoint.from_dict(data)


class TestCheckpointRoundTripSerialization:
    """Tests for round-trip serialization (to_dict -> from_dict)."""

    def test_round_trip_preserves_all_fields(self):
        """
        Test that round-trip serialization preserves all data without loss.

        Given: A HandoffCheckpoint with all fields populated
        When: Serialized to dict, then deserialized back to HandoffCheckpoint
        Then: All fields match the original values exactly
        """
        original = HandoffCheckpoint(
            checkpoint_id=str(uuid4()),
            parent_checkpoint_id=str(uuid4()),
            chain_id=str(uuid4()),
            created_at="2026-02-27T10:30:00Z",
            transcript_offset=12345,
            transcript_entry_count=99,
            task_name="Complex feature implementation",
            task_type="formal",
            progress_percent=42,
            blocker={"description": "External API down", "severity": "high"},
            next_steps="Step 1\nStep 2\nStep 3",
            git_branch="feature/complex",
            active_files=["src/a.py", "src/b.py", "tests/test.py"],
            recent_tools=[
                {"name": "read", "file": "src/a.py", "lines": "1-100"},
                {"name": "edit", "file": "src/a.py", "change": "added method"},
                {"name": "test", "file": "tests/test.py", "result": "failed"}
            ],
            transcript_path="/workspace/transcripts/feb27.txt",
            handover={
                "decisions": ["Use async/await", "Cache responses"],
                "patterns": ["retry pattern", "circuit breaker"]
            },
            open_conversation_context={
                "thread_id": "thread-xyz",
                "messages_count": 45
            },
            visual_context={
                "description": "Error visible in logs",
                "ui_element": "status bar"
            },
            resolved_issues=[
                {"id": "1", "description": "Import error", "fixed_at": "10:00"},
                {"id": "2", "description": "Type error", "fixed_at": "10:15"}
            ],
            modifications=[
                {"file": "src/a.py", "lines_added": 25, "lines_removed": 10},
                {"file": "src/b.py", "lines_added": 15, "lines_removed": 5}
            ],
            original_user_request="Implement complex feature with caching",
            first_user_request="Implement complex feature",
            saved_at="2026-02-27T10:30:00Z",
            version=1,
            implementation_status={
                "stage": "implementation",
                "remaining_tasks": 3,
                "blocked": False
            },
            pending_operations=[
                PendingOperation(
                    type="edit",
                    target="src/a.py",
                    state="in_progress",
                    details={"line": 150, "method": "process_data"}
                ),
                PendingOperation(
                    type="test",
                    target="tests/test_a.py",
                    state="pending",
                    details={"test_case": "test_process_data"}
                ),
            ],
            checksum="validchecksum123456"
        )

        # Serialize to dict
        serialized = original.to_dict()

        # Deserialize back to HandoffCheckpoint
        restored = HandoffCheckpoint.from_dict(serialized)

        # Verify all fields match
        assert restored.checkpoint_id == original.checkpoint_id
        assert restored.parent_checkpoint_id == original.parent_checkpoint_id
        assert restored.chain_id == original.chain_id
        assert restored.created_at == original.created_at
        assert restored.transcript_offset == original.transcript_offset
        assert restored.transcript_entry_count == original.transcript_entry_count
        assert restored.task_name == original.task_name
        assert restored.task_type == original.task_type
        assert restored.progress_percent == original.progress_percent
        assert restored.blocker == original.blocker
        assert restored.next_steps == original.next_steps
        assert restored.git_branch == original.git_branch
        assert restored.active_files == original.active_files
        assert restored.recent_tools == original.recent_tools
        assert restored.transcript_path == original.transcript_path
        assert restored.handover == original.handover
        assert restored.open_conversation_context == original.open_conversation_context
        assert restored.visual_context == original.visual_context
        assert restored.resolved_issues == original.resolved_issues
        assert restored.modifications == original.modifications
        assert restored.original_user_request == original.original_user_request
        assert restored.first_user_request == original.first_user_request
        assert restored.saved_at == original.saved_at
        assert restored.version == original.version
        assert restored.implementation_status == original.implementation_status
        assert restored.checksum == original.checksum

        # Verify pending_operations are restored correctly
        assert len(restored.pending_operations) == len(original.pending_operations)
        for i, (orig, rest) in enumerate(zip(original.pending_operations, restored.pending_operations)):
            assert rest.type == orig.type
            assert rest.target == orig.target
            assert rest.state == orig.state
            assert rest.details == orig.details
            assert rest.started_at == orig.started_at

    def test_round_trip_with_none_optional_fields(self):
        """
        Test round-trip serialization preserves None values for optional fields.

        Given: A HandoffCheckpoint with many optional fields set to None
        When: Serialized to dict, then deserialized
        Then: All None fields are preserved as None
        """
        original = HandoffCheckpoint(
            checkpoint_id=str(uuid4()),
            parent_checkpoint_id=None,
            chain_id=str(uuid4()),
            created_at="2026-02-27T10:30:00Z",
            transcript_offset=0,
            transcript_entry_count=0,
            task_name="Minimal task",
            task_type="informal",
            progress_percent=0,
            blocker=None,
            next_steps="",
            git_branch=None,
            active_files=[],
            recent_tools=[],
            transcript_path=None,
            handover=None,
            open_conversation_context=None,
            visual_context=None,
            resolved_issues=[],
            modifications=[],
            original_user_request=None,
            first_user_request=None,
            saved_at="2026-02-27T10:30:00Z",
            version=1,
            implementation_status=None,
            pending_operations=[],
            checksum="minimal_checksum"
        )

        restored = HandoffCheckpoint.from_dict(original.to_dict())

        assert restored.parent_checkpoint_id is None
        assert restored.blocker is None
        assert restored.git_branch is None
        assert restored.transcript_path is None
        assert restored.handover is None
        assert restored.open_conversation_context is None
        assert restored.visual_context is None
        assert restored.original_user_request is None
        assert restored.first_user_request is None
        assert restored.implementation_status is None
        assert restored.pending_operations == []
        assert restored.next_steps == ""
        assert restored.active_files == []
        assert restored.recent_tools == []

    def test_round_trip_preserves_empty_collections(self):
        """
        Test that empty lists and dicts are preserved during round-trip.

        Given: A HandoffCheckpoint with empty lists and dicts
        When: Round-trip serialized
        Then: Empty collections remain empty (not converted to None)
        """
        original = HandoffCheckpoint(
            checkpoint_id=str(uuid4()),
            parent_checkpoint_id=None,
            chain_id=str(uuid4()),
            created_at="2026-02-27T10:30:00Z",
            transcript_offset=0,
            transcript_entry_count=0,
            task_name="Test",
            task_type="informal",
            progress_percent=0,
            blocker=None,
            next_steps="",
            git_branch=None,
            active_files=[],
            recent_tools=[],
            transcript_path=None,
            handover={},
            open_conversation_context={},
            visual_context={},
            resolved_issues=[],
            modifications=[],
            original_user_request=None,
            first_user_request=None,
            saved_at="2026-02-27T10:30:00Z",
            version=1,
            implementation_status={},
            pending_operations=[],
            checksum="checksum_empty"
        )

        restored = HandoffCheckpoint.from_dict(original.to_dict())

        # Empty dicts should remain empty dicts (not None)
        assert restored.handover == {}
        assert restored.open_conversation_context == {}
        assert restored.visual_context == {}
        assert restored.implementation_status == {}

        # Empty lists should remain empty lists
        assert restored.active_files == []
        assert restored.recent_tools == []
        assert restored.resolved_issues == []
        assert restored.modifications == []
        assert restored.pending_operations == []

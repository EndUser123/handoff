#!/usr/bin/env python3
"""Tests for checkpoint chain functionality.

Tests checkpoint chain creation, linking, traversal, and
backward compatibility with old handoffs.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

# Add handoff package to path
HANDOFF_PACKAGE = Path(__file__).parent.parent.parent / "src"
if str(HANDOFF_PACKAGE) not in globals():
    import sys
    sys.path.insert(0, str(HANDOFF_PACKAGE))

from handoff.checkpoint_chain import CheckpointChain, HandoffCheckpointRef
from handoff.migrate import migrate_checkpoint_chain_fields
from handoff.models import HandoffCheckpoint, PendingOperation


class TestPendingOperation:
    """Tests for PendingOperation dataclass."""

    def test_create_pending_operation(self):
        """Test creating a PendingOperation."""
        op = PendingOperation(
            type="edit",
            target="src/main.py",
            state="in_progress",
            details={"line": 42}
        )
        assert op.type == "edit"
        assert op.target == "src/main.py"
        assert op.state == "in_progress"
        assert op.details == {"line": 42}

    def test_pending_operation_to_dict(self):
        """Test PendingOperation serialization to dict."""
        op = PendingOperation(
            type="test",
            target="tests/test_file.py",
            state="pending"
        )
        result = op.to_dict()
        assert result["type"] == "test"
        assert result["target"] == "tests/test_file.py"
        assert result["state"] == "pending"

    def test_pending_operation_from_dict_valid(self):
        """Test PendingOperation deserialization from valid dict."""
        data = {
            "type": "read",
            "target": "config.json",
            "state": "failed",
            "details": {"error": "file not found"}
        }
        op = PendingOperation.from_dict(data)
        assert op.type == "read"
        assert op.target == "config.json"
        assert op.state == "failed"

    def test_pending_operation_from_dict_missing_fields(self):
        """Test PendingOperation deserialization with missing fields."""
        with pytest.raises(ValueError, match="Missing required fields"):
            PendingOperation.from_dict({"type": "edit"})

    def test_pending_operation_invalid_type(self):
        """Test PendingOperation with invalid type."""
        data = {
            "type": "invalid_type",
            "target": "test",
            "state": "pending"
        }
        with pytest.raises(ValueError, match="Invalid type"):
            PendingOperation.from_dict(data)

    def test_pending_operation_invalid_state(self):
        """Test PendingOperation with invalid state."""
        data = {
            "type": "edit",
            "target": "test",
            "state": "invalid_state"
        }
        with pytest.raises(ValueError, match="Invalid state"):
            PendingOperation.from_dict(data)


class TestHandoffCheckpoint:
    """Tests for HandoffCheckpoint model."""

    def test_create_checkpoint(self):
        """Test creating a HandoffCheckpoint."""
        checkpoint_id = str(uuid4())
        chain_id = str(uuid4())

        checkpoint = HandoffCheckpoint(
            checkpoint_id=checkpoint_id,
            parent_checkpoint_id=None,
            chain_id=chain_id,
            created_at="2025-02-16T12:00:00Z",
            transcript_offset=12345,
            transcript_entry_count=42,
            task_name="test task",
            task_type="informal",
            progress_percent=50,
            blocker=None,
            next_steps="Complete the work",
            git_branch="main",
            active_files=["src/main.py"],
            recent_tools=[],
            transcript_path="/transcript.json",
            handover=None,
            open_conversation_context=None,
            visual_context=None,
            resolved_issues=[],
            modifications=[],
            original_user_request="test message",
            first_user_request="first message",
            saved_at="2025-02-16T12:00:00Z",
            version=1,
            implementation_status=None,
            pending_operations=[],
            checksum="sha256:abc123"
        )

        assert checkpoint.checkpoint_id == checkpoint_id
        assert checkpoint.parent_checkpoint_id is None
        assert checkpoint.chain_id == chain_id

    def test_checkpoint_to_dict(self):
        """Test HandoffCheckpoint serialization to dict."""
        checkpoint_id = str(uuid4())
        chain_id = str(uuid4())

        checkpoint = HandoffCheckpoint(
            checkpoint_id=checkpoint_id,
            parent_checkpoint_id=None,
            chain_id=chain_id,
            created_at="2025-02-16T12:00:00Z",
            transcript_offset=0,
            transcript_entry_count=0,
            task_name="test",
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
            saved_at="2025-02-16T12:00:00Z",
            version=1,
            implementation_status=None,
            pending_operations=[],
            checksum="sha256:test"
        )

        result = checkpoint.to_dict()
        assert result["checkpoint_id"] == checkpoint_id
        assert result["chain_id"] == chain_id

    def test_checkpoint_from_dict_valid(self):
        """Test HandoffCheckpoint deserialization from valid dict."""
        checkpoint_id = str(uuid4())
        chain_id = str(uuid4())

        data = {
            "checkpoint_id": checkpoint_id,
            "parent_checkpoint_id": None,
            "chain_id": chain_id,
            "created_at": "2025-02-16T12:00:00Z",
            "transcript_offset": 0,
            "transcript_entry_count": 0,
            "task_name": "test",
            "task_type": "informal",
            "progress_percent": 0,
            "blocker": None,
            "next_steps": "",
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
            "saved_at": "2025-02-16T12:00:00Z",
            "version": 1,
            "implementation_status": None,
            "pending_operations": [],
            "checksum": "sha256:" + "a" * 64
        }

        checkpoint = HandoffCheckpoint.from_dict(data)
        assert checkpoint.checkpoint_id == checkpoint_id
        assert checkpoint.chain_id == chain_id

    def test_checkpoint_from_dict_with_pending_operations(self):
        """Test HandoffCheckpoint with pending operations."""
        checkpoint_id = str(uuid4())
        chain_id = str(uuid4())

        data = {
            "checkpoint_id": checkpoint_id,
            "parent_checkpoint_id": None,
            "chain_id": chain_id,
            "created_at": "2025-02-16T12:00:00Z",
            "transcript_offset": 0,
            "transcript_entry_count": 0,
            "task_name": "test",
            "task_type": "informal",
            "progress_percent": 0,
            "blocker": None,
            "next_steps": "",
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
            "saved_at": "2025-02-16T12:00:00Z",
            "version": 1,
            "implementation_status": None,
            "pending_operations": [
                {
                    "type": "edit",
                    "target": "src/main.py",
                    "state": "in_progress",
                    "details": {}
                }
            ],
            "checksum": "sha256:" + "a" * 64
        }

        checkpoint = HandoffCheckpoint.from_dict(data)
        assert len(checkpoint.pending_operations) == 1
        assert checkpoint.pending_operations[0].type == "edit"


class TestCheckpointChain:
    """Tests for checkpoint chain linking."""

    def test_checkpoint_id_generation(self):
        """Test that checkpoint_id is generated as valid UUID v4."""
        from handoff.hooks.__lib.handoff_store import HandoffStore

        store = HandoffStore(
            project_root=Path("."),
            terminal_id="test_terminal"
        )

        # Build handoff data twice to test checkpoint linking
        handoff1 = store.build_handoff_data(
            task_name="Task 1",
            progress_pct=25,
            blocker=None,
            files_modified=[],
            next_steps=[],
            handover={},
            modifications=[],
        )

        handoff2 = store.build_handoff_data(
            task_name="Task 2",
            progress_pct=50,
            blocker=None,
            files_modified=[],
            next_steps=[],
            handover={},
            modifications=[],
        )

        # Verify checkpoint_id format (UUID v4)
        assert "-" in handoff1["checkpoint_id"]
        assert "-" in handoff2["checkpoint_id"]
        assert handoff1["checkpoint_id"] != handoff2["checkpoint_id"]

        # Verify parent linking
        assert handoff1["parent_checkpoint_id"] is None  # First in chain
        assert handoff2["parent_checkpoint_id"] == handoff1["checkpoint_id"]  # Links to first

        # Verify chain_id groups checkpoints
        assert handoff1["chain_id"] == handoff2["chain_id"]  # Same session

    def test_backward_compatibility_old_handoffs(self):
        """Test that old handoffs without new fields can be loaded."""
        old_handoff = {
            "task_name": "old task",
            "progress_percent": 10,
            "blocker": None,
            "next_steps": "Continue work",
            "git_branch": "main",
            "active_files": [],
            "recent_tools": [],
            "transcript_path": None,
            "handover": None,
            "resolved_issues": [],
            "modifications": [],
            "saved_at": "2025-02-16T12:00:00Z",
            "version": 1
        }

        # Migration should add missing fields
        migrated = migrate_checkpoint_chain_fields(old_handoff)

        assert "checkpoint_id" in migrated
        assert "parent_checkpoint_id" in migrated
        assert "chain_id" in migrated
        assert "transcript_offset" in migrated
        assert "transcript_entry_count" in migrated

        # Parent should be None for migrated handoffs
        assert migrated["parent_checkpoint_id"] is None

    def test_migration_is_idempotent(self):
        """Test that migration can be run multiple times safely."""
        old_handoff = {
            "task_name": "old task",
            "progress_percent": 10,
            "next_steps": "Continue work",
            "saved_at": "2025-02-16T12:00:00Z",
            "version": 1
        }

        # Run migration twice
        migrated1 = migrate_checkpoint_chain_fields(old_handoff)
        migrated2 = migrate_checkpoint_chain_fields(migrated1)

        # Checkpoint IDs should be preserved on second run
        assert migrated1["checkpoint_id"] == migrated2["checkpoint_id"]
        assert migrated1["chain_id"] == migrated2["chain_id"]

    def test_checkpoint_ref_creation(self):
        """Test HandoffCheckpointRef creation from task metadata."""
        checkpoint_id = str(uuid4())
        chain_id = str(uuid4())

        metadata = {
            "handoff": {
                "checkpoint_id": checkpoint_id,
                "parent_checkpoint_id": None,
                "chain_id": chain_id,
                "saved_at": "2025-02-16T12:00:00Z",
                "transcript_offset": 1000,
                "transcript_entry_count": 10
            },
            "created_at": "2025-02-16T12:00:00Z"
        }

        ref = HandoffCheckpointRef.from_task_metadata("task_123", metadata)

        assert ref.checkpoint_id == checkpoint_id
        assert ref.parent_checkpoint_id is None
        assert ref.chain_id == chain_id
        assert ref.task_id == "task_123"
        assert ref.transcript_offset == 1000
        assert ref.transcript_entry_count == 10


class TestCheckpointChainTraversal:
    """Tests for CheckpointChain traversal methods."""

    def test_get_chain_empty(self):
        """Test get_chain with no checkpoints."""
        with tempfile.TemporaryDirectory() as tmpdir:
            chain = CheckpointChain(Path(tmpdir), "test_terminal")
            result = chain.get_chain("nonexistent_chain")
            assert result == []

    def test_get_latest_empty(self):
        """Test get_latest with no checkpoints."""
        with tempfile.TemporaryDirectory() as tmpdir:
            chain = CheckpointChain(Path(tmpdir), "test_terminal")
            result = chain.get_latest("nonexistent_chain")
            assert result is None

    def test_get_chain_with_checkpoints(self):
        """Test get_chain returns checkpoints in chronological order."""
        import json

        chain_id = str(uuid4())
        checkpoint_id_1 = str(uuid4())
        checkpoint_id_2 = str(uuid4())
        checkpoint_id_3 = str(uuid4())

        with tempfile.TemporaryDirectory() as tmpdir:
            task_file = Path(tmpdir) / "test_terminal_tasks.json"

            # Create task file with 3 checkpoints in a chain
            task_data = {
                "tasks": {
                    "task_1": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_id_1,
                                "parent_checkpoint_id": None,
                                "chain_id": chain_id,
                                "saved_at": "2025-02-16T12:00:00Z",
                                "transcript_offset": 0,
                                "transcript_entry_count": 0
                            }
                        },
                        "created_at": "2025-02-16T12:00:00Z"
                    },
                    "task_2": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_id_2,
                                "parent_checkpoint_id": checkpoint_id_1,
                                "chain_id": chain_id,
                                "saved_at": "2025-02-16T12:05:00Z",
                                "transcript_offset": 1000,
                                "transcript_entry_count": 10
                            }
                        },
                        "created_at": "2025-02-16T12:05:00Z"
                    },
                    "task_3": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_id_3,
                                "parent_checkpoint_id": checkpoint_id_2,
                                "chain_id": chain_id,
                                "saved_at": "2025-02-16T12:10:00Z",
                                "transcript_offset": 2000,
                                "transcript_entry_count": 20
                            }
                        },
                        "created_at": "2025-02-16T12:10:00Z"
                    }
                }
            }

            task_file.write_text(json.dumps(task_data))

            chain = CheckpointChain(Path(tmpdir), "test_terminal")
            result = chain.get_chain(chain_id)

            assert len(result) == 3
            assert result[0].checkpoint_id == checkpoint_id_1
            assert result[1].checkpoint_id == checkpoint_id_2
            assert result[2].checkpoint_id == checkpoint_id_3

    def test_get_latest_with_checkpoints(self):
        """Test get_latest returns the newest checkpoint."""
        import json

        chain_id = str(uuid4())
        checkpoint_id_1 = str(uuid4())
        checkpoint_id_2 = str(uuid4())
        checkpoint_id_3 = str(uuid4())

        with tempfile.TemporaryDirectory() as tmpdir:
            task_file = Path(tmpdir) / "test_terminal_tasks.json"

            # Create task file with 3 checkpoints
            task_data = {
                "tasks": {
                    "task_1": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_id_1,
                                "parent_checkpoint_id": None,
                                "chain_id": chain_id,
                                "saved_at": "2025-02-16T12:00:00Z",
                                "transcript_offset": 0,
                                "transcript_entry_count": 0
                            }
                        },
                        "created_at": "2025-02-16T12:00:00Z"
                    },
                    "task_2": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_id_2,
                                "parent_checkpoint_id": checkpoint_id_1,
                                "chain_id": chain_id,
                                "saved_at": "2025-02-16T12:05:00Z",
                                "transcript_offset": 1000,
                                "transcript_entry_count": 10
                            }
                        },
                        "created_at": "2025-02-16T12:05:00Z"
                    },
                    "task_3": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_id_3,
                                "parent_checkpoint_id": checkpoint_id_2,
                                "chain_id": chain_id,
                                "saved_at": "2025-02-16T12:10:00Z",
                                "transcript_offset": 2000,
                                "transcript_entry_count": 20
                            }
                        },
                        "created_at": "2025-02-16T12:10:00Z"
                    }
                }
            }

            task_file.write_text(json.dumps(task_data))

            chain = CheckpointChain(Path(tmpdir), "test_terminal")
            latest = chain.get_latest(chain_id)

            assert latest is not None
            assert latest.checkpoint_id == checkpoint_id_3

    def test_get_previous(self):
        """Test get_previous returns the previous checkpoint in chain."""
        import json

        chain_id = str(uuid4())
        checkpoint_id_1 = str(uuid4())
        checkpoint_id_2 = str(uuid4())
        checkpoint_id_3 = str(uuid4())

        with tempfile.TemporaryDirectory() as tmpdir:
            task_file = Path(tmpdir) / "test_terminal_tasks.json"

            task_data = {
                "tasks": {
                    "task_1": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_id_1,
                                "parent_checkpoint_id": None,
                                "chain_id": chain_id,
                                "saved_at": "2025-02-16T12:00:00Z",
                                "transcript_offset": 0,
                                "transcript_entry_count": 0
                            }
                        },
                        "created_at": "2025-02-16T12:00:00Z"
                    },
                    "task_2": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_id_2,
                                "parent_checkpoint_id": checkpoint_id_1,
                                "chain_id": chain_id,
                                "saved_at": "2025-02-16T12:05:00Z",
                                "transcript_offset": 1000,
                                "transcript_entry_count": 10
                            }
                        },
                        "created_at": "2025-02-16T12:05:00Z"
                    },
                    "task_3": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_id_3,
                                "parent_checkpoint_id": checkpoint_id_2,
                                "chain_id": chain_id,
                                "saved_at": "2025-02-16T12:10:00Z",
                                "transcript_offset": 2000,
                                "transcript_entry_count": 20
                            }
                        },
                        "created_at": "2025-02-16T12:10:00Z"
                    }
                }
            }

            task_file.write_text(json.dumps(task_data))

            chain = CheckpointChain(Path(tmpdir), "test_terminal")

            # Get previous for middle checkpoint
            prev = chain.get_previous(checkpoint_id_2)
            assert prev is not None
            assert prev.checkpoint_id == checkpoint_id_1

            # Get previous for last checkpoint
            prev = chain.get_previous(checkpoint_id_3)
            assert prev is not None
            assert prev.checkpoint_id == checkpoint_id_2

            # Get previous for first checkpoint (no previous)
            prev = chain.get_previous(checkpoint_id_1)
            assert prev is None

    def test_get_next(self):
        """Test get_next returns the next checkpoint in chain."""
        import json

        chain_id = str(uuid4())
        checkpoint_id_1 = str(uuid4())
        checkpoint_id_2 = str(uuid4())
        checkpoint_id_3 = str(uuid4())

        with tempfile.TemporaryDirectory() as tmpdir:
            task_file = Path(tmpdir) / "test_terminal_tasks.json"

            task_data = {
                "tasks": {
                    "task_1": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_id_1,
                                "parent_checkpoint_id": None,
                                "chain_id": chain_id,
                                "saved_at": "2025-02-16T12:00:00Z",
                                "transcript_offset": 0,
                                "transcript_entry_count": 0
                            }
                        },
                        "created_at": "2025-02-16T12:00:00Z"
                    },
                    "task_2": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_id_2,
                                "parent_checkpoint_id": checkpoint_id_1,
                                "chain_id": chain_id,
                                "saved_at": "2025-02-16T12:05:00Z",
                                "transcript_offset": 1000,
                                "transcript_entry_count": 10
                            }
                        },
                        "created_at": "2025-02-16T12:05:00Z"
                    },
                    "task_3": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_id_3,
                                "parent_checkpoint_id": checkpoint_id_2,
                                "chain_id": chain_id,
                                "saved_at": "2025-02-16T12:10:00Z",
                                "transcript_offset": 2000,
                                "transcript_entry_count": 20
                            }
                        },
                        "created_at": "2025-02-16T12:10:00Z"
                    }
                }
            }

            task_file.write_text(json.dumps(task_data))

            chain = CheckpointChain(Path(tmpdir), "test_terminal")

            # Get next for first checkpoint
            next_cp = chain.get_next(checkpoint_id_1)
            assert next_cp is not None
            assert next_cp.checkpoint_id == checkpoint_id_2

            # Get next for middle checkpoint
            next_cp = chain.get_next(checkpoint_id_2)
            assert next_cp is not None
            assert next_cp.checkpoint_id == checkpoint_id_3

            # Get next for last checkpoint (no next)
            next_cp = chain.get_next(checkpoint_id_3)
            assert next_cp is None

    def test_cache_behavior(self):
        """Test that chain results are cached after first call."""
        import json

        chain_id = str(uuid4())
        checkpoint_id_1 = str(uuid4())

        with tempfile.TemporaryDirectory() as tmpdir:
            task_file = Path(tmpdir) / "test_terminal_tasks.json"

            task_data = {
                "tasks": {
                    "task_1": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_id_1,
                                "parent_checkpoint_id": None,
                                "chain_id": chain_id,
                                "saved_at": "2025-02-16T12:00:00Z",
                                "transcript_offset": 0,
                                "transcript_entry_count": 0
                            }
                        },
                        "created_at": "2025-02-16T12:00:00Z"
                    }
                }
            }

            task_file.write_text(json.dumps(task_data))

            chain = CheckpointChain(Path(tmpdir), "test_terminal")

            # First call should load from file
            result1 = chain.get_chain(chain_id)
            assert len(result1) == 1

            # Second call should use cache (same object reference)
            result2 = chain.get_chain(chain_id)
            assert len(result2) == 1
            assert result1 is result2  # Same cached list object

#!/usr/bin/env python3
"""
End-to-end integration tests for the handoff package.

These tests demonstrate the full workflow:
1. Creating a handoff checkpoint
2. Serializing to dict
3. Deserializing from dict
4. Traversing checkpoint chains
5. Validating checksums
"""

from handoff.checkpoint_chain import CheckpointChain
from handoff.migrate import compute_metadata_checksum
from handoff.models import HandoffCheckpoint, PendingOperation


class TestHandoffIntegration:
    """End-to-end handoff workflow tests."""

    def test_complete_handoff_lifecycle(self):
        """Test the complete handoff capture and restore lifecycle."""
        # Create a handoff checkpoint with full data
        checkpoint = HandoffCheckpoint(
            checkpoint_id="ckpt_integration_001",
            parent_checkpoint_id=None,
            chain_id="chain_integration_001",
            created_at="2026-02-17T14:30:00Z",
            task_name="Implement user authentication with JWT",
            task_type="feature",
            progress_percent=0,
            blocker=None,
            next_steps="Implement JWT authentication\\nAdd tests\\nUpdate documentation",
            git_branch="feature/jwt-auth",
            active_files=["src/auth.py", "tests/test_auth.py"],
            recent_tools=[],
            transcript_path="/transcript.json",
            handover=None,
            open_conversation_context=None,
            visual_context='{"screenshots": ["screenshot.png"]}',
            resolved_issues=[],
            modifications=[],
            original_user_request="Please implement JWT-based authentication for the API",
            first_user_request="Please implement JWT-based authentication for the API",
            saved_at="2026-02-17T14:30:00Z",
            version=1,
            implementation_status=None,
            transcript_offset=0,
            transcript_entry_count=10,
            pending_operations=[
                PendingOperation(
                    type="edit",
                    target="src/auth.py",
                    state="pending"
                ),
                PendingOperation(
                    type="test",
                    target="tests/test_auth.py",
                    state="pending"
                )
            ],
            checksum="sha256:abc123integration000000000000000000000000000000000000000000000000000000"
        )

        # Test serialization
        data_dict = checkpoint.to_dict()
        assert data_dict is not None
        assert data_dict["checkpoint_id"] == "ckpt_integration_001"
        assert data_dict["chain_id"] == "chain_integration_001"
        assert len(data_dict["pending_operations"]) == 2

        # Test deserialization
        restored = HandoffCheckpoint.from_dict(data_dict)
        assert restored.checkpoint_id == checkpoint.checkpoint_id
        assert restored.task_name == checkpoint.task_name
        assert restored.original_user_request == checkpoint.original_user_request
        assert len(restored.pending_operations) == len(checkpoint.pending_operations)

    def test_checkpoint_chain_traversal(self):
        """Test checkpoint chain creation and traversal."""
        import json
        import tempfile
        from pathlib import Path

        # Create a temporary task tracker directory
        with tempfile.TemporaryDirectory() as tmpdir:
            task_tracker_dir = Path(tmpdir)
            terminal_id = "test_terminal"

            # Create task file with checkpoint chain
            task_file = task_tracker_dir / f"{terminal_id}_tasks.json"
            task_data = {
                "tasks": {
                    "task_001": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": "ckpt_001",
                                "parent_checkpoint_id": None,
                                "chain_id": "chain_traversal_test",
                                "saved_at": "2026-02-17T14:30:00Z",
                                "task_name": "Step 1: Design",
                                "transcript_offset": 0,
                                "transcript_entry_count": 1,
                                "checksum": "sha256:checksum_100000000000000000000000000000000000000000000000000000000000000"
                            }
                        }
                    },
                    "task_002": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": "ckpt_002",
                                "parent_checkpoint_id": "ckpt_001",
                                "chain_id": "chain_traversal_test",
                                "saved_at": "2026-02-17T14:31:00Z",
                                "task_name": "Step 2: Implement",
                                "transcript_offset": 100,
                                "transcript_entry_count": 2,
                                "checksum": "sha256:checksum_200000000000000000000000000000000000000000000000000000000000000"
                            }
                        }
                    },
                    "task_003": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": "ckpt_003",
                                "parent_checkpoint_id": "ckpt_002",
                                "chain_id": "chain_traversal_test",
                                "saved_at": "2026-02-17T14:32:00Z",
                                "task_name": "Step 3: Test",
                                "transcript_offset": 200,
                                "transcript_entry_count": 3,
                                "checksum": "sha256:checksum_300000000000000000000000000000000000000000000000000000000000000"
                            }
                        }
                    }
                }
            }

            # Write task file
            with open(task_file, 'w') as f:
                json.dump(task_data, f)

            # Create chain
            chain = CheckpointChain(task_tracker_dir, terminal_id)

            # Test chain traversal
            latest = chain.get_latest("chain_traversal_test")
            assert latest is not None
            assert latest.checkpoint_id == "ckpt_003"

            # Test previous navigation
            step2 = chain.get_previous("ckpt_003")
            assert step2 is not None
            assert step2.checkpoint_id == "ckpt_002"

            # Test next navigation
            step3 = chain.get_next("ckpt_002")
            assert step3 is not None
            assert step3.checkpoint_id == "ckpt_003"

            # Test first checkpoint has no previous
            first = chain.get_previous("ckpt_001")
            assert first is None

            # Test last checkpoint has no next
            last = chain.get_next("ckpt_003")
            assert last is None

    def test_checksum_validation(self):
        """Test SHA256 checksum computation and validation."""
        checkpoint = HandoffCheckpoint(
            checkpoint_id="ckpt_checksum_001",
            parent_checkpoint_id=None,
            chain_id="chain_checksum_test",
            created_at="2026-02-17T14:30:00Z",
            task_name="Test checksum validation",
            task_type="test",
            progress_percent=100,
            blocker=None,
            next_steps="",
            git_branch="main",
            active_files=[],
            recent_tools=[],
            transcript_path="/transcript.json",
            handover=None,
            open_conversation_context=None,
            visual_context=None,
            resolved_issues=[],
            modifications=[],
            original_user_request="Test message",
            first_user_request="Test message",
            saved_at="2026-02-17T14:30:00Z",
            version=1,
            implementation_status=None,
            transcript_offset=0,
            transcript_entry_count=1,
            pending_operations=[],
            checksum=""
        )

        # Add metadata for checksum computation
        computed_checksum = compute_metadata_checksum({
            "test_key": "test_value"
        })

        # Verify checksum was computed
        assert computed_checksum is not None
        # compute_metadata_checksum returns "sha256:<64-char-hex>"
        assert computed_checksum.startswith("sha256:")
        assert len(computed_checksum) == 71  # "sha256:" + 64 hex chars

        # Assign to checkpoint
        checkpoint.checksum = computed_checksum

        # Verify serialization preserves checksum
        data_dict = checkpoint.to_dict()
        assert data_dict["checksum"] == computed_checksum

        restored = HandoffCheckpoint.from_dict(data_dict)
        assert restored.checksum == computed_checksum

    def test_pending_operation_validation(self):
        """Test pending operation type validation."""
        # Valid operation types
        valid_types = ["edit", "test", "read", "command", "skill"]

        for op_type in valid_types:
            op = PendingOperation(
                type=op_type,
                target=f"target_{op_type}",
                state="pending"
            )
            assert op.type == op_type
            assert op.target == f"target_{op_type}"

        # Test with full checkpoint
        checkpoint = HandoffCheckpoint(
            checkpoint_id="ckpt_pending_ops",
            parent_checkpoint_id=None,
            chain_id="chain_pending_test",
            created_at="2026-02-17T14:30:00Z",
            task_name="Test pending operations",
            task_type="test",
            progress_percent=0,
            blocker=None,
            next_steps="",
            git_branch="main",
            active_files=[],
            recent_tools=[],
            transcript_path="/transcript.json",
            handover=None,
            open_conversation_context=None,
            visual_context=None,
            resolved_issues=[],
            modifications=[],
            original_user_request="Test",
            first_user_request="Test",
            saved_at="2026-02-17T14:30:00Z",
            version=1,
            implementation_status=None,
            transcript_offset=0,
            transcript_entry_count=1,
            pending_operations=[
                PendingOperation(type=t, target=f"file_{t}", state="pending")
                for t in valid_types
            ],
            checksum="sha256:checksum_pending00000000000000000000000000000000000000000000000000000000000000"
        )

        assert len(checkpoint.pending_operations) == len(valid_types)

    def test_backward_compatibility_migration(self):
        """Test migration from old handoff format to new format."""
        # Old format (without checkpoint chain fields)
        old_handoff = {
            "task_name": "Old task",
            "task_type": "feature",
            "progress_percent": 50,
            "blocker": None,
            "next_steps": "",
            "active_files": [],
            "recent_tools": [],
            "original_user_request": "Old user message",
            "first_user_request": "Old user message",
            "saved_at": "2026-02-17T14:30:00Z",
            "version": 1
        }

        # Import migration function
        from handoff.migrate import migrate_checkpoint_chain_fields

        # Migrate to new format
        migrated = migrate_checkpoint_chain_fields(old_handoff)

        # Verify new fields were added
        assert "checkpoint_id" in migrated
        assert "parent_checkpoint_id" in migrated
        assert "chain_id" in migrated
        assert migrated["task_name"] == old_handoff["task_name"]
        assert migrated["original_user_request"] == old_handoff["original_user_request"]

    def test_empty_pending_operations(self):
        """Test checkpoint with no pending operations."""
        checkpoint = HandoffCheckpoint(
            checkpoint_id="ckpt_empty_pending",
            parent_checkpoint_id=None,
            chain_id="chain_empty_test",
            created_at="2026-02-17T14:30:00Z",
            task_name="Test empty pending operations",
            task_type="test",
            progress_percent=100,
            blocker=None,
            next_steps="",
            git_branch="main",
            active_files=[],
            recent_tools=[],
            transcript_path="/transcript.json",
            handover=None,
            open_conversation_context=None,
            visual_context=None,
            resolved_issues=[],
            modifications=[],
            original_user_request="Test",
            first_user_request="Test",
            saved_at="2026-02-17T14:30:00Z",
            version=1,
            implementation_status=None,
            transcript_offset=0,
            transcript_entry_count=1,
            pending_operations=[],  # Empty list
            checksum="sha256:checksum_empty0000000000000000000000000000000000000000000000000000000000000"
        )

        assert len(checkpoint.pending_operations) == 0

        # Serialize and deserialize
        data_dict = checkpoint.to_dict()
        restored = HandoffCheckpoint.from_dict(data_dict)

        assert len(restored.pending_operations) == 0

    def test_visual_context_preservation(self):
        """Test that visual context survives serialization."""
        visual_context = {
            "screenshots": ["screenshot1.png", "screenshot2.png"],
            "image_analysis": "The UI shows a login form with email and password fields",
            "diagrams": ["architecture.svg"]
        }

        checkpoint = HandoffCheckpoint(
            checkpoint_id="ckpt_visual_context",
            parent_checkpoint_id=None,
            chain_id="chain_visual_test",
            created_at="2026-02-17T14:30:00Z",
            task_name="Test visual context preservation",
            task_type="test",
            progress_percent=100,
            blocker=None,
            next_steps="",
            git_branch="main",
            active_files=[],
            recent_tools=[],
            transcript_path="/transcript.json",
            handover=None,
            open_conversation_context=None,
            visual_context=visual_context,
            resolved_issues=[],
            modifications=[],
            original_user_request="Test",
            first_user_request="Test",
            saved_at="2026-02-17T14:30:00Z",
            version=1,
            implementation_status=None,
            transcript_offset=0,
            transcript_entry_count=1,
            pending_operations=[],
            checksum="sha256:checksum_visual000000000000000000000000000000000000000000000000000000000000000"
        )

        # Serialize
        data_dict = checkpoint.to_dict()
        assert data_dict["visual_context"] == visual_context

        # Deserialize
        restored = HandoffCheckpoint.from_dict(data_dict)
        assert restored.visual_context == visual_context
        assert len(restored.visual_context["screenshots"]) == 2

#!/usr/bin/env python3
"""Regression test for checkpoint chain backward compatibility.

This test verifies that old handoff format (without checkpoint_ref fields)
can still be loaded and migrated correctly to create proper checkpoint references.

Run with: pytest tests/test_regression_backward_compat.py -v
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

# Add handoff package to path
HANDOFF_PACKAGE = Path(__file__).parent.parent / "src"
if str(HANDOFF_PACKAGE) not in globals():
    import sys
    sys.path.insert(0, str(HANDOFF_PACKAGE))

from handoff.checkpoint_chain import CheckpointChain, HandoffCheckpointRef
from handoff.migrate import migrate_checkpoint_chain_fields


class TestOldHandoffFormatBackwardCompatibility:
    """Tests for loading old handoff format without checkpoint chain fields."""

    def test_old_handoff_format_creates_checkpoint_ref_on_load(self):
        """
        Test that old handoff format (without checkpoint_ref) can be loaded
        and creates a proper checkpoint reference when loaded.

        Given: A task file with old handoff format (no checkpoint_id, chain_id, etc.)
        When: CheckpointChain loads the checkpoint
        Then: A HandoffCheckpointRef is created with proper checkpoint_ref fields

        This test FAILS because the expected behavior is not yet implemented.
        """
        # Create an old handoff format without checkpoint chain fields
        # This simulates a handoff created before checkpoint chain feature
        old_handoff_metadata = {
            "handoff": {
                "task_name": "Old task without checkpoint fields",
                "task_type": "informal",
                "progress_percent": 50,
                "blocker": None,
                "next_steps": "Complete the work",
                "git_branch": "main",
                "active_files": ["src/main.py"],
                "recent_tools": [],
                "transcript_path": None,
                "handover": None,
                "resolved_issues": [],
                "modifications": [],
                "saved_at": "2025-02-16T12:00:00Z",
                "version": 1
                # Note: No checkpoint_id, parent_checkpoint_id, chain_id, etc.
            },
            "created_at": "2025-02-16T12:00:00Z"
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create task file with old format
            task_file = Path(tmpdir) / "test_terminal_tasks.json"
            task_data = {
                "terminal_id": "test_terminal",
                "tasks": {
                    "task_1": {
                        "id": "task_1",
                        "subject": "Old task",
                        "status": "completed",
                        "created_at": "2025-02-16T12:00:00Z",
                        "metadata": old_handoff_metadata
                    }
                },
                "last_update": "2025-02-16T12:00:00Z"
            }

            task_file.write_text(json.dumps(task_data))

            # Load checkpoints via CheckpointChain
            chain = CheckpointChain(Path(tmpdir), "test_terminal")
            checkpoints = chain._load_all_checkpoints()

            # Expected: Old format should be migrated and create checkpoint_ref
            # This assertion will FAIL because old format without checkpoint_id
            # is not loaded into checkpoint list
            assert len(checkpoints) == 1, "Old handoff format should create a checkpoint_ref"

            checkpoint_ref = checkpoints[0]

            # Verify checkpoint_ref has all required fields
            assert isinstance(checkpoint_ref, HandoffCheckpointRef), \
                "Should create HandoffCheckpointRef from old format"

            assert checkpoint_ref.checkpoint_id != "", \
                "checkpoint_ref should have a valid checkpoint_id after migration"

            assert checkpoint_ref.chain_id != "", \
                "checkpoint_ref should have a valid chain_id after migration"

            assert checkpoint_ref.parent_checkpoint_id is None, \
                "Migrated old handoffs should have parent_checkpoint_id as None (first in chain)"

            assert checkpoint_ref.task_id == "task_1", \
                "checkpoint_ref should preserve original task_id"

            assert checkpoint_ref.transcript_offset == 0, \
                "Migrated handoffs should have transcript_offset default to 0"

            assert checkpoint_ref.transcript_entry_count == 0, \
                "Migrated handoffs should have transcript_entry_count default to 0"

    def test_old_handoff_migration_creates_checkpoint_ref_fields(self):
        """
        Test that migrate_checkpoint_chain_fields creates proper checkpoint_ref fields.

        Given: An old handoff dict without checkpoint chain fields
        When: migrate_checkpoint_chain_fields is called
        Then: All checkpoint_ref fields are added with appropriate values

        This test PASSES because migrate_checkpoint_chain_fields already works.
        """
        old_handoff = {
            "task_name": "Old task",
            "progress_percent": 25,
            "next_steps": "Continue work",
            "saved_at": "2025-02-16T12:00:00Z",
            "version": 1
            # Missing: checkpoint_id, parent_checkpoint_id, chain_id,
            #          transcript_offset, transcript_entry_count
        }

        migrated = migrate_checkpoint_chain_fields(old_handoff)

        # Verify all checkpoint_ref fields are added
        assert "checkpoint_id" in migrated, "Migration should add checkpoint_id"
        assert migrated["checkpoint_id"] != "", "checkpoint_id should be non-empty UUID"

        assert "parent_checkpoint_id" in migrated, "Migration should add parent_checkpoint_id"
        assert migrated["parent_checkpoint_id"] is None, "Old handoffs should have no parent"

        assert "chain_id" in migrated, "Migration should add chain_id"
        assert migrated["chain_id"] != "", "chain_id should be non-empty UUID"

        assert "transcript_offset" in migrated, "Migration should add transcript_offset"
        assert migrated["transcript_offset"] == 0, "Default transcript_offset should be 0"

        assert "transcript_entry_count" in migrated, "Migration should add transcript_entry_count"
        assert migrated["transcript_entry_count"] == 0, "Default transcript_entry_count should be 0"

        # Verify migration is idempotent
        migrated_again = migrate_checkpoint_chain_fields(migrated)
        assert migrated_again["checkpoint_id"] == migrated["checkpoint_id"], \
            "Migration should preserve checkpoint_id on second run"
        assert migrated_again["chain_id"] == migrated["chain_id"], \
            "Migration should preserve chain_id on second run"

    def test_checkpoint_chain_handles_mixed_old_and_new_formats(self):
        """
        Test that CheckpointChain can handle a mix of old and new formats.

        Given: A task file with both old handoffs (without checkpoint fields)
               and new handoffs (with checkpoint fields)
        When: CheckpointChain loads all checkpoints
        Then: Both formats are loaded and can create checkpoint references

        This test FAILS because old format without checkpoint_id is not loaded.
        """
        chain_id = str(uuid4())
        new_checkpoint_id = str(uuid4())

        # Create a mix of old and new format tasks
        with tempfile.TemporaryDirectory() as tmpdir:
            task_file = Path(tmpdir) / "test_terminal_tasks.json"
            task_data = {
                "terminal_id": "test_terminal",
                "tasks": {
                    "old_task_1": {
                        "id": "old_task_1",
                        "subject": "Old task 1",
                        "status": "completed",
                        "created_at": "2025-02-16T12:00:00Z",
                        "metadata": {
                            "handoff": {
                                "task_name": "Old task 1",
                                "progress_percent": 10,
                                "next_steps": "Start work",
                                "saved_at": "2025-02-16T12:00:00Z",
                                "version": 1
                                # No checkpoint_id, chain_id, etc.
                            }
                        }
                    },
                    "new_task_1": {
                        "id": "new_task_1",
                        "subject": "New task",
                        "status": "completed",
                        "created_at": "2025-02-16T12:05:00Z",
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": new_checkpoint_id,
                                "parent_checkpoint_id": None,
                                "chain_id": chain_id,
                                "task_name": "New task",
                                "progress_percent": 50,
                                "next_steps": "Continue work",
                                "saved_at": "2025-02-16T12:05:00Z",
                                "transcript_offset": 1000,
                                "transcript_entry_count": 10,
                                "version": 1
                            }
                        }
                    },
                    "old_task_2": {
                        "id": "old_task_2",
                        "subject": "Old task 2",
                        "status": "completed",
                        "created_at": "2025-02-16T12:10:00Z",
                        "metadata": {
                            "handoff": {
                                "task_name": "Old task 2",
                                "progress_percent": 25,
                                "next_steps": "More work",
                                "saved_at": "2025-02-16T12:10:00Z",
                                "version": 1
                                # No checkpoint_id, chain_id, etc.
                            }
                        }
                    }
                },
                "last_update": "2025-02-16T12:10:00Z"
            }

            task_file.write_text(json.dumps(task_data))

            # Load checkpoints via CheckpointChain
            chain = CheckpointChain(Path(tmpdir), "test_terminal")
            checkpoints = chain._load_all_checkpoints()

            # Expected: Should load both old (migrated) and new checkpoints
            # This assertion will FAIL because old format tasks are not loaded
            assert len(checkpoints) == 3, \
                "Should load 3 checkpoints (2 old format migrated + 1 new format)"

            # Verify new format checkpoint is loaded correctly
            new_checkpoint = next((c for c in checkpoints if c.checkpoint_id == new_checkpoint_id), None)
            assert new_checkpoint is not None, "New format checkpoint should be loaded"
            assert new_checkpoint.chain_id == chain_id, "New format checkpoint should preserve chain_id"
            assert new_checkpoint.transcript_offset == 1000, "New format checkpoint should preserve transcript_offset"

            # Verify old format checkpoints are migrated and loaded
            old_checkpoints = [c for c in checkpoints if c.task_id in ["old_task_1", "old_task_2"]]
            assert len(old_checkpoints) == 2, "Both old format tasks should be migrated and loaded"

            for old_cp in old_checkpoints:
                assert old_cp.checkpoint_id != "", "Old format should have checkpoint_id after migration"
                assert old_cp.chain_id != "", "Old format should have chain_id after migration"
                assert old_cp.parent_checkpoint_id is None, "Old format should have None as parent"

    def test_get_chain_with_old_format_checkpoints(self):
        """
        Test that get_chain works with old format checkpoints.

        Given: A chain containing old format checkpoints
        When: get_chain is called
        Then: All checkpoints in the chain are returned with proper refs

        This test FAILS because old format checkpoints are not loaded.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            task_file = Path(tmpdir) / "test_terminal_tasks.json"

            # Create tasks with old format (no checkpoint fields)
            task_data = {
                "terminal_id": "test_terminal",
                "tasks": {
                    "old_task_1": {
                        "id": "old_task_1",
                        "subject": "Old task 1",
                        "status": "completed",
                        "created_at": "2025-02-16T12:00:00Z",
                        "metadata": {
                            "handoff": {
                                "task_name": "Old task 1",
                                "progress_percent": 10,
                                "next_steps": "Start",
                                "saved_at": "2025-02-16T12:00:00Z",
                                "version": 1
                            }
                        }
                    },
                    "old_task_2": {
                        "id": "old_task_2",
                        "subject": "Old task 2",
                        "status": "completed",
                        "created_at": "2025-02-16T12:05:00Z",
                        "metadata": {
                            "handoff": {
                                "task_name": "Old task 2",
                                "progress_percent": 20,
                                "next_steps": "Continue",
                                "saved_at": "2025-02-16T12:05:00Z",
                                "version": 1
                            }
                        }
                    }
                },
                "last_update": "2025-02-16T12:05:00Z"
            }

            task_file.write_text(json.dumps(task_data))

            chain = CheckpointChain(Path(tmpdir), "test_terminal")

            # After migration, old checkpoints should have chain_ids
            # Try to get checkpoints using any chain_id from loaded checkpoints
            all_checkpoints = chain._load_all_checkpoints()

            # Expected: Old format checkpoints should be migrated and loaded
            # This assertion will FAIL
            assert len(all_checkpoints) == 2, "Old format checkpoints should be loaded after migration"

            # Each should have a valid chain_id (generated during migration)
            for checkpoint in all_checkpoints:
                assert checkpoint.chain_id != "", \
                    f"Checkpoint {checkpoint.task_id} should have chain_id after migration"

                # Can retrieve by chain_id
                chain_checkpoints = chain.get_chain(checkpoint.chain_id)
                assert len(chain_checkpoints) >= 1, \
                    f"Should be able to get chain by chain_id {checkpoint.chain_id}"

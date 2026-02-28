#!/usr/bin/env python3
"""Regression test for migration idempotency.

This test verifies that running migration functions multiple times
on the same data doesn't break or create duplicates.

These tests CAPTURE CURRENT BEHAVIOR before refactoring.
Run with: pytest tests/test_regression_idempotency.py -v
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

# Add handoff package to path
HANDOFF_PACKAGE = Path(__file__).parent.parent / "src"
if str(HANDOFF_PACKAGE) not in globals():
    import sys
    sys.path.insert(0, str(HANDOFF_PACKAGE))

from handoff.migrate import (
    migrate_checkpoint_chain_fields,
    migrate_handoffs,
)


class TestMigrationIdempotency:
    """Tests for migration idempotency - running migration twice should be safe."""

    def test_migrate_checkpoint_chain_fields_idempotency(self):
        """
        Test that migrate_checkpoint_chain_fields can be run multiple times safely.

        Given: An old handoff dict without checkpoint chain fields
        When: Migration is run twice on the same data
        Then: The second migration should preserve the IDs from the first run
        """
        # Arrange - Old handoff data without checkpoint fields
        old_handoff = {
            "task_name": "old task",
            "progress_percent": 10,
            "next_steps": "Continue work",
            "saved_at": "2025-02-16T12:00:00Z",
            "version": 1
        }

        # Act - Run migration twice
        first_migration = migrate_checkpoint_chain_fields(old_handoff)
        second_migration = migrate_checkpoint_chain_fields(first_migration)

        # Assert - Checkpoint IDs should be preserved on second run
        assert first_migration["checkpoint_id"] == second_migration["checkpoint_id"], \
            "Second migration should preserve checkpoint_id from first run"
        assert first_migration["chain_id"] == second_migration["chain_id"], \
            "Second migration should preserve chain_id from first run"
        assert first_migration["parent_checkpoint_id"] == second_migration["parent_checkpoint_id"], \
            "Second migration should preserve parent_checkpoint_id from first run"

    def test_migrate_handoffs_no_duplicates(self):
        """
        Test that migrate_handoffs doesn't create duplicate tasks when run twice.

        Given: A handoff directory with old handoff JSON files
        When: migrate_handoffs is run twice on the same directory
        Then: The second run should not create duplicate task entries

        This test will FAIL because the current implementation doesn't check
        for existing tasks before adding them.
        """
        # Arrange - Create temporary directories with sample handoff data
        with tempfile.TemporaryDirectory() as tmpdir:
            handoff_dir = Path(tmpdir) / "handoffs"
            task_tracker_dir = Path(tmpdir) / "task_tracker"
            handoff_dir.mkdir()
            task_tracker_dir.mkdir()

            # Create a sample handoff JSON file
            handoff_data = {
                "task_name": "test_task",
                "progress_percent": 50,
                "next_steps": "Complete the feature",
                "saved_at": "2025-02-27T10:00:00Z",
                "version": 1
            }
            handoff_file = handoff_dir / "test_handoff.json"
            handoff_file.write_text(json.dumps(handoff_data))

            terminal_id = "test_terminal"

            # Act - Run migration twice
            first_result = migrate_handoffs(
                handoff_dir=handoff_dir,
                task_tracker_dir=task_tracker_dir,
                terminal_id=terminal_id,
                dry_run=False
            )

            second_result = migrate_handoffs(
                handoff_dir=handoff_dir,
                task_tracker_dir=task_tracker_dir,
                terminal_id=terminal_id,
                dry_run=False
            )

            # Read the task file to check for duplicates
            task_file = task_tracker_dir / f"{terminal_id}_tasks.json"
            with open(task_file, encoding="utf-8") as f:
                task_data = json.load(f)

            # Assert - Second migration should be idempotent
            # Current implementation will FAIL this test because it doesn't
            # check for existing migrated tasks
            assert first_result["migrated"] == 1, \
                "First migration should migrate 1 handoff"

            # This assertion will FAIL - second migration creates duplicates
            assert second_result["migrated"] == 0, \
                "Second migration should not migrate anything (already migrated)"

            # Check that we only have one task, not duplicates
            assert len(task_data["tasks"]) == 1, \
                f"Should have exactly 1 task, but found {len(task_data['tasks'])}"

            # Verify the task ID is stable
            task_ids = list(task_data["tasks"].keys())
            assert len(task_ids) == 1, \
                f"Should have exactly 1 task ID, but found {len(task_ids)}: {task_ids}"

    def test_migrate_handoffs_preserves_existing_data(self):
        """
        Test that migrate_handoffs preserves existing task data when run twice.

        Given: A task tracker with existing migrated handoff data
        When: migrate_handoffs is run again
        Then: Existing task data should not be modified or duplicated

        This test will FAIL because the current implementation doesn't check
        for existing tasks before adding them.
        """
        # Arrange - Create temporary directories with sample handoff data
        with tempfile.TemporaryDirectory() as tmpdir:
            handoff_dir = Path(tmpdir) / "handoffs"
            task_tracker_dir = Path(tmpdir) / "task_tracker"
            handoff_dir.mkdir()
            task_tracker_dir.mkdir()

            # Create a sample handoff JSON file
            handoff_data = {
                "task_name": "test_task",
                "progress_percent": 50,
                "next_steps": "Complete the feature",
                "saved_at": "2025-02-27T10:00:00Z",
                "version": 1
            }
            handoff_file = handoff_dir / "test_handoff.json"
            handoff_file.write_text(json.dumps(handoff_data))

            terminal_id = "test_terminal"

            # Act - First migration
            first_result = migrate_handoffs(
                handoff_dir=handoff_dir,
                task_tracker_dir=task_tracker_dir,
                terminal_id=terminal_id,
                dry_run=False
            )

            # Read the task file after first migration
            task_file = task_tracker_dir / f"{terminal_id}_tasks.json"
            with open(task_file, encoding="utf-8") as f:
                first_task_data = json.load(f)

            # Get the original task details
            first_task_id = list(first_task_data["tasks"].keys())[0]
            first_task_checkpoint_id = first_task_data["tasks"][first_task_id]["metadata"]["handoff"]["checkpoint_id"]

            # Second migration
            second_result = migrate_handoffs(
                handoff_dir=handoff_dir,
                task_tracker_dir=task_tracker_dir,
                terminal_id=terminal_id,
                dry_run=False
            )

            # Read the task file after second migration
            with open(task_file, encoding="utf-8") as f:
                second_task_data = json.load(f)

            # Assert - Second migration should preserve existing data
            assert len(second_task_data["tasks"]) == 1, \
                "Should still have exactly 1 task after second migration"

            # The checkpoint_id should remain the same (not regenerated)
            second_task_id = list(second_task_data["tasks"].keys())[0]
            second_task_checkpoint_id = second_task_data["tasks"][second_task_id]["metadata"]["handoff"]["checkpoint_id"]

            assert second_task_checkpoint_id == first_task_checkpoint_id, \
                "Checkpoint ID should be preserved across migrations"

    def test_migrate_handoffs_with_multiple_files_idempotency(self):
        """
        Test idempotency with multiple handoff files.

        Given: Multiple handoff JSON files in the handoff directory
        When: migrate_handoffs is run twice
        Then: No duplicate tasks should be created

        This test will FAIL because the current implementation doesn't check
        for existing tasks before adding them.
        """
        # Arrange - Create temporary directories with multiple handoff files
        with tempfile.TemporaryDirectory() as tmpdir:
            handoff_dir = Path(tmpdir) / "handoffs"
            task_tracker_dir = Path(tmpdir) / "task_tracker"
            handoff_dir.mkdir()
            task_tracker_dir.mkdir()

            # Create multiple handoff files
            for i in range(3):
                handoff_data = {
                    "task_name": f"test_task_{i}",
                    "progress_percent": i * 25,
                    "next_steps": f"Complete feature {i}",
                    "saved_at": "2025-02-27T10:00:00Z",
                    "version": 1
                }
                handoff_file = handoff_dir / f"handoff_{i}.json"
                handoff_file.write_text(json.dumps(handoff_data))

            terminal_id = "test_terminal"

            # Act - Run migration twice
            first_result = migrate_handoffs(
                handoff_dir=handoff_dir,
                task_tracker_dir=task_tracker_dir,
                terminal_id=terminal_id,
                dry_run=False
            )

            second_result = migrate_handoffs(
                handoff_dir=handoff_dir,
                task_tracker_dir=task_tracker_dir,
                terminal_id=terminal_id,
                dry_run=False
            )

            # Read the task file
            task_file = task_tracker_dir / f"{terminal_id}_tasks.json"
            with open(task_file, encoding="utf-8") as f:
                task_data = json.load(f)

            # Assert
            assert first_result["migrated"] == 3, \
                "First migration should migrate 3 handoffs"

            # This will FAIL - second migration creates duplicates
            assert second_result["migrated"] == 0, \
                "Second migration should not migrate anything (already migrated)"

            assert len(task_data["tasks"]) == 3, \
                f"Should have exactly 3 tasks, but found {len(task_data['tasks'])}"

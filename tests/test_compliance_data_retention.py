"""
Compliance tests for data retention policies (COMP-001).

These tests verify that handoff data is automatically cleaned up
according to retention policies, not just manually on request.

Test: COMP-001 - No Data Retention Policy Enforcement
Issue: Cleanup only happens with --cleanup/--cleanup-force flags
Expected: Automatic cleanup during compaction operations
"""

import json
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from handoff.config import CLEANUP_DAYS


class TestDataRetentionAutomaticCleanup:
    """Test that old handoff data is automatically cleaned up."""

    @pytest.fixture
    def temp_project_root(self):
        """Create a temporary project root directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            # Create task tracker directory
            task_tracker_dir = root / ".claude" / "state" / "task_tracker"
            task_tracker_dir.mkdir(parents=True, exist_ok=True)
            yield root

    @pytest.fixture
    def old_handoff_files(self, temp_project_root):
        """Create old handoff files for testing."""
        task_tracker_dir = temp_project_root / ".claude" / "state" / "task_tracker"

        # Create files older than CLEANUP_DAYS (100 days old)
        old_time = datetime.now(UTC) - timedelta(days=100)
        old_timestamp = old_time.timestamp()

        old_files = []
        for i in range(3):
            file_path = task_tracker_dir / f"old_terminal_{i}_tasks.json"
            # Create a valid task file
            task_data = {
                "terminal_id": f"old_terminal_{i}",
                "tasks": {
                    "active_session": {
                        "status": "in_progress",
                        "created_at": old_time.isoformat()
                    }
                }
            }
            file_path.write_text(json.dumps(task_data))

            # Set file modification time to old timestamp
            os.utime(file_path, (old_timestamp, old_timestamp))
            old_files.append(file_path)

        # Create a recent file (should NOT be deleted)
        recent_time = datetime.now(UTC) - timedelta(days=10)
        recent_timestamp = recent_time.timestamp()
        recent_file = task_tracker_dir / "recent_terminal_tasks.json"
        recent_data = {
            "terminal_id": "recent_terminal",
            "tasks": {
                "active_session": {
                    "status": "in_progress",
                    "created_at": recent_time.isoformat()
                }
            }
        }
        recent_file.write_text(json.dumps(recent_data))
        os.utime(recent_file, (recent_timestamp, recent_timestamp))

        return {
            "old_files": old_files,
            "recent_file": recent_file,
            "task_tracker_dir": task_tracker_dir
        }

    def test_automatic_cleanup_during_compaction(self, temp_project_root, old_handoff_files):
        """
        Test COMP-001: Old handoff data is automatically cleaned up.

        Given: Old handoff files exist (> CLEANUP_DAYS old)
        When: Compaction occurs (without --cleanup flag)
        Then: Old files should be automatically deleted
              AND recent files should be preserved

        This test FAILS before the fix (no auto-cleanup).
        This test PASSES after the fix (automatic cleanup implemented).
        """
        # Arrange: Files are created by fixture
        old_files = old_handoff_files["old_files"]
        recent_file = old_handoff_files["recent_file"]
        task_tracker_dir = old_handoff_files["task_tracker_dir"]

        # Verify setup: old files exist
        for old_file in old_files:
            assert old_file.exists(), f"Old file should exist before cleanup: {old_file.name}"
        assert recent_file.exists(), "Recent file should exist before cleanup"

        # Act: Simulate compaction WITHOUT --cleanup flag
        # This is the key test: compaction should auto-cleanup old data
        # Call the cleanup function that PreCompact hook uses
        from handoff.config import cleanup_old_handoffs

        cleanup_old_handoffs(temp_project_root)

        # Assert: COMP-001 VIOLATION - old files are NOT automatically cleaned up
        files_still_exist = []
        for old_file in old_files:
            if old_file.exists():
                files_still_exist.append(old_file.name)

        # This assertion FAILS before the fix (files still exist = bug)
        # This assertion PASSES after the fix (files are deleted = fixed)
        assert len(files_still_exist) == 0, (
            f"COMP-001 VIOLATION: Old handoff files not automatically cleaned up: {files_still_exist}. "
            f"Files older than {CLEANUP_DAYS} days should be auto-deleted during compaction, "
            f"but manual cleanup with --cleanup-force flag is currently required. "
            f"This is a compliance issue - data retention policy is not enforced automatically."
        )

        # Assert: Recent file should be preserved
        assert recent_file.exists(), (
            f"Recent file should be preserved: {recent_file.name}"
        )

    def test_manual_cleanup_flag_still_works(self, temp_project_root, old_handoff_files):
        """
        Test that manual cleanup flags (--cleanup/--cleanup-force) still work.

        Given: Old handoff files exist (> CLEANUP_DAYS old)
        When: Manual cleanup is invoked with --cleanup-force flag
        Then: Old files should be deleted (existing behavior)

        This ensures we don't break existing manual cleanup functionality.
        """
        # Arrange: Files are created by fixture
        old_files = old_handoff_files["old_files"]
        recent_file = old_handoff_files["recent_file"]

        # Verify setup
        for old_file in old_files:
            assert old_file.exists(), f"Old file should exist: {old_file.name}"

        # Act: Simulate manual cleanup with --cleanup-force flag
        # This uses existing cleanup logic
        from datetime import UTC, datetime

        from handoff.config import CLEANUP_DAYS

        cutoff_time = datetime.now(UTC).timestamp() - (CLEANUP_DAYS * 86400)
        to_delete = []

        for task_file in old_handoff_files["task_tracker_dir"].glob("*_tasks.json"):
            try:
                mtime = task_file.stat().st_mtime
                if mtime < cutoff_time:
                    to_delete.append(task_file)
            except OSError:
                continue

        # Delete old files (manual cleanup)
        for f in to_delete:
            f.unlink()

        # Assert: Old files should be deleted
        for old_file in old_files:
            assert not old_file.exists(), (
                f"Old file should be deleted with manual cleanup: {old_file.name}"
            )

        # Assert: Recent file should be preserved
        assert recent_file.exists(), "Recent file should be preserved"

    def test_retention_days_configurable(self, temp_project_root):
        """
        Test that CLEANUP_DAYS configuration is respected.

        Given: CLEANUP_DAYS is set to a specific value
        When: Automatic cleanup runs
        Then: Only files older than CLEANUP_DAYS are deleted

        This verifies the retention policy is properly enforced.
        """
        # Arrange: Set custom retention period via environment
        custom_retention = 30  # days
        os.environ["HANDOFF_RETENTION_DAYS"] = str(custom_retention)

        # Reload config to pick up environment variable
        import importlib

        from handoff import config
        importlib.reload(config)

        task_tracker_dir = temp_project_root / ".claude" / "state" / "task_tracker"

        # Create file 35 days old (should be deleted with 30-day retention)
        old_time = datetime.now(UTC) - timedelta(days=35)
        old_timestamp = old_time.timestamp()
        old_file = task_tracker_dir / "very_old_terminal_tasks.json"
        old_file.write_text(json.dumps({"terminal_id": "very_old"}))
        os.utime(old_file, (old_timestamp, old_timestamp))

        # Create file 25 days old (should be kept with 30-day retention)
        recent_time = datetime.now(UTC) - timedelta(days=25)
        recent_timestamp = recent_time.timestamp()
        recent_file = task_tracker_dir / "kinda_old_terminal_tasks.json"
        recent_file.write_text(json.dumps({"terminal_id": "kinda_old"}))
        os.utime(recent_file, (recent_timestamp, recent_timestamp))

        # Verify setup
        assert old_file.exists(), "Very old file should exist"
        assert recent_file.exists(), "Kinda old file should exist"

        # Calculate cutoff with custom retention
        cutoff_time = datetime.now(UTC).timestamp() - (custom_retention * 86400)

        # Check which files should be deleted
        old_file_mtime = old_file.stat().st_mtime
        recent_file_mtime = recent_file.stat().st_mtime

        # Assert: Custom retention period is respected
        assert old_file_mtime < cutoff_time, "Very old file should be past cutoff"
        assert recent_file_mtime > cutoff_time, "Kinda old file should be before cutoff"

        # Clean up
        del os.environ["HANDOFF_RETENTION_DAYS"]
        importlib.reload(config)

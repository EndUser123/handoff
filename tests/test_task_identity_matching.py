#!/usr/bin/env python3
"""Tests for task identity matching in task_identity_manager.py.

Tests that task identity matching works correctly:
- Same task ID across messages should be grouped
- Different task IDs should be separate
- Task ID extraction from various message formats
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from uuid import uuid4

# Add handoff package to path
HANDOFF_PACKAGE = Path(__file__).parent.parent.parent / "src"
if str(HANDOFF_PACKAGE) not in globals():
    import sys
    sys.path.insert(0, str(HANDOFF_PACKAGE))

from handoff.hooks.__lib.task_identity_manager import TaskIdentityManager


class TestTaskIdentityMatching:
    """Tests for task identity matching and grouping."""

    def test_same_task_id_across_messages_grouped(self):
        """
        Test that messages with the same task ID are grouped together.

        Given: Multiple messages with the same task ID
        When: Task identity is retrieved
        Then: All messages should resolve to the same task
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Arrange
            project_root = Path(tmpdir)
            terminal_id = "test_terminal_1"
            task_name = "CWO12"

            manager = TaskIdentityManager(
                project_root=project_root,
                terminal_id=terminal_id
            )

            # Set task identity (simulating first message)
            manager.set_current_task(task_name)

            # Act: Simulate multiple messages with same task ID
            # Each message should retrieve the same task identity
            task_1 = manager.get_current_task()
            task_2 = manager.get_current_task()
            task_3 = manager.get_current_task()

            # Assert: All should return the same task name
            assert task_1 == task_name
            assert task_2 == task_name
            assert task_3 == task_name

            # Verify the session file contains the task identity
            session_data = json.loads(manager.session_file.read_text())
            assert session_data["task_name"] == task_name
            assert session_data["task_id"] == f"task_{task_name.lower()}"
            assert session_data["terminal_id"] == terminal_id

    def test_different_task_ids_separate(self):
        """
        Test that different task IDs are kept separate.

        BUG: Currently FAILS because environment variable set in set_current_task()
        causes cross-terminal bleeding. The env var TASK_NAME is global and persists
        across all terminals, causing manager_2 to retrieve manager_1's task.

        Given: Two different terminals with different task IDs
        When: Task identity is retrieved from each terminal
        Then: Each terminal should have its own task identity
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Arrange
            project_root = Path(tmpdir)

            # Create two managers for different terminals
            manager_1 = TaskIdentityManager(
                project_root=project_root,
                terminal_id="terminal_1"
            )
            manager_2 = TaskIdentityManager(
                project_root=project_root,
                terminal_id="terminal_2"
            )

            # Act: Set different tasks for each terminal
            manager_1.set_current_task("TASK_A")
            manager_2.set_current_task("TASK_B")

            # Clear environment variables to test session file isolation
            import os
            if "TASK_NAME" in os.environ:
                del os.environ["TASK_NAME"]

            # Assert: Each terminal should have its own task
            task_1 = manager_1.get_current_task()
            task_2 = manager_2.get_current_task()

            assert task_1 == "TASK_A"
            assert task_2 == "TASK_B"
            assert task_1 != task_2

            # Verify session files are terminal-scoped
            session_1_data = json.loads(manager_1.session_file.read_text())
            session_2_data = json.loads(manager_2.session_file.read_text())

            assert session_1_data["task_name"] == "TASK_A"
            assert session_2_data["task_name"] == "TASK_B"
            assert session_1_data["terminal_id"] == "terminal_1"
            assert session_2_data["terminal_id"] == "terminal_2"

    def test_task_id_extraction_from_session_file(self):
        """
        Test that task ID is correctly extracted from session file.

        BUG: Currently FAILS because environment variable from previous test
        (TASK_B) persists and takes priority over session file.

        Given: A session file exists with task metadata
        When: Task identity is retrieved (no env var set)
        Then: Task should be extracted from session file
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Arrange
            project_root = Path(tmpdir)
            terminal_id = "test_terminal_extract"
            task_name = "EXTRACT01"

            # Clear any existing environment variable
            import os
            if "TASK_NAME" in os.environ:
                del os.environ["TASK_NAME"]

            manager = TaskIdentityManager(
                project_root=project_root,
                terminal_id=terminal_id
            )

            # Pre-create session file with task data
            session_data = {
                "task_name": task_name,
                "task_id": f"task_{task_name.lower()}",
                "terminal_id": terminal_id,
                "started": "2025-02-27T12:00:00Z",
                "checksum": "abc123"
            }
            manager.session_file.parent.mkdir(parents=True, exist_ok=True)
            manager.session_file.write_text(json.dumps(session_data))

            # Act: Retrieve task (should read from session file)
            task = manager.get_current_task()

            # Assert
            assert task == task_name

    def test_task_id_extraction_from_env_var(self):
        """
        Test that task ID is correctly extracted from environment variable.

        Given: TASK_NAME environment variable is set
        When: Task identity is retrieved
        Then: Task should be extracted from environment variable
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Arrange
            project_root = Path(tmpdir)
            terminal_id = "test_terminal_env"
            task_name = "ENV_TASK_01"

            # Set environment variable
            import os
            os.environ["TASK_NAME"] = task_name

            manager = TaskIdentityManager(
                project_root=project_root,
                terminal_id=terminal_id
            )

            # Act: Retrieve task (should read from env var)
            task = manager.get_current_task()

            # Assert
            assert task == task_name

            # Cleanup
            del os.environ["TASK_NAME"]

    def test_task_id_extraction_from_compact_metadata(self):
        """
        Test that task ID is correctly extracted from compact metadata.

        Given: Compact metadata file exists with recent timestamp
        When: Task identity is retrieved (no session file or env var)
        Then: Task should be extracted from compact metadata
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Arrange
            project_root = Path(tmpdir)
            terminal_id = "test_terminal_compact"
            task_name = "COMPACT01"

            manager = TaskIdentityManager(
                project_root=project_root,
                terminal_id=terminal_id
            )

            # Pre-create compact metadata file with recent timestamp
            from datetime import UTC, datetime

            metadata_data = {
                "task_name": task_name,
                "task_id": f"task_{task_name.lower()}",
                "handoff_id": str(uuid4()),
                "timestamp": datetime.now(UTC).isoformat(),
                "version": "v1"
            }
            manager.metadata_file.parent.mkdir(parents=True, exist_ok=True)
            manager.metadata_file.write_text(json.dumps(metadata_data))

            # Act: Retrieve task (should read from compact metadata)
            task = manager.get_current_task()

            # Assert
            assert task == task_name

    def test_terminal_id_verification_prevents_cross_terminal_bleeding(self):
        """
        Test that terminal ID verification prevents task bleeding between terminals.

        BUG DISCOVERED: This test reveals TWO bugs:
        1. Session files are written to global path (P:/.claude/state/task-identity/)
           instead of project_root, causing cross-test pollution
        2. Environment variable TASK_NAME is global (not terminal-scoped), causing
           task bleeding between terminals

        Given: A session file from terminal_1 exists
        When: Task identity is retrieved from terminal_2
        Then: Task should NOT be extracted (terminal mismatch)

        Current behavior: Returns task from global state or env var
        Expected behavior: Should return None (no task for terminal_2)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Arrange
            project_root = Path(tmpdir)
            task_name = "SECURE_TASK"

            # Clear environment variable to isolate session file behavior
            import os
            if "TASK_NAME" in os.environ:
                del os.environ["TASK_NAME"]

            # Create session file for terminal_1
            manager_1 = TaskIdentityManager(
                project_root=project_root,
                terminal_id="terminal_1"
            )
            manager_1.set_current_task(task_name)

            # Verify session file was created in expected location
            # BUG: Files go to P:/.claude/state/task-identity/ not tmpdir!
            assert manager_1.session_file.parent == Path("P:/.claude/state/task-identity")
            assert manager_1.session_file.name == "session-task-terminal_1.json"

            # CRITICAL: Clear env var AFTER set_current_task to isolate session file behavior
            # This reveals the bug: env var is global, not terminal-scoped
            import os
            if "TASK_NAME" in os.environ:
                del os.environ["TASK_NAME"]

            # Act: Try to retrieve from terminal_2
            manager_2 = TaskIdentityManager(
                project_root=project_root,
                terminal_id="terminal_2"
            )
            task = manager_2.get_current_task()

            # Assert: Should not get task_1's task (terminal mismatch)
            # Since there's no task for terminal_2, should return None
            # BUG TEST: This assertion will FAIL due to cross-pollution
            assert task is None, f"Expected None but got '{task}'. Task bleeding detected!"

    def test_task_identity_grouping_by_id(self):
        """
        Test that task identities are correctly grouped by task_id.

        Given: Multiple task metadata entries with same task_id
        When: Tasks are retrieved and compared
        Then: They should be grouped together by task_id
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Arrange
            project_root = Path(tmpdir)
            terminal_id = "test_terminal_grouping"
            task_name = "GROUP_TASK"

            manager = TaskIdentityManager(
                project_root=project_root,
                terminal_id=terminal_id
            )

            # Set task (creates session file with task_id)
            manager.set_current_task(task_name)

            # Read the session file to get the task_id
            session_data = json.loads(manager.session_file.read_text())
            expected_task_id = f"task_{task_name.lower()}"

            # Assert: Verify task_id format
            assert session_data["task_id"] == expected_task_id

            # Verify that task_name can be derived from task_id
            assert session_data["task_id"] == f"task_{task_name.lower()}"
            assert session_data["task_name"] == task_name

    def test_task_identity_matching_across_recovery_sources(self):
        """
        Test that task identity matches correctly across different recovery sources.

        Given: Task identity stored in multiple sources (env, session, metadata)
        When: Task is retrieved from different sources
        Then: All sources should return the same task identity
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Arrange
            project_root = Path(tmpdir)
            terminal_id = "test_terminal_recovery"
            task_name = "RECOVERY_TASK"

            manager = TaskIdentityManager(
                project_root=project_root,
                terminal_id=terminal_id
            )

            # Store task in session file
            manager.set_current_task(task_name)

            # Also store in compact metadata
            manager.store_compact_metadata(task_name, str(uuid4()))

            # Also set environment variable
            import os
            os.environ["TASK_NAME"] = task_name

            # Act: Retrieve task (should get from highest priority source: env var)
            task_from_env = manager.get_current_task()

            # Remove env var and try again (should get from session file)
            del os.environ["TASK_NAME"]
            task_from_session = manager.get_current_task()

            # Assert: All should return the same task
            assert task_from_env == task_name
            assert task_from_session == task_name

    def test_extract_task_id_from_various_message_formats(self):
        """
        Test that task IDs can be extracted from various message formats.

        Given: Different message formats containing task identifiers
        When: Task identity is parsed and stored
        Then: Task ID should be correctly extracted and normalized
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Arrange
            project_root = Path(tmpdir)
            terminal_id = "test_terminal_formats"

            # Test various task name formats
            test_cases = [
                ("CWO12", "task_cwo12"),
                ("DEV-TASK-001", "task_dev-task-001"),
                ("feature_auth", "task_feature_auth"),
                ("BUGFIX_123", "task_bugfix_123"),
            ]

            for task_name, expected_task_id in test_cases:
                manager = TaskIdentityManager(
                    project_root=project_root,
                    terminal_id=terminal_id
                )

                # Act: Set task
                manager.set_current_task(task_name)

                # Assert: Verify task_id format
                session_data = json.loads(manager.session_file.read_text())
                assert session_data["task_name"] == task_name
                assert session_data["task_id"] == expected_task_id

                # Clean up for next test
                manager.session_file.unlink()

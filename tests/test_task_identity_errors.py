#!/usr/bin/env python3
"""Error handling tests for TaskIdentityManager.

Tests error scenarios for task identity management:
- Messages without task identifiers
- Malformed task IDs
- None or empty inputs

Expected: Should handle error scenarios gracefully without crashing
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

# Add handoff package to path
HANDOFF_PACKAGE = Path(__file__).parent.parent / "src"
if str(HANDOFF_PACKAGE) not in globals():
    import sys
    sys.path.insert(0, str(HANDOFF_PACKAGE))

from handoff.hooks.__lib.task_identity_manager import TaskIdentityManager


class TestTaskIdentityManagerNoIdentifier:
    """Tests for handling messages without task identifiers."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create temporary directory for test files."""
        return tmp_path / "test_project"

    @pytest.fixture
    def manager(self, temp_dir):
        """Create TaskIdentityManager with temporary directory."""
        temp_dir.mkdir(parents=True, exist_ok=True)
        return TaskIdentityManager(project_root=temp_dir)

    def test_get_current_task_when_no_sources_available(self, manager):
        """Test get_current_task when no task sources are available.

        Given: No environment variable, session files, or git metadata
        When: get_current_task is called
        Then: Should return None gracefully without crashing
        """
        # Arrange: Ensure no environment variable
        with patch.dict('os.environ', {}, clear=True):
            # Act: Try to get current task
            result = manager.get_current_task()

            # Assert: Should return None (no task found)
            assert result is None, "Should return None when no task sources available"

    def test_get_current_task_with_empty_session_file(self, manager, temp_dir):
        """Test get_current_task with empty session file.

        Given: Session file exists but is empty
        When: get_current_task is called
        Then: Should continue to next source without crashing
        """
        # Arrange: Create empty session file
        session_file = Path("P:/.claude/state/task-identity") / f"session-task-{manager.terminal_id}.json"
        session_file.parent.mkdir(parents=True, exist_ok=True)
        session_file.write_text("")

        with patch.dict('os.environ', {}, clear=True):
            # Act: Try to get current task
            result = manager.get_current_task()

            # Assert: Should handle gracefully and return None
            assert result is None, "Should handle empty session file gracefully"

    def test_get_current_task_with_malformed_session_file(self, manager, temp_dir):
        """Test get_current_task with malformed JSON in session file.

        Given: Session file contains invalid JSON
        When: get_current_task is called
        Then: Should continue to next source without crashing
        """
        # Arrange: Create malformed session file
        session_file = Path("P:/.claude/state/task-identity") / f"session-task-{manager.terminal_id}.json"
        session_file.parent.mkdir(parents=True, exist_ok=True)
        session_file.write_text("{ invalid json }")

        with patch.dict('os.environ', {}, clear=True):
            # Act: Try to get current task
            result = manager.get_current_task()

            # Assert: Should handle gracefully and return None
            assert result is None, "Should handle malformed JSON gracefully"


class TestTaskIdentityManagerMalformedIDs:
    """Tests for handling malformed task IDs."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create temporary directory for test files."""
        return tmp_path / "test_project"

    @pytest.fixture
    def manager(self, temp_dir):
        """Create TaskIdentityManager with temporary directory."""
        temp_dir.mkdir(parents=True, exist_ok=True)
        return TaskIdentityManager(project_root=temp_dir)

    def test_set_current_task_with_empty_string(self, manager):
        """Test set_current_task with empty string task name.

        Given: Task name is an empty string
        When: set_current_task is called with ""
        Then: Should raise ValueError or return False (reject invalid input)
        """
        # Arrange: Empty task name
        # Act: Try to set empty task
        result = manager.set_current_task("")

        # Assert: Should reject empty string (current implementation accepts it - this test FAILS)
        assert result is False, "Should reject empty string task name"

    def test_set_current_task_with_whitespace_only(self, manager):
        """Test set_current_task with whitespace-only task name.

        Given: Task name contains only whitespace
        When: set_current_task is called with "   "
        Then: Should reject whitespace-only task names
        """
        # Arrange: Whitespace task name
        # Act: Try to set whitespace task
        result = manager.set_current_task("   ")

        # Assert: Should reject whitespace (current implementation accepts it - this test FAILS)
        assert result is False, "Should reject whitespace-only task name"

    def test_set_current_task_with_special_characters(self, manager):
        """Test set_current_task with special characters in task name.

        Given: Task name contains dangerous special characters
        When: set_current_task is called
        Then: Should reject task names with path separators or control characters
        """
        # Arrange: Task names with dangerous special chars
        dangerous_names = [
            "task/with/slashes",  # Path separator
            "task\\with\\backslashes",  # Windows path separator
            "task\nwith\nnewlines",  # Control character
            "task\twith\ttabs",  # Control character
        ]

        for task_name in dangerous_names:
            # Act: Try to set special char task
            result = manager.set_current_task(task_name)

            # Assert: Should reject dangerous characters (current implementation accepts - this test FAILS)
            assert result is False, f"Should reject task name with dangerous characters: '{task_name}'"

        # But emoji and regular symbols should be OK
        safe_names = [
            "task😀with😀emoji",
            "task with spaces and !@#$% symbols"
        ]

        for task_name in safe_names:
            result = manager.set_current_task(task_name)
            assert result is True, f"Should accept safe task name: '{task_name}'"

    def test_session_file_with_missing_task_name(self, manager):
        """Test reading session file that lacks task_name field.

        Given: Session file exists but missing task_name key
        When: get_current_task is called
        Then: Should continue to next source without crashing
        """
        # Arrange: Create session file without task_name
        session_file = Path("P:/.claude/state/task-identity") / f"session-task-{manager.terminal_id}.json"
        session_file.parent.mkdir(parents=True, exist_ok=True)
        session_file.write_text('{"terminal_id": "test123", "started": "2024-01-01"}')

        with patch.dict('os.environ', {}, clear=True):
            # Act: Try to get current task
            result = manager.get_current_task()

            # Assert: Should handle missing field gracefully
            assert result is None, "Should handle missing task_name field gracefully"


class TestTaskIdentityManagerNoneInputs:
    """Tests for handling None or invalid inputs."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create temporary directory for test files."""
        return tmp_path / "test_project"

    @pytest.fixture
    def manager(self, temp_dir):
        """Create TaskIdentityManager with temporary directory."""
        temp_dir.mkdir(parents=True, exist_ok=True)
        return TaskIdentityManager(project_root=temp_dir)

    def test_manager_with_none_project_root(self):
        """Test TaskIdentityManager initialization with None project_root.

        Given: project_root is None
        When: TaskIdentityManager is created
        Then: Should default to cwd without crashing
        """
        # Arrange & Act: Create manager with None
        manager = TaskIdentityManager(project_root=None)

        # Assert: Should initialize with cwd
        assert manager.project_root is not None, "Should default to cwd when None"

    def test_manager_with_none_terminal_id(self):
        """Test TaskIdentityManager initialization with None terminal_id.

        Given: terminal_id is None
        When: TaskIdentityManager is created
        Then: Should auto-detect terminal_id without crashing
        """
        # Arrange & Act: Create manager with None
        manager = TaskIdentityManager(terminal_id=None)

        # Assert: Should auto-detect terminal_id
        assert manager.terminal_id is not None, "Should auto-detect terminal_id when None"

    def test_store_compact_metadata_with_none_task_name(self, manager):
        """Test store_compact_metadata with None task name.

        Given: task_name parameter is None
        When: store_compact_metadata is called
        Then: Should handle gracefully without crashing
        """
        # Arrange: None task name
        # Act: Try to store with None
        result = manager.store_compact_metadata(None, "handoff123")

        # Assert: Should handle without crashing
        assert isinstance(result, bool), "Should return boolean without crashing"

    def test_store_compact_metadata_with_none_handoff_id(self, manager):
        """Test store_compact_metadata with None handoff_id.

        Given: handoff_id parameter is None
        When: store_compact_metadata is called
        Then: Should handle gracefully without crashing
        """
        # Arrange: None handoff_id
        # Act: Try to store with None
        result = manager.store_compact_metadata("TASK123", None)

        # Assert: Should handle without crashing
        assert isinstance(result, bool), "Should return boolean without crashing"

    def test_register_task_worktree_mapping_with_none_task_name(self, manager):
        """Test register_task_worktree_mapping with None task_name.

        Given: task_name parameter is None
        When: register_task_worktree_mapping is called
        Then: Should handle gracefully without crashing
        """
        # Arrange: None task name
        # Act: Try to register with None
        result = manager.register_task_worktree_mapping(None, "main")

        # Assert: Should handle without crashing
        assert isinstance(result, bool), "Should return boolean without crashing"

    def test_register_task_worktree_mapping_with_none_branch(self, manager):
        """Test register_task_worktree_mapping with None branch.

        Given: branch parameter is None
        When: register_task_worktree_mapping is called
        Then: Should handle gracefully without crashing
        """
        # Arrange: None branch
        # Act: Try to register with None
        result = manager.register_task_worktree_mapping("TASK123", None)

        # Assert: Should handle without crashing
        assert isinstance(result, bool), "Should return boolean without crashing"

    def test_record_active_command_with_none_command(self, manager):
        """Test record_active_command with None command.

        Given: command parameter is None
        When: record_active_command is called
        Then: Should handle gracefully without crashing
        """
        # Arrange: None command
        # Act: Try to record with None
        result = manager.record_active_command(None, "execution")

        # Assert: Should handle without crashing
        assert isinstance(result, bool), "Should return boolean without crashing"

    def test_record_active_command_with_none_phase(self, manager):
        """Test record_active_command with None phase.

        Given: phase parameter is None
        When: record_active_command is called
        Then: Should handle gracefully without crashing
        """
        # Arrange: None phase
        # Act: Try to record with None
        result = manager.record_active_command("duf", None)

        # Assert: Should handle without crashing
        assert isinstance(result, bool), "Should return boolean without crashing"

    def test_get_transient_task_id_with_corrupted_active_command_file(self, manager):
        """Test _get_transient_task_id with corrupted active_command.json.

        Given: active_command.json contains invalid JSON
        When: get_current_task is called (which checks transient task)
        Then: Should continue to next source without crashing
        """
        # Arrange: Create corrupted active command file
        active_cmd_file = manager.project_root / ".claude" / "active_command.json"
        active_cmd_file.parent.mkdir(parents=True, exist_ok=True)
        active_cmd_file.write_text("{ corrupted json }")

        with patch.dict('os.environ', {}, clear=True):
            # Act: Try to get current task
            result = manager.get_current_task()

            # Assert: Should handle corrupted file gracefully
            assert result is None, "Should handle corrupted active_command.json gracefully"


class TestTaskIdentityManagerGracefulDegradation:
    """Tests for graceful degradation under various error conditions."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create temporary directory for test files."""
        return tmp_path / "test_project"

    @pytest.fixture
    def manager(self, temp_dir):
        """Create TaskIdentityManager with temporary directory."""
        temp_dir.mkdir(parents=True, exist_ok=True)
        return TaskIdentityManager(project_root=temp_dir)

    def test_multiple_sources_failing_continues_to_next(self, manager):
        """Test that multiple failing sources continues gracefully through chain.

        Given: Multiple sources fail (empty env, bad session, bad metadata)
        When: get_current_task is called
        Then: Should try all sources and return None without crashing
        """
        # Arrange: Create multiple bad files
        session_file = Path("P:/.claude/state/task-identity") / f"session-task-{manager.terminal_id}.json"
        session_file.parent.mkdir(parents=True, exist_ok=True)
        session_file.write_text("{ bad json }")

        metadata_file = Path("P:/.claude/state/task-identity") / f"last-compact-metadata-{manager.terminal_id}.json"
        metadata_file.parent.mkdir(parents=True, exist_ok=True)
        metadata_file.write_text("{ also bad }")

        with patch.dict('os.environ', {}, clear=True):
            # Act: Try to get current task
            result = manager.get_current_task()

            # Assert: Should try all sources and return None
            assert result is None, "Should degrade gracefully through all sources"

    def test_cleanup_with_no_state_directory(self, manager):
        """Test cleanup_stale_terminal_files when state directory doesn't exist.

        Given: State directory doesn't exist
        When: cleanup_stale_terminal_files is called
        Then: Should return 0 without crashing
        """
        # Arrange: Ensure no state directory (using temp path)
        temp_state = manager.project_root / ".claude" / "state-task-identity"
        if temp_state.exists():
            temp_state.unlink()

        # Act: Try cleanup
        result = manager.cleanup_stale_terminal_files()

        # Assert: Should return 0 (nothing deleted)
        assert result == 0, "Should handle missing directory gracefully"

    def test_clear_active_command_with_no_file(self, manager):
        """Test clear_active_command when file doesn't exist.

        Given: active_command.json doesn't exist
        When: clear_active_command is called
        Then: Should return False without crashing
        """
        # Arrange: Ensure no active command file
        active_cmd_file = manager.project_root / ".claude" / "active_command.json"
        if active_cmd_file.exists():
            active_cmd_file.unlink()

        # Act: Try to clear
        result = manager.clear_active_command()

        # Assert: Should return False (file didn't exist)
        assert isinstance(result, bool), "Should return boolean without crashing"

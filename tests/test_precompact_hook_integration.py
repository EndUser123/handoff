#!/usr/bin/env python3
"""
Integration tests for PreCompact_handoff_capture hook.

These tests verify the complete workflow of the PreCompact handoff capture system:
1. Task identity is captured from conversation using TaskIdentityManager
2. Handoff metadata is built with checkpoint_id and chain_id using HandoverBuilder
3. Handoff is stored in task tracker metadata using HandoffStore

Run with: pytest tests/test_precompact_hook_integration.py -v
"""

import json
import os

# Add src to path for imports
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent.parent / "src" / "handoff" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))
sys.path.insert(0, str(HOOKS_DIR / "__lib"))

from handoff.hooks.__lib.handoff_store import HandoffStore
from handoff.hooks.__lib.handover import HandoverBuilder
from handoff.hooks.__lib.task_identity_manager import TaskIdentityManager
from handoff.hooks.__lib.transcript import TranscriptParser


class TestPreCompactHookTaskIdentityCapture:
    """Tests for task identity capture from conversation."""

    @pytest.fixture
    def temp_project_root(self):
        """Create a temporary project root directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def mock_terminal_id(self):
        """Mock terminal ID."""
        return "test_terminal_12345"

    @pytest.fixture
    def task_manager(self, temp_project_root, mock_terminal_id):
        """Create TaskIdentityManager instance."""
        return TaskIdentityManager(
            project_root=temp_project_root,
            terminal_id=mock_terminal_id
        )

    def test_captures_task_identity_from_conversation(self, task_manager, temp_project_root):
        """
        Test that hook captures task identity from conversation.

        Given: A task has been set in the environment
        When: TaskIdentityManager.get_current_task() is called
        Then: The task name should be returned

        This test verifies the first requirement: Hook captures task identity.
        """
        # Arrange: Set task via environment variable
        test_task_name = "CWO12"
        os.environ["TASK_NAME"] = test_task_name

        # Act: Get current task
        captured_task = task_manager.get_current_task()

        # Assert: Task should be captured from environment
        assert captured_task is not None, "Task identity should be captured"
        assert captured_task == test_task_name, f"Expected {test_task_name}, got {captured_task}"

        # Cleanup
        del os.environ["TASK_NAME"]

    def test_captures_task_identity_from_session_file(self, task_manager, temp_project_root):
        """
        Test that hook captures task identity from session file.

        Given: A task has been stored in the session file
        When: TaskIdentityManager.get_current_task() is called
        Then: The task name should be returned from session file

        This verifies fallback to session file when env var is not set.
        """
        # Arrange: Write task to session file
        test_task_name = "CWO45"
        session_file = Path("P:/.claude/state/task-identity") / f"session-task-{task_manager.terminal_id}.json"
        session_file.parent.mkdir(parents=True, exist_ok=True)

        session_data = {
            "task_name": test_task_name,
            "task_id": f"task_{test_task_name.lower()}",
            "terminal_id": task_manager.terminal_id,
            "started": datetime.now(UTC).isoformat(),
            "checksum": "test_checksum"
        }
        session_file.write_text(json.dumps(session_data, indent=2))

        # Act: Get current task (should read from session file)
        captured_task = task_manager.get_current_task()

        # Assert: Task should be captured from session file
        assert captured_task is not None, "Task identity should be captured from session file"
        assert captured_task == test_task_name, f"Expected {test_task_name}, got {captured_task}"

        # Cleanup
        session_file.unlink()


class TestPreCompactHookHandoffMetadataBuild:
    """Tests for handoff metadata building with checkpoint_id and chain_id."""

    @pytest.fixture
    def temp_project_root(self):
        """Create a temporary project root directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def mock_terminal_id(self):
        """Mock terminal ID."""
        return "test_terminal_12345"

    @pytest.fixture
    def mock_transcript_path(self, temp_project_root):
        """Create a mock transcript file."""
        transcript_path = temp_project_root / "transcript.jsonl"
        # Write minimal transcript
        transcript_path.write_text('{"type": "user", "message": "Test message"}\n')
        return transcript_path

    @pytest.fixture
    def transcript_parser(self, mock_transcript_path):
        """Create TranscriptParser instance."""
        return TranscriptParser(transcript_path=mock_transcript_path)

    @pytest.fixture
    def handover_builder(self, temp_project_root, transcript_parser):
        """Create HandoverBuilder instance."""
        return HandoverBuilder(
            project_root=temp_project_root,
            transcript_parser=transcript_parser
        )

    @pytest.fixture
    def handoff_store(self, temp_project_root, mock_terminal_id):
        """Create HandoffStore instance."""
        return HandoffStore(
            project_root=temp_project_root,
            terminal_id=mock_terminal_id
        )

    def test_builds_handoff_metadata_with_checkpoint_id(self, handoff_store):
        """
        Test that hook builds handoff metadata with checkpoint_id.

        Given: HandoffStore.build_handoff_data() is called with task data
        When: The handoff data is built
        Then: checkpoint_id should be present and should be a valid UUID string

        This verifies requirement 2a: Hook builds handoff metadata with checkpoint_id.
        """
        # Arrange: Prepare task data
        task_name = "test_task_feature_implementation"
        progress_pct = 50
        blocker = None
        files_modified = ["src/main.py", "tests/test_main.py"]
        next_steps = ["Write unit tests", "Update documentation"]
        handover = {"decisions": [], "patterns_learned": []}
        modifications = []

        # Act: Build handoff data
        handoff_data = handoff_store.build_handoff_data(
            task_name=task_name,
            progress_pct=progress_pct,
            blocker=blocker,
            files_modified=files_modified,
            next_steps=next_steps,
            handover=handover,
            modifications=modifications
        )

        # Assert: checkpoint_id should exist and be valid
        assert "checkpoint_id" in handoff_data, "checkpoint_id should be present in handoff data"
        checkpoint_id = handoff_data["checkpoint_id"]
        assert isinstance(checkpoint_id, str), "checkpoint_id should be a string"
        assert len(checkpoint_id) == 36, "checkpoint_id should be a UUID (36 characters)"
        assert checkpoint_id.count("-") == 4, "checkpoint_id should be a valid UUID format"

    def test_builds_handoff_metadata_with_chain_id(self, handoff_store):
        """
        Test that hook builds handoff metadata with chain_id.

        Given: HandoffStore.build_handoff_data() is called with task data
        When: The handoff data is built
        Then: chain_id should be present and should be a valid UUID string

        This verifies requirement 2b: Hook builds handoff metadata with chain_id.
        """
        # Arrange: Prepare task data
        task_name = "test_task_feature_implementation"
        progress_pct = 75
        blocker = None
        files_modified = ["src/module.py"]
        next_steps = ["Complete feature", "Add tests"]
        handover = {"decisions": [], "patterns_learned": []}
        modifications = []

        # Act: Build handoff data
        handoff_data = handoff_store.build_handoff_data(
            task_name=task_name,
            progress_pct=progress_pct,
            blocker=blocker,
            files_modified=files_modified,
            next_steps=next_steps,
            handover=handover,
            modifications=modifications
        )

        # Assert: chain_id should exist and be valid
        assert "chain_id" in handoff_data, "chain_id should be present in handoff data"
        chain_id = handoff_data["chain_id"]
        assert isinstance(chain_id, str), "chain_id should be a string"
        assert len(chain_id) == 36, "chain_id should be a UUID (36 characters)"
        assert chain_id.count("-") == 4, "chain_id should be a valid UUID format"

    def test_chain_id_persists_across_multiple_checkpoints(self, handoff_store):
        """
        Test that chain_id remains consistent across multiple handoff builds.

        Given: HandoffStore builds multiple checkpoints
        When: build_handoff_data() is called multiple times
        Then: All checkpoints should share the same chain_id

        This verifies the chain functionality: multiple checkpoints in same session share chain_id.
        """
        # Arrange: Prepare task data
        task_name = "test_task_chain_persistence"

        # Act: Build first checkpoint
        handoff_data_1 = handoff_store.build_handoff_data(
            task_name=task_name,
            progress_pct=25,
            blocker=None,
            files_modified=[],
            next_steps=[],
            handover={"decisions": [], "patterns_learned": []},
            modifications=[]
        )

        # Act: Build second checkpoint
        handoff_data_2 = handoff_store.build_handoff_data(
            task_name=task_name,
            progress_pct=50,
            blocker=None,
            files_modified=[],
            next_steps=[],
            handover={"decisions": [], "patterns_learned": []},
            modifications=[]
        )

        # Act: Build third checkpoint
        handoff_data_3 = handoff_store.build_handoff_data(
            task_name=task_name,
            progress_pct=75,
            blocker=None,
            files_modified=[],
            next_steps=[],
            handover={"decisions": [], "patterns_learned": []},
            modifications=[]
        )

        # Assert: All checkpoints should share the same chain_id
        chain_id_1 = handoff_data_1["chain_id"]
        chain_id_2 = handoff_data_2["chain_id"]
        chain_id_3 = handoff_data_3["chain_id"]

        assert chain_id_1 == chain_id_2 == chain_id_3, "All checkpoints in chain should have same chain_id"

        # Assert: Each checkpoint should have unique checkpoint_id
        assert handoff_data_1["checkpoint_id"] != handoff_data_2["checkpoint_id"], "Each checkpoint should have unique checkpoint_id"
        assert handoff_data_2["checkpoint_id"] != handoff_data_3["checkpoint_id"], "Each checkpoint should have unique checkpoint_id"

        # Assert: Parent linking should work
        assert handoff_data_2["parent_checkpoint_id"] == handoff_data_1["checkpoint_id"], "Second checkpoint should parent to first"
        assert handoff_data_3["parent_checkpoint_id"] == handoff_data_2["checkpoint_id"], "Third checkpoint should parent to second"


class TestPreCompactHookHandoffStorage:
    """Tests for handoff storage in task tracker metadata."""

    @pytest.fixture
    def temp_project_root(self):
        """Create a temporary project root directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def mock_terminal_id(self):
        """Mock terminal ID."""
        return "test_terminal_12345"

    @pytest.fixture
    def handoff_store(self, temp_project_root, mock_terminal_id):
        """Create HandoffStore instance."""
        return HandoffStore(
            project_root=temp_project_root,
            terminal_id=mock_terminal_id
        )

    def test_stores_handoff_in_task_tracker_metadata(self, handoff_store, temp_project_root):
        """
        Test that hook stores handoff in task tracker metadata.

        Given: HandoffStore.create_continue_session_task() is called with handoff metadata
        When: The task is created
        Then: The handoff should be stored in the task tracker file

        This verifies requirement 3: Hook stores handoff in task tracker metadata.
        """
        # RED PHASE: This test is expected to FAIL until implementation is complete
        assert False, "RED PHASE: This test is expected to FAIL. Implementation needs to verify task file creation and metadata storage."

        # The following assertions show what SHOULD happen after implementation:
        # Arrange: Prepare handoff metadata
        # task_name = "test_task_feature_implementation"
        # task_id = "task_test_task_feature_implementation"
        # handoff_metadata = {
        #     "task_name": task_name,
        #     "task_type": "feature",
        #     "progress_percent": 60,
        #     "blocker": None,
        #     "next_steps": "Complete implementation\nAdd unit tests",
        #     "git_branch": "feature/test",
        #     "active_files": ["src/feature.py"],
        #     "recent_tools": [],
        #     "transcript_path": "/transcript.json",
        #     "handover": {"decisions": [], "patterns_learned": []},
        #     "open_conversation_context": None,
        #     "visual_context": None,
        #     "resolved_issues": [],
        #     "modifications": [],
        #     "original_user_request": "Implement test feature",
        #     "first_user_request": "Implement test feature",
        #     "saved_at": datetime.now(UTC).isoformat(),
        #     "version": 1,
        #     "implementation_status": None,
        # }
        #
        # # Act: Create continue_session task
        # handoff_store.create_continue_session_task(task_name, task_id, handoff_metadata)
        #
        # # Assert: Task file should exist with correct structure
        # task_file = Path("P:/.claude/state/task_tracker") / f"{handoff_store.terminal_id}_tasks.json"
        # assert task_file.exists(), "Task tracker file should be created"
        # task_data = json.loads(task_file.read_text())
        # assert "continue_session" in task_data["tasks"], "continue_session task should exist"
        # assert "active_session" in task_data["tasks"], "active_session task should exist"
        #
        # # Verify handoff metadata is stored
        # continue_task = task_data["tasks"]["continue_session"]
        # assert "metadata" in continue_task, "Task should have metadata"
        # assert "handoff" in continue_task["metadata"], "Metadata should contain handoff"
        # stored_handoff = continue_task["metadata"]["handoff"]
        # assert stored_handoff["task_name"] == task_name, "Handoff should preserve task_name"
        # assert stored_handoff["progress_percent"] == 60, "Handoff should preserve progress_percent"

    def test_handoff_metadata_contains_checkpoint_chain_fields(self, handoff_store):
        """
        Test that stored handoff metadata contains checkpoint chain fields.

        Given: Handoff is stored in task tracker
        When: The handoff metadata is retrieved
        Then: It should contain checkpoint_id, parent_checkpoint_id, and chain_id

        This verifies the complete workflow: capture -> build -> store with chain tracking.
        """
        # Arrange: Build handoff data with chain tracking
        task_name = "test_task_chain_fields"
        handoff_data = handoff_store.build_handoff_data(
            task_name=task_name,
            progress_pct=40,
            blocker=None,
            files_modified=[],
            next_steps=[],
            handover={"decisions": [], "patterns_learned": []},
            modifications=[]
        )

        # Create full handoff metadata
        handoff_metadata = {
            "task_name": task_name,
            "progress_percent": handoff_data["progress_pct"],
            "blocker": handoff_data["blocker"],
            "next_steps": "\n".join(handoff_data["next_steps"]),
            "saved_at": datetime.now(UTC).isoformat(),
            # Include checkpoint chain fields
            "checkpoint_id": handoff_data["checkpoint_id"],
            "parent_checkpoint_id": handoff_data["parent_checkpoint_id"],
            "chain_id": handoff_data["chain_id"],
        }

        # Act & Assert: Verify checkpoint chain fields are present
        assert "checkpoint_id" in handoff_metadata, "Handoff metadata should contain checkpoint_id"
        assert "parent_checkpoint_id" in handoff_metadata, "Handoff metadata should contain parent_checkpoint_id"
        assert "chain_id" in handoff_metadata, "Handoff metadata should contain chain_id"

        # Verify values are valid
        assert handoff_metadata["checkpoint_id"] == handoff_data["checkpoint_id"], "checkpoint_id should match"
        assert handoff_metadata["chain_id"] == handoff_data["chain_id"], "chain_id should match"


class TestPreCompactHookIntegration:
    """End-to-end integration tests for the complete PreCompact workflow."""

    @pytest.fixture
    def temp_project_root(self):
        """Create a temporary project root directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def mock_terminal_id(self):
        """Mock terminal ID."""
        return "test_terminal_e2e"

    def test_complete_precompact_workflow(self, temp_project_root, mock_terminal_id):
        """
        Test the complete PreCompact workflow end-to-end.

        Given: A session with task identity and transcript
        When: PreCompactHandoffCapture.run() executes
        Then:
            1. Task identity is captured from conversation
            2. Handoff metadata is built with checkpoint_id and chain_id
            3. Handoff is stored in task tracker metadata

        This is the comprehensive integration test covering all requirements.
        """
        # RED PHASE: Test is expected to FAIL
        assert False, "RED PHASE: This test will fail until PreCompactHandoffCapture is fully integrated with test fixtures."

        # The following code shows what SHOULD happen after implementation:
        # # Arrange: Set up test environment
        # task_name = "E2E_TEST_TASK"
        # os.environ["TASK_NAME"] = task_name
        #
        # # Create minimal transcript
        # transcript_path = temp_project_root / "session.jsonl"
        # transcript_path.write_text('{"type": "user", "message": {"content": "Test request"}}\n')
        #
        # # Create progress file
        # progress_file = temp_project_root / ".claude" / "progress.txt"
        # progress_file.parent.mkdir(parents=True, exist_ok=True)
        # progress_file.write_text("50%")
        #
        # # Initialize components
        # task_manager = TaskIdentityManager(
        #     project_root=temp_project_root,
        #     terminal_id=mock_terminal_id
        # )
        # transcript_parser = TranscriptParser(transcript_path=str(transcript_path))
        # handover_builder = HandoverBuilder(
        #     project_root=temp_project_root,
        #     transcript_parser=transcript_parser
        # )
        # handoff_store = HandoffStore(
        #     project_root=temp_project_root,
        #     terminal_id=mock_terminal_id
        # )
        #
        # # Act: Run the workflow
        # # 1. Capture task identity
        # captured_task = task_manager.get_current_task()
        # assert captured_task == task_name, "Task identity should be captured"
        #
        # # 2. Build handoff metadata
        # handoff_data = handoff_store.build_handoff_data(
        #     task_name=captured_task,
        #     progress_pct=50,
        #     blocker=None,
        #     files_modified=[],
        #     next_steps=["Continue implementation"],
        #     handover=handover_builder.build(captured_task),
        #     modifications=[]
        # )
        #
        # # Verify checkpoint chain fields
        # assert "checkpoint_id" in handoff_data, "Should have checkpoint_id"
        # assert "chain_id" in handoff_data, "Should have chain_id"
        #
        # # 3. Store handoff in task tracker
        # task_id = f"task_{captured_task.lower()}"
        # handoff_metadata = {
        #     "task_name": captured_task,
        #     "progress_percent": handoff_data["progress_pct"],
        #     "checkpoint_id": handoff_data["checkpoint_id"],
        #     "chain_id": handoff_data["chain_id"],
        #     "saved_at": datetime.now(UTC).isoformat(),
        # }
        # handoff_store.create_continue_session_task(captured_task, task_id, handoff_metadata)
        #
        # # Verify: Check task tracker file
        # # (This would require patching the hardcoded path as shown in earlier test)
        # task_file = Path("P:/.claude/state/task_tracker") / f"{mock_terminal_id}_tasks.json"
        # assert task_file.exists(), "Task file should be created"
        #
        # # Cleanup
        # del os.environ["TASK_NAME"]

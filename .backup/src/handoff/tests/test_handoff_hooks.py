#!/usr/bin/env python3
"""Unit tests for handoff capture and restore hooks."""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

# Add paths
HOOKS_DIR = Path(__file__).parent.parent
HANDOFF_PACKAGE = Path("P:/packages/handoff/src")

sys.path.insert(0, str(HOOKS_DIR))
if HANDOFF_PACKAGE.exists():
    sys.path.insert(0, str(HANDOFF_PACKAGE))


class TestPreCompactHandoffCapture(unittest.TestCase):
    """Test PreCompact_handoff_capture.py functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.hook_path = HOOKS_DIR / "PreCompact_handoff_capture.py"

    def test_hook_file_exists(self):
        """Test that capture hook file exists."""
        self.assertTrue(self.hook_path.exists(), "PreCompact_handoff_capture.py should exist")

    def test_hook_syntax_valid(self):
        """Test that capture hook has valid Python syntax."""
        import py_compile
        try:
            py_compile.compile(str(self.hook_path), doraise=True)
        except py_compile.PyCompileError as e:
            self.fail(f"Capture hook has syntax error: {e}")

    def test_session_type_detection_planning(self):
        """Test session type detection for planning sessions."""
        # Import after path setup
        from PreCompact_handoff_capture import detect_session_type

        user_message = "We need to design the architecture for the authentication system"
        active_files = ["plan-20260304-auth.md", "docs/plans/architecture.md"]

        session_type, emoji = detect_session_type(user_message, active_files)

        self.assertEqual(session_type, "planning")
        self.assertEqual(emoji, "📋")

    def test_session_type_detection_debug(self):
        """Test session type detection for debug sessions."""
        from PreCompact_handoff_capture import detect_session_type

        user_message = "We need to fix the authentication bug"
        active_files = ["error.log", "traceback.txt", "src/auth.py"]

        session_type, emoji = detect_session_type(user_message, active_files)

        self.assertEqual(session_type, "debug")
        self.assertEqual(emoji, "🐛")

    def test_session_type_detection_feature(self):
        """Test session type detection for feature development."""
        from PreCompact_handoff_capture import detect_session_type

        user_message = "Let's implement the new user authentication feature"
        active_files = ["src/auth.py", "src/user.py"]

        session_type, emoji = detect_session_type(user_message, active_files)

        self.assertEqual(session_type, "feature")
        self.assertEqual(emoji, "✨")

    def test_planning_blocker_detection(self):
        """Test planning session blocker detection."""
        from PreCompact_handoff_capture import detect_planning_session

        # Test with /plan-workflow command
        user_message = "/plan-workflow build Implement user authentication"
        active_files = []

        blocker = detect_planning_session(user_message, active_files)

        self.assertIsNotNone(blocker)
        self.assertEqual(blocker["type"], "awaiting_approval")
        self.assertIn("/plan-workflow", blocker["invoked_command"])

    def test_planning_blocker_with_plan_files(self):
        """Test planning blocker detection with plan files."""
        from PreCompact_handoff_capture import detect_planning_session

        user_message = "Let's create an architecture for the system"
        active_files = ["plan-20260304-architecture.md"]

        blocker = detect_planning_session(user_message, active_files)

        self.assertIsNotNone(blocker)
        self.assertEqual(blocker["type"], "awaiting_approval")

    def test_no_blocker_for_regular_session(self):
        """Test that regular sessions don't get blockers."""
        from PreCompact_handoff_capture import detect_planning_session

        user_message = "Let's fix the authentication bug"
        active_files = ["error.log"]

        blocker = detect_planning_session(user_message, active_files)

        self.assertIsNone(blocker)

    @patch('PreCompact_handoff_capture.HandoffStore')
    def test_capture_hook_with_mock_data(self, mock_store):
        """Test capture hook processes input correctly."""
        # Mock HandoffStore methods
        mock_store_instance = Mock()
        mock_store.return_value = mock_store_instance
        mock_store_instance.build_handoff_data.return_value = {
            "checkpoint_id": "test-123",
            "session_type": "debug"
        }
        mock_store_instance.create_continue_session_task.return_value = None

        # Prepare test input
        test_input = {
            "sessionId": "test-session-123",
            "terminalId": "test_terminal",
            "transcript": "User: Fix the auth bug\n\nLet's investigate.",
            "toolUses": [
                {"input": {"file_path": "P:/src/auth.py"}},
                {"input": {"file_path": "P:/error.log"}}
            ]
        }

        # Simulate hook execution
        import subprocess
        result = subprocess.run(
            [sys.executable, str(self.hook_path)],
            input=json.dumps(test_input).encode(),
            capture_output=True,
            timeout=10,
            cwd=str(HOOKS_DIR)
        )

        # Check output
        self.assertEqual(result.returncode, 0, "Hook should exit successfully")

        output = json.loads(result.stdout.decode())
        self.assertEqual(output["decision"], "allow")
        self.assertIn("Captured handoff", output["reason"])


class TestSessionStartHandoffRestore(unittest.TestCase):
    """Test SessionStart_handoff_restore.py functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.hook_path = HOOKS_DIR / "SessionStart_handoff_restore.py"
        self.task_tracker_dir = HOOKS_DIR.parent / "state" / "task_tracker"

    def test_hook_file_exists(self):
        """Test that restore hook file exists."""
        self.assertTrue(self.hook_path.exists(), "SessionStart_handoff_restore.py should exist")

    def test_hook_syntax_valid(self):
        """Test that restore hook has valid Python syntax."""
        import py_compile
        try:
            py_compile.compile(str(self.hook_path), doraise=True)
        except py_compile.PyCompileError as e:
            self.fail(f"Restore hook has syntax error: {e}")

    def test_restoration_formatting(self):
        """Test restoration message formatting."""
        from SessionStart_handoff_restore import format_restoration_message

        handoff_data = {
            "session_info": {
                "session_type": "debug",
                "emoji": "🐛",
                "captured_at": "2026-03-07T12:00:00Z"
            },
            "task": {
                "name": "Fix auth bug",
                "user_message": "Fix the authentication bug in login system",
                "progress_pct": 50,
                "blocker": None
            },
            "context": {
                "active_files": ["src/auth.py", "error.log"],
                "pending_operations": [
                    {"type": "edit", "target": "src/auth.py", "status": "edited but not verified"}
                ],
                "visual_context": []
            },
            "continuation": {
                "next_steps": ["Add unit tests", "Verify fix"]
            }
        }

        message = format_restoration_message(handoff_data)

        self.assertIn("WHERE WE ARE IN THE TASK", message)
        self.assertIn("🐛 debug", message)
        self.assertIn("Fix auth bug", message)
        self.assertIn("50%", message)
        self.assertIn("src/auth.py", message)
        self.assertIn("edited but not verified", message)

    def test_restoration_with_planning_blocker(self):
        """Test restoration message with planning blocker."""
        from SessionStart_handoff_restore import format_restoration_message

        handoff_data = {
            "session_info": {
                "session_type": "planning",
                "emoji": "📋"
            },
            "task": {
                "name": "Plan feature X",
                "user_message": "/plan-workflow build Implement feature X",
                "progress_pct": 100,
                "blocker": {
                    "type": "awaiting_approval",
                    "invoked_command": "/plan-workflow build Implement feature X",
                    "reason": "Plan not approved"
                }
            },
            "context": {
                "active_files": ["plan-20260304-feature-x.md"],
                "pending_operations": [],
                "visual_context": []
            },
            "continuation": {
                "next_steps": []
            }
        }

        message = format_restoration_message(handoff_data)

        self.assertIn("⚠️ **BLOCKER: Awaiting User Approval**", message)
        self.assertIn("/plan-workflow build Implement feature X", message)
        self.assertIn("DO NOT proceed with implementation", message)


class TestHandoffIntegration(unittest.TestCase):
    """Integration tests for handoff system."""

    def test_task_tracker_directory_exists(self):
        """Test that task tracker directory exists or can be created."""
        task_tracker_dir = HOOKS_DIR.parent / "state" / "task_tracker"

        if task_tracker_dir.exists():
            self.assertTrue(task_tracker_dir.is_dir())
        else:
            # Directory doesn't exist yet, but should be creatable
            self.assertTrue(task_tracker_dir.parent.exists())

    def test_handoff_package_importable(self):
        """Test that handoff package can be imported."""
        try:
            from handoff.hooks.__lib.handoff_store import HandoffStore
            self.assertTrue(HandoffStore is not None)
        except ImportError as e:
            self.fail(f"Cannot import handoff package: {e}")

    def test_hook_registration_in_routers(self):
        """Test that hooks are registered in their routers."""
        # Check PreCompact.py
        precompact_path = HOOKS_DIR / "PreCompact.py"
        with open(precompact_path, 'r') as f:
            precompact_content = f.read()
        self.assertIn("PreCompact_handoff_capture.py", precompact_content)

        # Check SessionStart.py
        sessionstart_path = HOOKS_DIR / "SessionStart.py"
        with open(sessionstart_path, 'r') as f:
            sessionstart_content = f.read()
        self.assertIn("SessionStart_handoff_restore.py", sessionstart_content)


if __name__ == "__main__":
    # Run tests
    unittest.main(verbosity=2)

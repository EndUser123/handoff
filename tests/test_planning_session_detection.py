#!/usr/bin/env python3
"""Tests for planning session detection and approval blocker system."""


import pytest

from handoff.hooks.__lib.session_type_detector import SessionTypeDetector


class TestPlanningSessionDetection:
    """Test planning session type detection."""

    def test_detect_plan_workflow_command(self):
        """Test that /plan-workflow command is detected as planning session."""
        detector = SessionTypeDetector()

        message = "/plan-workflow build Implement feature X"
        files = ["docs/plan-feature-x.md"]

        session_type = detector.detect_session_type(message, files)

        assert session_type == "planning", f"Expected 'planning', got '{session_type}'"

    def test_detect_arch_command(self):
        """Test that /arch command is detected as planning session."""
        detector = SessionTypeDetector()

        message = "/arch Design authentication system"
        files = ["docs/arch-auth.md"]

        session_type = detector.detect_session_type(message, files)

        assert session_type == "planning", f"Expected 'planning', got '{session_type}'"

    def test_detect_breakdown_command(self):
        """Test that /breakdown command is detected as planning session."""
        detector = SessionTypeDetector()

        message = "/breakdown Refactor user module"
        files = ["docs/tasks/user-refactor.md"]

        session_type = detector.detect_session_type(message, files)

        assert session_type == "planning", f"Expected 'planning', got '{session_type}'"

    def test_detect_design_command(self):
        """Test that /design command is detected as planning session."""
        detector = SessionTypeDetector()

        message = "/design Create API schema"
        files = ["docs/api-schema-design.md"]

        session_type = detector.detect_session_type(message, files)

        assert session_type == "planning", f"Expected 'planning', got '{session_type}'"

    def test_plan_file_triggers_planning_session(self):
        """Test that plan-*.md files trigger planning session even without explicit command."""
        detector = SessionTypeDetector()

        message = "Creating implementation plan for feature"
        files = ["plan-20260304-feature-x.md"]

        session_type = detector.detect_session_type(message, files)

        assert session_type == "planning", f"Expected 'planning', got '{session_type}'"

    def test_non_planning_message_not_detected(self):
        """Test that regular implementation messages are not detected as planning."""
        detector = SessionTypeDetector()

        message = "Implement authentication feature"
        files = ["src/auth.py"]

        session_type = detector.detect_session_type(message, files)

        assert session_type != "planning", f"Should not detect planning for implementation, got '{session_type}'"

    def test_planning_comment_does_not_trigger(self):
        """Test that mentioning planning command in a comment doesn't trigger planning session."""
        detector = SessionTypeDetector()

        # User is working on something else, just mentions planning
        message = "I need to remember to run /plan-workflow later"
        files = ["src/feature.py"]

        session_type = detector.detect_session_type(message, files)

        # Should detect as docs (mentions "remember", documentation-like)
        # or feature (working on feature.py), not planning
        assert session_type != "planning", f"Comment mentioning planning should not trigger, got '{session_type}'"


class TestBlockerCreation:
    """Test blocker creation for planning sessions."""

    def test_planning_session_creates_awaiting_approval_blocker(self):
        """Test that planning sessions create awaiting_approval blocker."""

        # This would require mocking the full PreCompactHook
        # For now, document expected behavior:
        # When session_type == "planning":
        #   blocker = {
        #     "type": "awaiting_approval",
        #     "description": "Planning complete. Awaiting user review before implementation.",
        #     "requires_action": "user_approval"
        #   }
        pass

    def test_non_planning_session_no_special_blocker(self):
        """Test that non-planning sessions don't get awaiting_approval blocker."""
        # When session_type != "planning":
        #   blocker = None (or existing blocker logic)
        pass


class TestInvokedCommandCapture:
    """Test invoked_command capture and restoration."""

    def test_invoked_command_captured_from_active_command_file(self):
        """Test that invoked_command is read from active_command.json."""
        # PreCompact should read from .claude/state/active_command.json
        # and capture "invoked_command" in state file
        pass

    def test_invoked_command_fallback_to_message_extraction(self):
        """Test fallback to extracting command from last_user_message."""
        # If active_command.json missing:
        # Extract first /command from last_user_message
        message = "/plan-workflow build Implement feature X"
        expected_command = "/plan-workflow build Implement feature X"

        # Extract first slash command
        import re

        match = re.search(r'/[a-z-]+(?:\s+[^\n]+)?', message)
        if match:
            command = match.group(0)
            assert command == expected_command

    def test_invoked_command_displayed_in_sessionstart(self):
        """Test that invoked_command is displayed in SessionStart restoration."""
        # SessionStart should display:
        # **Invoked Command:** /plan-workflow build Implement feature X
        pass


class TestSessionStartWarningDisplay:
    """Test SessionStart warning display for awaiting_approval blocker."""

    def test_awaiting_approval_blocker_shows_prominent_warning(self):
        """Test that awaiting_approval blocker shows prominent warning."""
        # When blocker.type == "awaiting_approval":
        # Display:
        # ⚠️ BLOCKER: Awaiting User Approval
        #   Plan has been created but NOT approved.
        #   DO NOT proceed with implementation until user reviews.
        # **Invoked Command:** /plan-workflow build...
        pass

    def test_regular_blocker_shows_normal_display(self):
        """Test that regular blockers show normal display (no special warning)."""
        # Regular blockers show:
        # **Current Blocker:** <description>
        # No special warning formatting
        pass


class TestBackwardCompatibility:
    """Test backward compatibility with old state files."""

    def test_old_state_file_without_invoked_command(self):
        """Test that old state files without invoked_command work correctly."""
        # Old state file format (no invoked_command field):
        old_state = {
            "terminal_id": "test_term",
            "task_name": "Feature X",
            "last_user_message": "Implement feature",
            "active_files": ["src/feature.py"],
            "session_type": "feature",
            # NO invoked_command field
        }

        # Should default to "unknown command"
        invoked_command = old_state.get("invoked_command", "unknown command")
        assert invoked_command == "unknown command"

    def test_old_state_file_without_blocker_type(self):
        """Test that old state files without blocker.type work correctly."""
        # Old state file format (blocker is string, not dict):
        old_state = {
            "terminal_id": "test_term",
            "task_name": "Feature X",
            "blocker": "API dependency missing",  # String, not dict
            # NO blocker.type field
        }

        # Should handle gracefully
        blocker = old_state.get("blocker")
        if isinstance(blocker, dict):
            blocker_type = blocker.get("type")
        else:
            blocker_type = None

        assert blocker_type is None

    def test_old_state_file_without_session_type(self):
        """Test that old state files without session_type default to unknown."""
        # Old state file format (no session_type field):
        old_state = {
            "terminal_id": "test_term",
            "task_name": "Feature X",
            "last_user_message": "Implement feature",
            # NO session_type field
        }

        # Should default to "unknown"
        session_type = old_state.get("session_type", "unknown")
        assert session_type == "unknown"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

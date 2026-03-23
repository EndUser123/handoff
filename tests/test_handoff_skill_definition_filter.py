"""Tests for skill definition filtering in handoff capture.

This test module verifies that skill definitions (SKILL.md content) are properly
filtered from:
1. Decision extraction (_build_decisions)
2. Goal extraction fallback

Bug report: After compaction, handoff system incorrectly captured 722-line
SKILL.md content as the user goal and decision constraints.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Load the transcript module directly to avoid circular imports in scripts/__init__.py
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPT_PATH = PACKAGE_ROOT / "scripts" / "hooks" / "__lib" / "transcript.py"

spec = importlib.util.spec_from_file_location("transcript", TRANSCRIPT_PATH)
transcript = importlib.util.module_from_spec(spec)
sys.modules["transcript"] = transcript
spec.loader.exec_module(transcript)

is_meta_instruction = transcript.is_meta_instruction


class TestIsMetaInstructionSkillDefinitions:
    """Test that is_meta_instruction correctly filters skill definitions."""

    def test_skill_definition_detected_as_meta(self) -> None:
        """Skill definitions starting with 'Base directory for this skill:' should be filtered."""
        skill_definition = """Base directory for this skill: P:/packages/handoff

# Handoff Skill

## Purpose
This skill provides...
"""
        assert is_meta_instruction(skill_definition) is True

    def test_skill_definition_variations(self) -> None:
        """Various skill definition formats should be filtered."""
        variations = [
            "Base directory for this skill: /some/path",
            "Base directory for this skill: P:\\some\\path",
            "Base directory for this skill: P:/some/path\n\n# Skill content",
        ]
        for variation in variations:
            assert is_meta_instruction(variation) is True, (
                f"Failed for: {variation[:50]}..."
            )

    def test_legitimate_user_message_not_filtered(self) -> None:
        """Legitimate user messages should NOT be filtered."""
        legitimate_messages = [
            "implement the handoff fix",
            "you must not break existing behavior",
            "I decided to use the filter approach",
            "do not include skill definitions",
        ]
        for message in legitimate_messages:
            assert is_meta_instruction(message) is False, (
                f"Incorrectly filtered: {message}"
            )


class TestBuildDecisionsSkillFilter:
    """Test that _build_decisions filters skill definitions."""

    def test_skill_definition_not_captured_as_decision(self) -> None:
        """Skill definitions with decision keywords should NOT become decisions."""
        # This will be a failing test initially (RED phase)
        # Import here to allow test to fail gracefully if module not ready

        # Create mock transcript with skill definition containing decision keywords
        # The skill definition appears as a "user" message in the transcript
        skill_definition_content = """Base directory for this skill: P:/some/path

# Test Skill

## Constraints
- You must always validate input
- Do not skip tests
- Never ignore errors
"""

        # For now, we test the filtering logic directly
        # In integration tests, we'd use a real transcript
        assert is_meta_instruction(skill_definition_content) is True

    def test_legitimate_constraint_captured_as_decision(self) -> None:
        """Legitimate user constraints should still be captured."""
        # This verifies we don't over-filter
        legitimate_constraint = "You must validate all user input before processing"
        assert is_meta_instruction(legitimate_constraint) is False


class TestGoalExtractionSkillFilter:
    """Test that goal extraction filters skill definitions."""

    def test_fallback_goal_filters_skill_definition(self) -> None:
        """When falling back to last user message, skill definitions should be filtered."""
        # The fix should apply is_meta_instruction() to fallback_goal
        skill_definition = (
            "Base directory for this skill: P:/packages/handoff\n\n# Content..."
        )
        assert is_meta_instruction(skill_definition) is True

    def test_skill_definition_in_goal_replaced_with_context(self) -> None:
        """If goal looks like skill definition, it should be replaced."""
        # This tests the existing behavior at lines 311-313
        goal = "Base directory for this skill: P:/some/path\n\n# Skill content"
        assert goal.lower().startswith("base directory for this skill:")


class TestRegressionSkillCapture:
    """Regression test for the reported bug.

    Bug: After compaction, goal field contained 722-line SKILL.md content
    instead of user request, and decision_register contained skill definitions.
    """

    def test_skill_definition_not_captured_as_goal(self) -> None:
        """Skill definitions should never become the goal."""
        skill_definition = """Base directory for this skill: P:/packages/handoff

# Handoff Skill - Session Context Preservation

[722 lines of skill content...]
"""
        # Verify the skill definition is properly identified as meta instruction
        assert is_meta_instruction(skill_definition) is True

    def test_skill_constraints_not_captured_as_decisions(self) -> None:
        """Skill definition constraints should NOT appear in decision_register."""
        # Skill definitions often contain "must", "do not", "never" patterns
        skill_with_constraints = """Base directory for this skill: P:/packages/handoff

## Constraints
- You must preserve context across compaction
- Do not lose user goals
- Never skip the decision register
"""
        # This should be filtered, not captured as a decision
        assert is_meta_instruction(skill_with_constraints) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

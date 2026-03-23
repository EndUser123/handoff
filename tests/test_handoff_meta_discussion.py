"""Tests for meta-discussion detection in handoff extraction.

This test module verifies that conversational fragments about the system
are properly filtered from goal and decision extraction.
"""

from scripts.hooks.__lib.transcript import (
    is_meta_discussion,
)
import pytest


class TestIsMetaDiscussion:
    """Test that is_meta_discussion correctly identifies meta-discussion."""

    def test_so_youre_question_detected(self):
        """Questions starting with 'So you're' should be filtered."""
        meta_message = "So you're just going to sit there and do nothing unless I tell you to do something."
        assert is_meta_discussion(meta_message) is True

    def test_dont_understand_question_detected(self):
        """Questions about not understanding should be filtered."""
        meta_message = (
            "I don't understand task five. Don't we have something to fix first?"
        )
        assert is_meta_discussion(meta_message) is True

    def test_system_question_detected(self):
        """Questions about the system should be filtered."""
        meta_message = "Did it work? Is it optimal?"
        assert is_meta_discussion(meta_message) is True

    def test_are_there_more_detected(self):
        """Questions asking for more tasks should be filtered."""
        meta_message = "Are there more ideas? Are there more fixes?"
        assert is_meta_discussion(meta_message) is True

    def test_do_you_hate_detected(self):
        """Conversational questions about feelings should be filtered."""
        meta_message = "Do you hate yourself?"
        assert is_meta_discussion(meta_message) is True

    def test_legitimate_task_not_filtered(self):
        """Legitimate task messages should NOT be filtered."""
        task_messages = [
            "implement the handoff fix",
            "add tests for meta-discussion detection",
            "fix the truncation bug in decisions",
            "update the plan with new requirements",
        ]
        for message in task_messages:
            assert is_meta_discussion(message) is False, f"Should not filter: {message}"

    def test_skill_definition_detected(self):
        """Skill definitions should still be filtered."""
        skill_def = "Base directory for this skill: P:/packages/handoff"
        assert is_meta_discussion(skill_def) is True

    def test_meta_instruction_also_detected(self):
        """Meta-instructions should also be caught."""
        meta_instructions = [
            "thanks for the help",
            "summarize what we did",
            "are we done yet?",
        ]
        for message in meta_instructions:
            assert is_meta_discussion(message) is True, f"Should filter: {message}"


class TestDecisionExtractionIntegration:
    """Test that meta-discussion is filtered from decision extraction."""

    def test_conversational_fragment_not_decision(self):
        """Conversational fragments should not be captured as decisions."""
        # This is what appeared in the actual handoff file
        conversation = "Our solution needs to be multi-terminal isolated and immune to stale data. Remember?"

        # Should be detected as meta-discussion
        assert is_meta_discussion(conversation) is True

    def test_legitimate_constraint_still_captured(self):
        """Legitimate constraints should still be captured."""
        # This is a real constraint that should be captured
        constraint = "Our solution must use Python 3.12+ for type hints compatibility."

        assert is_meta_discussion(constraint) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

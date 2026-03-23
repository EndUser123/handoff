"""Tests for correction message detection in handoff goal extraction.

This test module verifies that user correction messages are properly filtered
from goal extraction to prevent capturing what the task ISN'T rather than what it IS.
"""

from scripts.hooks.__lib.transcript import (
    is_correction_message,
    extract_last_substantive_user_message,
)
import json
import pytest
import tempfile
from pathlib import Path


class TestIsCorrectionMessage:
    """Test that is_correction_message correctly identifies user corrections."""

    def test_no_task_is_not_about_detected(self):
        """'No, the task is not about' pattern should be filtered."""
        correction = "No, the task is not about teaching users, it's about updating your templates."
        assert is_correction_message(correction) is True

    def test_thats_not_what_i_asked_detected(self):
        """'That's not what I asked' pattern should be filtered."""
        correction = "That's not what I asked. You did the wrong task."
        assert is_correction_message(correction) is True

    def test_you_did_wrong_task_detected(self):
        """'You did the wrong task' pattern should be filtered."""
        correction = "You did the wrong task. I asked for something else."
        assert is_correction_message(correction) is True

    def test_you_are_wrong_about_detected(self):
        """'You're wrong about' pattern should be filtered."""
        correction = "You're wrong about the approach. We need to use async."
        assert is_correction_message(correction) is True

    def test_i_didnt_ask_for_detected(self):
        """'I didn't ask for' pattern should be filtered."""
        correction = "I didn't ask for a refactor, I asked for a bug fix."
        assert is_correction_message(correction) is True

    def test_thats_incorrect_detected(self):
        """'That's incorrect' pattern should be filtered."""
        correction = "That's incorrect. The requirement is X, not Y."
        assert is_correction_message(correction) is True

    def test_losing_mind_making_stuff_up_detected(self):
        """'You're losing your mind/making stuff up' pattern should be filtered."""
        correction = (
            "You're losing your mind in making stuff up. Check the last chat session."
        )
        assert is_correction_message(correction) is True

    def test_thats_not_what_i_meant_detected(self):
        """'That's not what I meant' pattern should be filtered."""
        correction = (
            "That's not what I meant. The task is about prompting enhancements."
        )
        assert is_correction_message(correction) is True

    def test_not_about_teaching_detected(self):
        """'Not about teaching' pattern should be filtered."""
        correction = (
            "No, the task is not about teaching users, it's about updating templates."
        )
        assert is_correction_message(correction) is True

    def test_task_is_not_about_detected(self):
        """'The task is not about' pattern should be filtered."""
        correction = "The task is not about teaching users."
        assert is_correction_message(correction) is True

    def test_legitimate_task_not_filtered(self):
        """Legitimate task messages should NOT be filtered."""
        task_messages = [
            "Implement the handoff fix",
            "Add tests for correction message detection",
            "Fix the truncation bug in decisions",
            "Update the plan with new requirements",
            "Work on prompting enhancements for /arch templates",
        ]
        for message in task_messages:
            assert is_correction_message(message) is False, (
                f"Should not filter: {message}"
            )

    def test_normal_task_with_negative_word_not_filtered(self):
        """Tasks with negative words but not corrections should NOT be filtered."""
        legitimate_tasks = [
            "Don't forget to add error handling",  # Starts with "Don't" but is a task
            "Refactor the authentication code",  # No correction pattern
            "Fix the bug in the test suite",  # No correction pattern
        ]
        for message in legitimate_tasks:
            assert is_correction_message(message) is False, (
                f"Should not filter: {message}"
            )

    def test_mid_message_corrections_detected(self):
        """Corrections in the middle of messages should be detected."""
        mid_message_corrections = [
            "Wait, that's not what I asked for. I need feature X.",
            "Actually, no - you're doing it wrong. Let me clarify.",
            "Hold on, you misunderstood the requirement.",
            "Let me clarify - the task is about testing, not deployment.",
        ]
        for message in mid_message_corrections:
            assert is_correction_message(message) is True, (
                f"Should detect mid-message correction: {message}"
            )

    def test_ai_state_criticism_detected(self):
        """AI state criticism patterns should be detected."""
        criticism_messages = [
            "You're confused about the requirements",
            "You're misinterpreting what I asked for",
            "You misunderstood the task completely",
            "Stop hallucinating and read the requirements",
            "Let me clarify what I actually asked for",
        ]
        for message in criticism_messages:
            assert is_correction_message(message) is True, (
                f"Should detect AI criticism: {message}"
            )

    def test_general_correction_indicators_detected(self):
        """General correction indicators should be detected."""
        general_corrections = [
            "Actually, not that. I need feature X instead.",
            "Wait, that's wrong. The requirement is Y.",
            "Correction: The task is about testing, not deployment.",
            "Actually, wrong approach. Use async instead.",
        ]
        for message in general_corrections:
            assert is_correction_message(message) is True, (
                f"Should detect general correction: {message}"
            )


class TestGoalExtractionWithCorrections:
    """Test that correction messages are skipped in goal extraction."""

    def create_test_transcript(self, entries, output_path):
        """Create a test transcript JSONL file."""
        with open(output_path, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

    def test_correction_heavy_conversation(self):
        """Case 1: Correction-heavy conversation → Skip corrections, extract actual task.

        Expected: Extract "Work on prompting enhancements for /arch templates",
        not the correction messages.
        """
        entries = [
            {
                "type": "user",
                "message": {
                    "content": ["That's not what I asked. You did the wrong task."]
                },
                "timestamp": "2026-03-19T12:00:00Z",
            },
            {
                "type": "assistant",
                "message": {
                    "content": ["I apologize. Let me understand the correct task."]
                },
                "timestamp": "2026-03-19T12:00:01Z",
            },
            {
                "type": "user",
                "message": {
                    "content": [
                        "You are losing your mind in making stuff up. Check the last chat session because you will find that I asked you about prompting enhancements."
                    ]
                },
                "timestamp": "2026-03-19T12:00:02Z",
            },
            {
                "type": "assistant",
                "message": {
                    "content": [
                        "I understand now. Let me work on prompting enhancements."
                    ]
                },
                "timestamp": "2026-03-19T12:00:03Z",
            },
            {
                "type": "user",
                "message": {
                    "content": [
                        "No, the task is not about teaching users, it's about updating your templates."
                    ]
                },
                "timestamp": "2026-03-19T12:00:04Z",
            },
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            temp_path = f.name

        try:
            self.create_test_transcript(entries, temp_path)
            result_dict = extract_last_substantive_user_message(temp_path)
            result = result_dict.get("goal", "Unknown task")

            # With the fix, all correction messages should be skipped
            # The function should continue searching backwards
            # In this case, the first message is also a correction
            # So it should return "Unknown task" or the first non-correction message
            assert (
                result
                != "No, the task is not about teaching users, it's about updating your templates."
            )
            assert (
                result
                != "You are losing your mind in making stuff up. Check the last chat session because you will find that I asked you about prompting enhancements."
            )
            assert result != "That's not what I asked. You did the wrong task."

            # Verify observability data is present
            assert "corrections_skipped" in result_dict
            assert result_dict["corrections_skipped"] > 0, (
                "Should have skipped corrections"
            )
        finally:
            Path(temp_path).unlink()

    def test_correction_then_task(self):
        """Case 2: Correction followed by actual task → Extract task, skip correction.

        Expected: Extract "Implement the feature", not "That's not what I asked".
        """
        entries = [
            {
                "type": "user",
                "message": {"content": ["Implement the feature"]},
                "timestamp": "2026-03-19T12:00:00Z",
            },
            {
                "type": "assistant",
                "message": {"content": ["I'll implement it wrong"]},
                "timestamp": "2026-03-19T12:00:01Z",
            },
            {
                "type": "user",
                "message": {"content": ["That's not what I asked"]},
                "timestamp": "2026-03-19T12:00:02Z",
            },
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            temp_path = f.name

        try:
            self.create_test_transcript(entries, temp_path)
            result_dict = extract_last_substantive_user_message(temp_path)
            result = result_dict.get("goal", "Unknown task")

            # Should skip the correction and find the actual task
            expected = "Implement the feature"
            assert result == expected, f"Expected '{expected}', got '{result}'"
        finally:
            Path(temp_path).unlink()

    def test_only_correction_messages(self):
        """Case 3: Only correction messages → Return "Unknown task" or continue searching.

        Expected: Returns "Unknown task" when all messages are corrections.
        """
        entries = [
            {
                "type": "user",
                "message": {"content": ["That's not what I asked"]},
                "timestamp": "2026-03-19T12:00:00Z",
            },
            {
                "type": "assistant",
                "message": {"content": ["I apologize"]},
                "timestamp": "2026-03-19T12:00:01Z",
            },
            {
                "type": "user",
                "message": {"content": ["No, the task is not about teaching users"]},
                "timestamp": "2026-03-19T12:00:02Z",
            },
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            temp_path = f.name

        try:
            self.create_test_transcript(entries, temp_path)
            result_dict = extract_last_substantive_user_message(temp_path)
            result = result_dict.get("goal", "Unknown task")

            # Should return "Unknown task" when all messages are corrections
            # or continue searching if there are more messages
            # The important thing is it shouldn't return a correction message
            if result != "Unknown task":
                # If it found something, make sure it's not a correction
                assert not is_correction_message(result), (
                    f"Should not return correction: {result}"
                )
        finally:
            Path(temp_path).unlink()

    def test_normal_conversation_unchanged(self):
        """Case 4: Normal conversation → Extract task (no change in behavior).

        Expected: Extract "Add feature X" (same as before the fix).
        """
        entries = [
            {
                "type": "user",
                "message": {"content": ["Add feature X"]},
                "timestamp": "2026-03-19T12:00:00Z",
            },
            {
                "type": "assistant",
                "message": {"content": ["I'll add feature X"]},
                "timestamp": "2026-03-19T12:00:01Z",
            },
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            temp_path = f.name

        try:
            self.create_test_transcript(entries, temp_path)
            result_dict = extract_last_substantive_user_message(temp_path)
            result = result_dict.get("goal", "Unknown task")

            expected = "Add feature X"
            assert result == expected, f"Expected '{expected}', got '{result}'"
        finally:
            Path(temp_path).unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

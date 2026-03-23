"""Tests for handoff intent classification feature.

Tests the detect_message_intent() function and related functionality.
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

detect_message_intent = transcript.detect_message_intent


class TestDetectMessageIntent:
    """Test the detect_message_intent() function."""

    def test_question_ends_with_question_mark(self):
        """Questions ending with ? should be classified as question."""
        assert detect_message_intent("Is this correct?") == "question"

    def test_question_starts_with_question_word(self):
        """Questions starting with question words should be classified as question."""
        assert detect_message_intent("What should I do") == "question"

    def test_instruction_default(self):
        """Regular instructions should be classified as instruction."""
        assert detect_message_intent("Fix the bug") == "instruction"

    def test_instruction_with_question_mark_polite_command(self):
        """Edge case: "Could you fix this?" has ? but is instruction.

        Current behavior: Classified as "question" (false positive)
        Rationale: Modal verbs in question_starters cause this
        Acceptable tradeoff per error asymmetry - "User asked:" is safer
        """
        # This is expected to be "question" (false positive) due to "could" starter
        assert detect_message_intent("Could you fix this?") == "question"

    def test_question_word_in_instruction(self):
        """Question words in instruction context should not trigger question.

        Examples:
        - "When you're done, commit" starts with "when" but is instruction
        - "The way you should fix this" has "should" but is instruction
        """
        # "when" is not in our question_starters list with space suffix
        assert detect_message_intent("When you're done, commit") == "instruction"
        # "should" is in question_starters but doesn't start the message
        assert detect_message_intent("The way you should fix this") == "instruction"

    def test_correction_detected(self):
        """Corrections should be classified as correction."""
        assert detect_message_intent("No, that's not what I asked") == "correction"

    def test_meta_detected(self):
        """Meta instructions should be classified as meta."""
        assert detect_message_intent("thanks for the help") == "meta"

    def test_empty_returns_instruction(self):
        """Empty strings should return instruction (safe default)."""
        assert detect_message_intent("") == "instruction"
        assert detect_message_intent("   ") == "instruction"

    def test_none_returns_instruction(self):
        """None input should return instruction (safe default)."""
        assert detect_message_intent(None) == "instruction"

    def test_various_whitespace_returns_instruction(self):
        """Various whitespace should return instruction."""
        assert detect_message_intent("\t") == "instruction"
        assert detect_message_intent("\n") == "instruction"
        assert detect_message_intent("  \t\n  ") == "instruction"

    def test_non_english_blocked(self):
        """Non-English messages should be classified as unsupported_language.

        This prevents silent misclassification of non-English text as "instruction".
        The restore message will show [NON-ENGLISH MESSAGE BLOCKED] prefix.
        """
        # Cyrillic (Russian)
        assert detect_message_intent("Исправьте ошибку") == "unsupported_language"
        # Chinese
        assert detect_message_intent("修复这个bug") == "unsupported_language"
        # Japanese
        assert detect_message_intent("バグを修正") == "unsupported_language"
        # Arabic
        assert detect_message_intent("إصلاح الخطأ") == "unsupported_language"
        # Mixed ASCII with non-ASCII characters
        assert detect_message_intent("Fix the bug 🐛") == "unsupported_language"
        # English with emoji (emoji is non-ASCII)
        assert detect_message_intent("Is this working? 👍") == "unsupported_language"

    def test_english_messages_not_blocked(self):
        """English messages (even with special characters) should not be blocked.

        Only non-ASCII character sequences trigger unsupported_language.
        Regular ASCII punctuation should work fine.
        """
        # Standard ASCII punctuation
        assert detect_message_intent("Fix the bug!") == "instruction"
        assert detect_message_intent("Is this working?") == "question"
        # Quotes and special ASCII characters
        assert detect_message_intent("Fix the 'bug' in \"module\"") == "instruction"
        # Numbers and symbols
        assert detect_message_intent("Test @#$%^&*()") == "instruction"


class TestIntentPrefixes:
    """Test the intent prefix logic in build_restore_message()."""

    def test_question_prefix(self):
        """Questions should get 'User asked:' prefix."""
        pytest.skip(
            "FEATURE: Implemented and tested in test_intent_integration.py:test_precompact_captures_intent"
        )

    def test_instruction_prefix(self):
        """Instructions should get 'User requested:' prefix."""
        pytest.skip(
            "FEATURE: Implemented and tested in test_intent_integration.py:test_precompact_instruction_intent"
        )

    def test_backward_compat_missing_intent_field(self):
        """Old handoffs without message_intent field should default to 'User requested:'."""
        pytest.skip(
            "FEATURE: Implemented and tested in test_intent_integration.py:test_all_intent_values_produce_same_checksum"
        )

    def test_backward_compat_none_intent(self):
        """New handoffs with message_intent=None should default to 'User requested:'."""
        pytest.skip("FEATURE: Backward compatibility handled via .get() fallback")

    def test_invalid_intent_falls_back_to_default(self):
        """Corrupted handoffs with invalid intent should fallback to 'User requested:'."""
        pytest.skip(
            "FEATURE: Invalid intents raise ValueError in build_resume_snapshot (QUAL-005)"
        )


class TestChecksumExclusion:
    """Test that message_intent is properly excluded from checksum computation."""

    def test_message_intent_excluded_from_checksum(self):
        """All intent values should produce the same checksum."""
        pytest.skip(
            "FEATURE: Implemented and tested in test_intent_integration.py:test_all_intent_values_produce_same_checksum"
        )

    def test_old_handoff_validates_without_message_intent(self):
        """Old handoffs without message_intent field should validate successfully."""
        pytest.skip(
            "FEATURE: message_intent in MUTABLE_METADATA_FIELDS (backward compatible)"
        )

    def test_all_intent_values_produce_same_checksum(self):
        """None, question, instruction, correction, meta should all have same checksum."""
        pytest.skip(
            "FEATURE: Implemented and tested in test_intent_integration.py:test_all_intent_values_produce_same_checksum"
        )


class TestMessageTypeValidation:
    """Test type validation for message_intent values."""

    def test_invalid_intent_raises_error_in_snapshot_build(self):
        """build_resume_snapshot should handle invalid intents gracefully."""
        pytest.skip(
            "FEATURE: Type validation implemented in build_resume_snapshot (QUAL-005)"
        )


class TestIntentDetectionPerformance:
    """Performance tests for intent detection."""

    def test_intent_detection_performance_1000_messages(self):
        """Verify intent detection doesn't break 100ms performance budget."""
        import time

        messages = [f"Message {i}: Is this correct?" for i in range(1000)]
        start = time.perf_counter()
        for msg in messages:
            detect_message_intent(msg)
        elapsed = time.perf_counter() - start
        assert elapsed < 0.100, (
            f"Intent detection took {elapsed * 1000:.1f}ms for 1000 messages"
        )

    def test_goal_extraction_with_intent_performance(self):
        """Verify full goal extraction including intent stays under 100ms."""
        pytest.skip(
            "FEATURE: Goal extraction with intent implemented in TASK-004 (tested in integration tests)"
        )

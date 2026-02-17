#!/usr/bin/env python3
"""Tests for transcript.py extract_user_message_from_blocker function.

Tests the blocker-to-user-message extraction logic that strips the
"User's last question:" prefix from blocker descriptions.
"""

import pytest

from handoff.hooks.__lib.transcript import extract_user_message_from_blocker


class TestExtractUserMessageFromBlocker:
    """Test extract_user_message_from_blocker function with various blocker formats."""

    def test_dict_with_prefix(self) -> None:
        """Test blocker dict with 'User's last question:' prefix."""
        blocker = {
            "description": "User's last question: implement option a",
            "severity": "info",
            "source": "transcript",
        }
        result = extract_user_message_from_blocker(blocker)
        assert result == "implement option a"

    def test_dict_with_prefix_extra_whitespace(self) -> None:
        """Test blocker dict with prefix and extra whitespace."""
        blocker = {
            "description": "User's last question:   fix the bug in parser  ",
            "severity": "info",
        }
        result = extract_user_message_from_blocker(blocker)
        assert result == "fix the bug in parser"

    def test_string_with_prefix(self) -> None:
        """Test string blocker with 'User's last question:' prefix."""
        blocker = "User's last question: update the package"
        result = extract_user_message_from_blocker(blocker)
        assert result == "update the package"

    def test_dict_without_prefix(self) -> None:
        """Test blocker dict without prefix - returns description as-is."""
        blocker = {
            "description": "just implement feature X",
            "severity": "info",
        }
        result = extract_user_message_from_blocker(blocker)
        assert result == "just implement feature X"

    def test_string_without_prefix(self) -> None:
        """Test string blocker without prefix - returns as-is."""
        blocker = "fix bug in authentication"
        result = extract_user_message_from_blocker(blocker)
        assert result == "fix bug in authentication"

    def test_none_blocker(self) -> None:
        """Test None blocker returns None."""
        result = extract_user_message_from_blocker(None)
        assert result is None

    def test_empty_dict(self) -> None:
        """Test empty dict returns None."""
        result = extract_user_message_from_blocker({})
        assert result is None

    def test_dict_with_empty_description(self) -> None:
        """Test dict with empty description returns None."""
        blocker = {"description": "", "severity": "info"}
        result = extract_user_message_from_blocker(blocker)
        assert result is None

    def test_dict_missing_description_field(self) -> None:
        """Test dict without description field returns None."""
        blocker = {"severity": "info", "source": "manual"}
        result = extract_user_message_from_blocker(blocker)
        assert result is None

    def test_empty_string(self) -> None:
        """Test empty string returns None."""
        result = extract_user_message_from_blocker("")
        assert result is None

    def test_prefix_only_empty_after(self) -> None:
        """Test prefix with nothing after it returns None."""
        blocker = {"description": "User's last question:   "}
        result = extract_user_message_from_blocker(blocker)
        assert result is None

    def test_invalid_type(self) -> None:
        """Test invalid type (list, int, etc.) returns None."""
        assert extract_user_message_from_blocker(["list", "value"]) is None
        assert extract_user_message_from_blocker(123) is None
        assert extract_user_message_from_blocker(3.14) is None

    def test_long_message_with_prefix(self) -> None:
        """Test long user message is preserved correctly."""
        long_msg = (
            "User's last question: implement a comprehensive refactoring of the "
            "authentication system including OAuth2 integration, JWT token management, "
            "and session handling across multiple microservices"
        )
        result = extract_user_message_from_blocker(long_msg)
        assert result.startswith("implement a comprehensive refactoring")
        assert "authentication system" in result
        assert "session handling" in result

    def test_multiline_description(self) -> None:
        """Test multiline description handles newlines."""
        blocker = {
            "description": "User's last question: fix the parser\nand add tests",
        }
        result = extract_user_message_from_blocker(blocker)
        # Newlines are preserved in the message
        assert "fix the parser" in result
        assert "add tests" in result

    def test_prefix_case_sensitive(self) -> None:
        """Test prefix is case-sensitive (lowercase 'user's' won't match)."""
        blocker = {"description": "user's last question: lowercase prefix"}
        result = extract_user_message_from_blocker(blocker)
        # Prefix not matched due to case sensitivity, returns as-is
        assert result == "user's last question: lowercase prefix"

    def test_partial_prefix_match(self) -> None:
        """Test partial prefix match (should still work)."""
        blocker = {"description": "User's last question was: should we use this?"}
        result = extract_user_message_from_blocker(blocker)
        # Only exact "User's last question:" is stripped
        assert "was:" in result

    def test_unicode_characters(self) -> None:
        """Test message with unicode characters."""
        blocker = {"description": "User's last question: fix the emoji 🐛 bug"}
        result = extract_user_message_from_blocker(blocker)
        assert result == "fix the emoji 🐛 bug"

    def test_real_compaction_example(self) -> None:
        """Test the actual compaction case from the bug fix."""
        blocker = {
            "description": "User's last question: yes, update the package",
            "severity": "info",
            "source": "transcript",
        }
        result = extract_user_message_from_blocker(blocker)
        assert result == "yes, update the package"

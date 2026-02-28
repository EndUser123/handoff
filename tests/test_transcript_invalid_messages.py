#!/usr/bin/env python3
"""Tests for transcript.py extract_transcript_from_messages function.

Tests invalid message handling - ensures the function gracefully skips invalid
messages and continues processing valid ones.
"""

import pytest

from handoff.hooks.__lib.transcript import extract_transcript_from_messages


class TestExtractTranscriptFromMessagesInvalidInput:
    """Test extract_transcript_from_messages with invalid message formats."""

    def test_skips_non_dict_messages(self):
        """
        Test that non-dict messages are skipped.

        Given: A list of messages containing non-dict items
        When: extract_transcript_from_messages is called
        Then: Non-dict messages are skipped, valid messages are processed
        """
        messages = [
            {"role": "user", "content": "valid message 1"},
            "not a dict",
            {"role": "assistant", "content": "valid message 2"},
            123,
            None,
            ["list", "instead", "of", "dict"],
        ]

        result = extract_transcript_from_messages(messages)

        # Should only process the two valid dict messages
        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "valid message 1"
        assert result[1]["role"] == "assistant"
        assert result[1]["content"] == "valid message 2"

    def test_skips_messages_missing_role_field(self):
        """
        Test that messages missing 'role' field are skipped.

        Given: A list of messages with some missing 'role' field
        When: extract_transcript_from_messages is called
        Then: Messages without 'role' are skipped, valid messages are processed
        """
        messages = [
            {"role": "user", "content": "valid message 1"},
            {"content": "missing role field"},
            {"role": "assistant", "content": "valid message 2"},
            {"unexpected_field": "value"},
            {"role": "user", "content": "valid message 3"},
        ]

        result = extract_transcript_from_messages(messages)

        # Should only process messages with 'role' field
        assert len(result) == 3
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "valid message 1"
        assert result[1]["role"] == "assistant"
        assert result[1]["content"] == "valid message 2"
        assert result[2]["role"] == "user"
        assert result[2]["content"] == "valid message 3"

    def test_skips_messages_with_unexpected_types(self):
        """
        Test that messages with unexpected value types are skipped.

        Given: A list of messages with unexpected types for fields
        When: extract_transcript_from_messages is called
        Then: Messages with invalid types are skipped
        """
        messages = [
            {"role": "user", "content": "valid message"},
            {"role": 123, "content": "role is not a string"},
            {"role": "user", "content": ["content", "is", "list"]},
            {"role": None, "content": "role is None"},
            {"role": "assistant", "content": "another valid message"},
        ]

        result = extract_transcript_from_messages(messages)

        # Should only process messages with correct types
        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "valid message"
        assert result[1]["role"] == "assistant"
        assert result[1]["content"] == "another valid message"

    def test_handles_empty_list(self):
        """
        Test that an empty message list returns empty result.

        Given: An empty list of messages
        When: extract_transcript_from_messages is called
        Then: Returns empty list
        """
        result = extract_transcript_from_messages([])
        assert result == []

    def test_handles_all_invalid_messages(self):
        """
        Test that a list with only invalid messages returns empty result.

        Given: A list containing only invalid messages
        When: extract_transcript_from_messages is called
        Then: Returns empty list
        """
        messages = [
            "not a dict",
            123,
            None,
            {"content": "missing role"},
            {"role": 123, "content": "invalid role type"},
        ]

        result = extract_transcript_from_messages(messages)
        assert result == []

    def test_preserves_valid_message_structure(self):
        """
        Test that valid message structure is preserved.

        Given: A list of valid messages with various fields
        When: extract_transcript_from_messages is called
        Then: All fields are preserved in the output
        """
        messages = [
            {
                "role": "user",
                "content": "message with metadata",
                "timestamp": "2024-01-01T00:00:00Z",
                "tool_calls": None,
            },
            {"role": "assistant", "content": "simple message"},
        ]

        result = extract_transcript_from_messages(messages)

        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "message with metadata"
        assert result[0]["timestamp"] == "2024-01-01T00:00:00Z"
        assert result[0]["tool_calls"] is None
        assert result[1]["role"] == "assistant"
        assert result[1]["content"] == "simple message"

    def test_mixed_valid_and_invalid_messages_complex(self):
        """
        Test complex mix of valid and invalid messages.

        Given: A realistic mix of valid and invalid messages
        When: extract_transcript_from_messages is called
        Then: Only valid messages are extracted and returned in order
        """
        messages = [
            {"role": "user", "content": "first valid"},
            None,
            {"role": "assistant", "content": "second valid"},
            "invalid string",
            {"content": "missing role"},
            {"role": "user", "content": "third valid"},
            {"role": 123, "content": "invalid role type"},
            {"role": "user", "content": "fourth valid"},
            [],
            {"role": "assistant", "content": "fifth valid"},
        ]

        result = extract_transcript_from_messages(messages)

        assert len(result) == 5
        assert result[0] == {"role": "user", "content": "first valid"}
        assert result[1] == {"role": "assistant", "content": "second valid"}
        assert result[2] == {"role": "user", "content": "third valid"}
        assert result[3] == {"role": "user", "content": "fourth valid"}
        assert result[4] == {"role": "assistant", "content": "fifth valid"}

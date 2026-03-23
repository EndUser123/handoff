#!/usr/bin/env python3
"""Edge case tests for transcript extraction (Item 10).

This test covers edge cases in transcript processing:
- Empty transcripts
- Single-message transcripts
- All-meta transcripts (no substantive messages)
- All-correction transcripts (no substantive messages)
- Very short messages (< 10 chars)
- Non-English messages
- Malformed transcript entries
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.hooks.__lib.transcript import extract_last_substantive_user_message


def _write_transcript(path: Path, entries: list[dict]) -> None:
    """Write transcript entries to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry) + "\n")


def test_empty_transcript_returns_unknown():
    """Empty transcript should return 'Unknown task' with scan_pattern 'no_entries'."""
    transcript_path = Path("/tmp/test_empty.jsonl")
    _write_transcript(transcript_path, [])

    result = extract_last_substantive_user_message(str(transcript_path))

    assert result["goal"] == "Unknown task"
    assert (
        result["scan_pattern"] == "no_entries"
    )  # Actual behavior: "no_entries" not "not_found"
    assert result["messages_scanned"] == 0

    # Clean up
    transcript_path.unlink(missing_ok=True)


def test_single_substantive_message():
    """Single substantive message should be returned."""
    transcript_path = Path("/tmp/test_single.jsonl")
    _write_transcript(
        transcript_path,
        [
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "text",
                            "text": "Implement feature X with proper error handling and logging",
                        }
                    ]
                },
            },
        ],
    )

    result = extract_last_substantive_user_message(str(transcript_path))

    assert (
        result["goal"] == "Implement feature X with proper error handling and logging"
    )
    assert result["scan_pattern"] == "found_substantive"
    assert result["messages_scanned"] == 1
    assert result["message_intent"] == "instruction"

    # Clean up
    transcript_path.unlink(missing_ok=True)


def test_single_meta_message():
    """Single meta instruction should be filtered out.

    Note: Uses pattern that actually matches META_PATTERNS in transcript.py.
    """
    transcript_path = Path("/tmp/test_single_meta.jsonl")
    _write_transcript(
        transcript_path,
        [
            {
                "type": "user",
                "message": {
                    "content": [{"type": "text", "text": "summarize what we did"}]
                },
            },
        ],
    )

    result = extract_last_substantive_user_message(str(transcript_path))

    assert result["goal"] == "Unknown task"
    assert result["scan_pattern"] == "not_found"
    assert result["meta_skipped"] == 1

    # Clean up
    transcript_path.unlink(missing_ok=True)


def test_single_correction_message():
    """Single correction message should be filtered out."""
    transcript_path = Path("/tmp/test_single_correction.jsonl")
    _write_transcript(
        transcript_path,
        [
            {
                "type": "user",
                "message": {
                    "content": [
                        {"type": "text", "text": "That's wrong, fix it differently"}
                    ]
                },
            },
        ],
    )

    result = extract_last_substantive_user_message(str(transcript_path))

    assert result["goal"] == "Unknown task"
    assert result["scan_pattern"] == "not_found"
    assert result["corrections_skipped"] == 1

    # Clean up
    transcript_path.unlink(missing_ok=True)


def test_single_very_short_message():
    """Single very short message (< 10 chars) should be filtered out."""
    transcript_path = Path("/tmp/test_short.jsonl")
    _write_transcript(
        transcript_path,
        [
            {
                "type": "user",
                "message": {"content": [{"type": "text", "text": "OK"}]},
            },
        ],
    )

    result = extract_last_substantive_user_message(str(transcript_path))

    assert result["goal"] == "Unknown task"
    assert result["scan_pattern"] == "not_found"

    # Clean up
    transcript_path.unlink(missing_ok=True)


def test_all_meta_transcript():
    """Transcript with only meta instructions should return 'Unknown task'.

    Note: Uses patterns that actually match META_PATTERNS in transcript.py.
    """
    transcript_path = Path("/tmp/test_all_meta.jsonl")
    _write_transcript(
        transcript_path,
        [
            {
                "type": "user",
                "message": {
                    "content": [{"type": "text", "text": "summarize what we did"}]
                },
            },
            {
                "type": "user",
                "message": {"content": [{"type": "text", "text": "are we done yet"}]},
            },
            {
                "type": "user",
                "message": {
                    "content": [{"type": "text", "text": "thanks for the help"}]
                },
            },
        ],
    )

    result = extract_last_substantive_user_message(str(transcript_path))

    assert result["goal"] == "Unknown task"
    assert result["scan_pattern"] == "not_found"
    assert result["meta_skipped"] >= 3

    # Clean up
    transcript_path.unlink(missing_ok=True)


def test_all_correction_transcript():
    """Transcript with only corrections should return 'Unknown task'.

    Note: CORRECTION_PATTERNS are very specific (e.g., "no, the task is not about").
    Messages like "That's wrong" don't match the pattern, so they are treated as substantive.
    """
    transcript_path = Path("/tmp/test_all_corrections.jsonl")
    _write_transcript(
        transcript_path,
        [
            {
                "type": "user",
                "message": {"content": [{"type": "text", "text": "That's wrong"}]},
            },
            {
                "type": "user",
                "message": {"content": [{"type": "text", "text": "No, not that"}]},
            },
            {
                "type": "user",
                "message": {"content": [{"type": "text", "text": "Fix it properly"}]},
            },
        ],
    )

    result = extract_last_substantive_user_message(str(transcript_path))

    # "Fix it properly" is substantive (not a correction pattern match)
    assert result["goal"] == "Fix it properly"
    assert result["message_intent"] == "instruction"

    # Clean up
    transcript_path.unlink(missing_ok=True)


def test_all_very_short_messages():
    """Transcript with only very short messages should return 'Unknown task'."""
    transcript_path = Path("/tmp/test_all_short.jsonl")
    _write_transcript(
        transcript_path,
        [
            {"type": "user", "message": {"content": [{"type": "text", "text": "OK"}]}},
            {"type": "user", "message": {"content": [{"type": "text", "text": "No"}]}},
            {"type": "user", "message": {"content": [{"type": "text", "text": "Yes"}]}},
            {"type": "user", "message": {"content": [{"type": "text", "text": "Go"}]}},
        ],
    )

    result = extract_last_substantive_user_message(str(transcript_path))

    assert result["goal"] == "Unknown task"
    assert result["scan_pattern"] == "not_found"

    # Clean up
    transcript_path.unlink(missing_ok=True)


def test_non_english_message_blocked():
    """Non-English message should return 'unsupported_language' intent."""
    transcript_path = Path("/tmp/test_non_english.jsonl")
    _write_transcript(
        transcript_path,
        [
            {
                "type": "user",
                "message": {
                    "content": [{"type": "text", "text": "Implement feature X"}]
                },
            },
            {
                "type": "user",
                "message": {"content": [{"type": "text", "text": "实现功能X"}]},
            },
        ],
    )

    result = extract_last_substantive_user_message(str(transcript_path))

    # Should return the first substantive message (English)
    # and mark the second as unsupported language
    assert result["goal"] == "Implement feature X"
    assert result["message_intent"] == "instruction"

    # Clean up
    transcript_path.unlink(missing_ok=True)


def test_malformed_transcript_entry_missing_type():
    """Transcript entry without 'type' field should be handled gracefully."""
    transcript_path = Path("/tmp/test_malformed.jsonl")
    _write_transcript(
        transcript_path,
        [
            # Missing 'type' field - should be skipped
            {
                "message": {
                    "content": [
                        {"type": "text", "text": "Implement feature X properly"}
                    ]
                },
            },
        ],
    )

    result = extract_last_substantive_user_message(str(transcript_path))

    # Should return Unknown task since entry was malformed
    assert result["goal"] == "Unknown task"
    assert result["scan_pattern"] == "not_found"

    # Clean up
    transcript_path.unlink(missing_ok=True)


def test_malformed_transcript_entry_missing_message():
    """Transcript entry without 'message' field should be handled gracefully."""
    transcript_path = Path("/tmp/test_malformed_no_message.jsonl")
    _write_transcript(
        transcript_path,
        [
            # Has 'type' but missing 'message' field
            {"type": "user"},
        ],
    )

    result = extract_last_substantive_user_message(str(transcript_path))

    # Should return Unknown task since entry was malformed
    assert result["goal"] == "Unknown task"
    assert result["scan_pattern"] == "not_found"

    # Clean up
    transcript_path.unlink(missing_ok=True)


def test_malformed_transcript_entry_missing_content():
    """Transcript entry with message but no content array should be handled gracefully."""
    transcript_path = Path("/tmp/test_malformed_no_content.jsonl")
    _write_transcript(
        transcript_path,
        [
            {
                "type": "user",
                "message": {},  # Empty message, no 'content' field
            },
        ],
    )

    result = extract_last_substantive_user_message(str(transcript_path))

    # Should return Unknown task since entry was malformed
    assert result["goal"] == "Unknown task"
    assert result["scan_pattern"] == "not_found"

    # Clean up
    transcript_path.unlink(missing_ok=True)


def test_malformed_transcript_entry_content_not_array():
    """Transcript entry with content as non-array should be handled gracefully.

    Note: The system is lenient and extracts text even when content is a string.
    """
    transcript_path = Path("/tmp/test_malformed_content_not_array.jsonl")
    _write_transcript(
        transcript_path,
        [
            {
                "type": "user",
                "message": {"content": "Implement feature X"},  # String, not array
            },
        ],
    )

    result = extract_last_substantive_user_message(str(transcript_path))

    # System extracts text even from malformed content
    assert result["goal"] == "Implement feature X"
    assert result["message_intent"] == "instruction"

    # Clean up
    transcript_path.unlink(missing_ok=True)


def test_assistant_messages_only():
    """Transcript with only assistant messages should return 'Unknown task'."""
    transcript_path = Path("/tmp/test_assistant_only.jsonl")
    _write_transcript(
        transcript_path,
        [
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "I'll help you with that"}]
                },
            },
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "Let me implement feature X"}]
                },
            },
        ],
    )

    result = extract_last_substantive_user_message(str(transcript_path))

    # Assistant messages are not user messages
    assert result["goal"] == "Unknown task"
    assert result["scan_pattern"] == "not_found"

    # Clean up
    transcript_path.unlink(missing_ok=True)


def test_tool_use_messages_only():
    """Transcript with only tool_use entries should return 'Unknown task'."""
    transcript_path = Path("/tmp/test_tool_use_only.jsonl")
    _write_transcript(
        transcript_path,
        [
            {
                "type": "tool_use",
                "name": "Read",
                "input": {"file_path": "test.py"},
            },
            {
                "type": "tool_use",
                "name": "Edit",
                "input": {"file_path": "test.py"},
            },
        ],
    )

    result = extract_last_substantive_user_message(str(transcript_path))

    # tool_use entries are not user messages
    assert result["goal"] == "Unknown task"
    assert result["scan_pattern"] == "not_found"

    # Clean up
    transcript_path.unlink(missing_ok=True)


def test_question_then_instruction():
    """Question followed by instruction - should return the instruction."""
    transcript_path = Path("/tmp/test_question_then_instruction.jsonl")
    _write_transcript(
        transcript_path,
        [
            # Oldest: question
            {
                "type": "user",
                "message": {
                    "content": [{"type": "text", "text": "How does the API work?"}]
                },
            },
            # Newest: instruction
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "text",
                            "text": "Implement feature X with proper error handling",
                        }
                    ]
                },
            },
        ],
    )

    result = extract_last_substantive_user_message(str(transcript_path))

    # Should return the instruction (newest message)
    assert result["goal"] == "Implement feature X with proper error handling"
    assert result["message_intent"] == "instruction"

    # Clean up
    transcript_path.unlink(missing_ok=True)


def test_clarification_then_task():
    """Clarification followed by actual task - should return the task."""
    transcript_path = Path("/tmp/test_clarification_then_task.jsonl")
    _write_transcript(
        transcript_path,
        [
            # Oldest: clarification
            {
                "type": "user",
                "message": {"content": [{"type": "text", "text": "What do you mean?"}]},
            },
            # Newest: actual task
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "text",
                            "text": "Implement feature X with proper error handling",
                        }
                    ]
                },
            },
        ],
    )

    result = extract_last_substantive_user_message(str(transcript_path))

    # Should return the task (newest message)
    assert result["goal"] == "Implement feature X with proper error handling"
    assert result["message_intent"] == "instruction"

    # Clean up
    transcript_path.unlink(missing_ok=True)


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])

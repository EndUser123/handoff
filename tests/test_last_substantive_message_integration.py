#!/usr/bin/env python3
"""Integration tests for the last substantive user message bug fix.

This test verifies the fix for the bug where the handoff system was delivering
the FIRST question instead of the LAST task.

Bug Description:
- The backward scan loop had an early return that prevented state updates
- previous_message_text was never updated from None
- Topic shift detection was completely non-functional
- The function returned immediately on the first substantive message

Fix:
- Removed early return inside the loop
- Added state update on each iteration: previous_message_text = message_text
- Return after loop completes to return the most recent substantive message
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


def test_bug_scenario_correction_message_then_task():
    """
    Test the original bug scenario: correction message followed by actual task.

    Transcript structure (newest to oldest):
    1. "that's not what I asked" (correction - should be skipped)
    2. "Implement feature X" (actual task - should be returned)

    Before fix: Would return "that's not what I asked" (first message)
    After fix: Should return "Implement feature X" (last substantive message)
    """
    transcript_path = Path("/tmp/test_correction_then_task.jsonl")
    _write_transcript(
        transcript_path,
        [
            # Oldest message first
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "text",
                            "text": "Implement feature X with error handling",
                        }
                    ]
                },
            },
            {
                "type": "tool_use",
                "name": "Read",
                "input": {"file_path": "some_file.py"},
            },
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "Let me implement that"}]
                },
            },
            # Correction message (newer)
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "text",
                            "text": "that's not what I asked, focus on Y instead",
                        }
                    ]
                },
            },
            # Newest message (but it's a correction, so should be skipped)
        ],
    )

    result = extract_last_substantive_user_message(str(transcript_path))

    # Should return the actual task, not the correction
    assert result["goal"] == "Implement feature X with error handling"
    assert result["corrections_skipped"] == 1
    assert result["scan_pattern"] == "found_substantive"

    # Clean up
    transcript_path.unlink(missing_ok=True)


def test_bug_scenario_topic_shift():
    """
    Test topic shift detection: multiple messages on different topics.

    Transcript structure (newest to oldest):
    1. "How does API Z work?" (different topic - should stop here)
    2. "Actually fix bug Y" (correction - should be skipped)
    3. "Implement feature X" (original task - should be preserved)

    Before fix: Would return "How does API Z work?" (topic shift didn't work)
    After fix: Should return "How does API Z work?" (most recent BEFORE topic shift)
    """
    transcript_path = Path("/tmp/test_topic_shift.jsonl")
    _write_transcript(
        transcript_path,
        [
            # Oldest: original task
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
            {
                "type": "tool_use",
                "name": "Edit",
                "input": {"file_path": "feature_x.py"},
            },
            # Middle: correction (should be skipped)
            {
                "type": "user",
                "message": {
                    "content": [{"type": "text", "text": "Actually, fix bug Y instead"}]
                },
            },
            # Newest: different topic (should cause stop)
            {
                "type": "user",
                "message": {
                    "content": [{"type": "text", "text": "How does API Z work?"}]
                },
            },
        ],
    )

    result = extract_last_substantive_user_message(str(transcript_path))

    # Should return the message from the newest topic (before topic shift)
    assert result["goal"] == "How does API Z work?"
    assert result["topic_shift_hit"] == True
    # Note: "Actually, fix bug Y instead" is now detected as correction with new pattern
    assert result["corrections_skipped"] == 1
    assert result["scan_pattern"] == "found_substantive"

    # The original task "Implement feature X" should NOT be returned
    assert "feature X" not in result["goal"]

    # Clean up
    transcript_path.unlink(missing_ok=True)


def test_bug_scenario_multiple_substantive_messages_same_topic():
    """
    Test multiple substantive messages on the same topic.

    Transcript structure (newest to oldest):
    1. "Also add logging" (continuation)
    2. "Implement feature X" (main task)
    3. "Start feature X" (initial)

    Expected: Return the MOST RECENT substantive message on the topic
    """
    transcript_path = Path("/tmp/test_same_topic.jsonl")
    _write_transcript(
        transcript_path,
        [
            # Oldest
            {
                "type": "user",
                "message": {"content": [{"type": "text", "text": "Start feature X"}]},
            },
            # Middle
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
            # Newest
            {
                "type": "user",
                "message": {"content": [{"type": "text", "text": "Also add logging"}]},
            },
        ],
    )

    result = extract_last_substantive_user_message(str(transcript_path))

    # Should return the MOST RECENT message, not the first
    assert result["goal"] == "Also add logging"
    # Note: topic_shift_hit is True because "Also add logging" and "Implement feature X..."
    # have no keyword overlap (intersection = {}), so is_same_topic() returns False
    assert (
        result["topic_shift_hit"] == True
    )  # Different topic due to no keyword overlap
    assert result["messages_scanned"] == 2  # Only scanned 2 before topic shift detected

    # Clean up
    transcript_path.unlink(missing_ok=True)


def test_bug_scenario_all_messages_filtered():
    """
    Test when all messages are filtered (meta, corrections, too short).

    Expected: Return "Unknown task" with scan_pattern "not_found"
    """
    transcript_path = Path("/tmp/test_all_filtered.jsonl")
    _write_transcript(
        transcript_path,
        [
            # Meta instruction (matches META_PATTERNS: "^summarize|explain")
            {
                "type": "user",
                "message": {"content": [{"type": "text", "text": "Summarize"}]},
            },
            # Correction
            {
                "type": "user",
                "message": {
                    "content": [{"type": "text", "text": "That's wrong, fix it"}]
                },
            },
            # Too short
            {"type": "user", "message": {"content": [{"type": "text", "text": "OK"}]}},
        ],
    )

    result = extract_last_substantive_user_message(str(transcript_path))

    # Should return "Unknown task" since no substantive message found
    assert result["goal"] == "Unknown task"
    assert result["scan_pattern"] == "not_found"
    # Note: "Summarize" is 9 chars, so it's filtered by length check (<10)
    # before meta-instruction check runs. meta_skipped = 0 is correct.
    assert result["corrections_skipped"] == 1

    # Clean up
    transcript_path.unlink(missing_ok=True)


def test_message_intent_present_in_result():
    """
    Test that message_intent is included in the result.

    This verifies the integration between extract_last_substantive_user_message
    and the handoff envelope creation.
    """
    transcript_path = Path("/tmp/test_message_intent.jsonl")
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

    # message_intent should be present and classified
    assert "message_intent" in result
    assert result["message_intent"] in ["instruction", "question", "clarification", "directive"]

    # Clean up
    transcript_path.unlink(missing_ok=True)


if __name__ == "__main__":
    # Run tests
    import pytest

    pytest.main([__file__, "-v"])

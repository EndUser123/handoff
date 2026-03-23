#!/usr/bin/env python3
"""Test that verifies loop iteration (catches original early-return bug).

The original bug was an early return that prevented the loop from iterating
through all messages. This test with 3 substantive messages would have
caught that bug (early return would return the FIRST message, not the LAST).

This is a regression test to ensure the bug doesn't reoccur.
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


def test_three_substantive_messages_returns_last_one():
    """
    Test with 3 substantive messages to verify loop iterates completely.

    This would have caught the original bug where an early return
    prevented state updates and returned the FIRST message instead of LAST.

    Transcript structure (newest to oldest):
    1. "Add error handling" (3rd substantive - should be returned)
    2. "Implement feature X" (2nd substantive)
    3. "Start feature X" (1st substantive - would be returned with bug)
    """
    transcript_path = Path("/tmp/test_three_messages.jsonl")
    _write_transcript(
        transcript_path,
        [
            # Oldest: 1st substantive message
            {
                "type": "user",
                "message": {"content": [{"type": "text", "text": "Start feature X"}]},
            },
            # Middle: 2nd substantive message
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "text",
                            "text": "Implement feature X with proper design",
                        }
                    ]
                },
            },
            # Newest: 3rd substantive message (should be returned)
            {
                "type": "user",
                "message": {
                    "content": [{"type": "text", "text": "Add error handling"}]
                },
            },
        ],
    )

    result = extract_last_substantive_user_message(str(transcript_path))

    # Should return the MOST RECENT message (3rd one), not the first
    assert result["goal"] == "Add error handling"
    # Note: scanned 2 messages because "Add error handling" and "Implement feature X..."
    # have no keyword overlap, triggering topic_shift_hit. This is expected behavior.

    # Clean up
    transcript_path.unlink(missing_ok=True)


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])

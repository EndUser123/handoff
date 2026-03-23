#!/usr/bin/env python3
"""Test last user message extraction from transcript."""

import sys
import json
from pathlib import Path

# Add handoff package to path
HANDOFF_PACKAGE = Path(__file__).parent.parent / "core"
sys.path.insert(0, str(HANDOFF_PACKAGE))

from core.hooks.__lib.transcript import TranscriptParser


def test_last_user_message_full_transcript():
    """Test that last user message is extracted even when it's not in the last 20 lines."""

    # Simulate a LONG transcript (100 entries) where the last user message
    # is NOT in the last 20 entries
    synthetic_entries = []

    # Add 50 filler entries (tool_use, assistant responses)
    for i in range(50):
        synthetic_entries.append(
            {"type": "assistant", "message": {"content": [f"Response {i}"]}}
        )

    # The ACTUAL last user message (at position 50)
    synthetic_entries.append(
        {
            "type": "user",
            "message": {
                "content": ["this is my actual last command - fix the handoff bug"]
            },
        }
    )

    # Add 49 more filler entries after it (simulating system messages, etc.)
    for i in range(51, 100):
        synthetic_entries.append(
            {
                "type": "tool_use" if i % 2 == 0 else "assistant",
                "name": "some_tool",
                "message": {"content": [f"Filler {i}"]},
            }
        )

    # Write to temp file
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for entry in synthetic_entries:
            f.write(json.dumps(entry) + "\n")
        temp_path = f.name

    try:
        parser = TranscriptParser(temp_path)
        last_message = parser.extract_last_user_message()

        print("Long transcript test (100 entries, user msg at position 50):")
        print(f"  Result: {last_message}")

        if last_message == "this is my actual last command - fix the handoff bug":
            print(
                "  ✓ PASS: Correctly extracted user message from middle of transcript"
            )
            print(
                "    (Would have been missed by 20-line scan which only looks at lines 80-100)"
            )
            return True
        else:
            print(f"  ✗ FAIL: Got '{last_message}' instead of expected message")
            return False
    finally:
        import os

        os.unlink(temp_path)


def test_last_user_message_skips_meta_tags():
    """Test that meta tags and system messages are skipped."""

    synthetic_entries = [
        # System/meta content that should be skipped
        {"type": "user", "message": {"content": ["<system_message>"]}},
        {
            "type": "user",
            "message": {"content": ["This session is being continued from compaction"]},
        },
        {"type": "user", "message": {"content": ["Stop hook feedback: blah blah"]}},
        {
            "type": "user",
            "message": {"content": ["hi"]},
        },  # Too short (< MIN_CONTENT_LENGTH)
        # The ACTUAL last substantial user message
        {"type": "user", "message": {"content": ["run the tests to verify the fix"]}},
    ]

    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for entry in synthetic_entries:
            f.write(json.dumps(entry) + "\n")
        temp_path = f.name

    try:
        parser = TranscriptParser(temp_path)
        last_message = parser.extract_last_user_message()

        print("\nMeta tag filtering test:")
        print(f"  Result: {last_message}")

        if last_message == "run the tests to verify the fix":
            print("  ✓ PASS: Correctly skipped meta tags and short messages")
            return True
        else:
            print(f"  ✗ FAIL: Got '{last_message}' instead of expected message")
            return False
    finally:
        import os

        os.unlink(temp_path)


def test_last_user_message_untruncated():
    """Test that the FULL message is returned, not truncated to 200 chars."""

    # A long message (>200 chars)
    long_message = "please investigate the handoff system because it's not preserving my last command correctly and the LLM after compaction doesn't know what it was working on which is really frustrating because I need to maintain context across sessions"

    synthetic_entries = [{"type": "user", "message": {"content": [long_message]}}]

    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for entry in synthetic_entries:
            f.write(json.dumps(entry) + "\n")
        temp_path = f.name

    try:
        parser = TranscriptParser(temp_path)
        last_message = parser.extract_last_user_message()

        print("\nUntruncated message test:")
        print(f"  Expected length: {len(long_message)}")
        print(f"  Actual length: {len(last_message) if last_message else 0}")

        if last_message == long_message:
            print("  ✓ PASS: Full message returned (not truncated)")
            return True
        else:
            print("  ✗ FAIL: Message was truncated or modified")
            print(f"    Expected: '{long_message[:50]}...'")
            print(f"    Got: '{last_message[:50] if last_message else 'None'}...'")
            return False
    finally:
        import os

        os.unlink(temp_path)


def test_last_user_message_skips_dict_items():
    """Test that dict items (tool_result, thinking blocks) are skipped - only strings extracted."""

    # Simulate a user message with mixed content: tool_result dict + actual string
    # This is the bug case: assistant thinking embedded in user message via tool_result
    synthetic_entries = [
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "tool_use_id": "call_abc123",
                        "type": "tool_result",
                        "content": "why is it called arch-skill? shouldn't it just be arch?",  # Assistant thinking in tool result
                        "is_error": False,
                    },
                    "this is the actual user text that should be extracted",  # Real user input
                ]
            },
        }
    ]

    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for entry in synthetic_entries:
            f.write(json.dumps(entry) + "\n")
        temp_path = f.name

    try:
        parser = TranscriptParser(temp_path)
        last_message = parser.extract_last_user_message()

        print("\nDict item filtering test (fix for handoff bug):")
        print(f"  Result: {last_message}")

        # Should extract the user text, NOT the tool_result content
        if last_message == "this is the actual user text that should be extracted":
            print(
                "  ✓ PASS: Correctly skipped dict items (tool_result) and extracted user text"
            )
            print(
                "    (Fixed bug where assistant thinking in tool_result was extracted)"
            )
            return True
        else:
            print(f"  ✗ FAIL: Got '{last_message}' instead of expected user text")
            print("    (BUG: Dict items not being skipped properly)")
            return False
    finally:
        import os

        os.unlink(temp_path)


if __name__ == "__main__":
    results = [
        test_last_user_message_full_transcript(),
        test_last_user_message_skips_meta_tags(),
        test_last_user_message_untruncated(),
        test_last_user_message_skips_dict_items(),  # New test for the fix
    ]

    print(f"\n{'=' * 50}")
    print(f"Results: {sum(results)}/{len(results)} tests passed")
    sys.exit(0 if all(results) else 1)

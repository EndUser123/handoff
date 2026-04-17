#!/usr/bin/env python3
"""Tests for improved canonical_goal extraction.

Tests Phase 2 improvements:
- Extract last substantive user message (works backwards from end)
- Skip meta-instructions ("thanks", "summarize", "explain", "revert", "rollback")
- Stop at session boundaries (session_chain_id change)
- Stop at topic shifts (semantic similarity < 30%)
- Handle side-threads

Test Scenarios:
- Case 1: Last message is meta-instruction → Skip "thanks", extract previous substantive message
- Case 2: Side question before task completion → Skip side question, extract main task
- Case 3: Session boundary in middle of transcript → Only gather messages after last session boundary
"""

import json
import sys
import tempfile
from pathlib import Path

# Add handoff package to path
HANDOFF_PACKAGE = Path(__file__).parent.parent
sys.path.insert(0, str(HANDOFF_PACKAGE))

from core.hooks.__lib.transcript import (
    detect_session_boundary,
    extract_last_substantive_user_message,
    is_meta_instruction,
    is_same_topic,
)


def create_test_transcript(entries, output_path):
    """Create a test transcript JSONL file.

    Args:
        entries: List of entry dicts
        output_path: Path to write transcript
    """
    with open(output_path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def test_case_1_skip_meta_instructions():
    """Case 1: Last message is meta-instruction → Skip "thanks", extract previous substantive message.

    Expected: Extract "Fix the authentication bug", not "Thanks for your help"
    """
    entries = [
        {
            "type": "user",
            "message": {"content": ["Fix the authentication bug"]},
            "timestamp": "2026-03-08T12:00:00Z",
        },
        {
            "type": "assistant",
            "message": {"content": ["I'll help you fix the authentication bug"]},
            "timestamp": "2026-03-08T12:00:01Z",
        },
        {
            "type": "user",
            "message": {"content": ["Thanks for your help"]},
            "timestamp": "2026-03-08T12:00:02Z",
        },
    ]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        temp_path = f.name

    try:
        create_test_transcript(entries, temp_path)
        result = extract_last_substantive_user_message(temp_path)

        print("Case 1 - Skip meta-instructions:")
        print(f"  Result: {result}")
        expected = "Fix the authentication bug"
        if result == expected:
            print(
                "  ✓ PASS: Correctly skipped 'thanks' and extracted substantive message"
            )
            return True
        else:
            print(f"  ✗ FAIL: Expected '{expected}', got '{result}'")
            return False
    finally:
        Path(temp_path).unlink()


def test_case_2_skip_side_question():
    """Case 2: Side question before task completion → Skip side question, extract main task.

    Expected: Extract "Continue debugging", not "Quick question: what's the weather?"
    """
    entries = [
        {
            "type": "user",
            "message": {"content": ["Debug the authentication issue"]},
            "timestamp": "2026-03-08T12:00:00Z",
        },
        {
            "type": "assistant",
            "message": {"content": ["I'm investigating the authentication issue"]},
            "timestamp": "2026-03-08T12:00:01Z",
        },
        {
            "type": "user",
            "message": {"content": ["Quick question: what's the weather?"]},
            "timestamp": "2026-03-08T12:00:02Z",
        },
        {
            "type": "assistant",
            "message": {"content": ["It's sunny, 75°F"]},
            "timestamp": "2026-03-08T12:00:03Z",
        },
        {
            "type": "user",
            "message": {"content": ["Continue debugging"]},
            "timestamp": "2026-03-08T12:00:04Z",
        },
    ]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        temp_path = f.name

    try:
        create_test_transcript(entries, temp_path)
        result = extract_last_substantive_user_message(temp_path)

        print("\nCase 2 - Skip side question:")
        print(f"  Result: {result}")
        expected = "Continue debugging"
        if result == expected:
            print("  ✓ PASS: Correctly skipped side question and extracted main task")
            return True
        else:
            print(f"  ✗ FAIL: Expected '{expected}', got '{result}'")
            return False
    finally:
        Path(temp_path).unlink()


def test_case_3_session_boundary():
    """Case 3: Session boundary in middle of transcript → Only gather messages after last session boundary.

    Expected: Extract "Write tests for new feature", not "Fix the old bug"
    """
    entries = [
        {
            "type": "user",
            "message": {"content": ["Fix the old bug"]},
            "timestamp": "2026-03-08T12:00:00Z",
            "session_chain_id": "session-1",
        },
        {
            "type": "assistant",
            "message": {"content": ["I'll fix the bug"]},
            "timestamp": "2026-03-08T12:00:01Z",
            "session_chain_id": "session-1",
        },
        # Session boundary here - session_chain_id changes
        {
            "type": "user",
            "message": {"content": ["Write tests for new feature"]},
            "timestamp": "2026-03-08T12:00:02Z",
            "session_chain_id": "session-2",  # Different session
        },
        {
            "type": "assistant",
            "message": {"content": ["I'll write tests"]},
            "timestamp": "2026-03-08T12:00:03Z",
            "session_chain_id": "session-2",
        },
    ]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        temp_path = f.name

    try:
        create_test_transcript(entries, temp_path)
        result = extract_last_substantive_user_message(temp_path)

        print("\nCase 3 - Session boundary detection:")
        print(f"  Result: {result}")
        expected = "Write tests for new feature"
        if result == expected:
            print("  ✓ PASS: Correctly stopped at session boundary")
            return True
        else:
            print(f"  ✗ FAIL: Expected '{expected}', got '{result}'")
            return False
    finally:
        Path(temp_path).unlink()


def test_is_meta_instruction():
    """Test is_meta_instruction helper function."""
    test_cases = [
        ("thanks", True),
        ("thank you", True),
        ("summarize the session", True),
        ("explain the code", True),
        ("revert the changes", True),
        ("rollback to previous version", True),
        ("that's all", True),
        ("done", True),
        ("finish", True),
        ("Fix the authentication bug", False),
        ("Continue debugging", False),
        ("Write tests", False),
    ]

    print("\nTesting is_meta_instruction helper:")
    results = []
    for message, expected in test_cases:
        result = is_meta_instruction(message)
        status = "✓" if result == expected else "✗"
        print(f"  {status} '{message}': {result} (expected {expected})")
        results.append(result == expected)

    return all(results)


def test_is_same_topic():
    """Test is_same_topic helper function with keyword overlap.

    Uses threshold > 30% keyword overlap.
    """
    test_cases = [
        # High overlap (> 30%) → same topic
        ("Fix authentication bug", "Fix authentication in login", True),
        # Low overlap (< 30%) → different topic
        ("Debug the issue", "Continue debugging", False),  # Only "debug" overlaps (25%)
        ("Fix authentication bug", "Write tests for feature", False),
        ("What's the weather", "Debug the code", False),
        # Edge cases
        ("test", "testing", False),  # Different words (0% overlap)
        ("", "Any message", False),  # Empty string
    ]

    print("\nTesting is_same_topic helper:")
    results = []
    for msg1, msg2, expected in test_cases:
        result = is_same_topic(msg1, msg2)
        status = "✓" if result == expected else "✗"
        print(f"  {status} '{msg1}' vs '{msg2}': {result} (expected {expected})")
        results.append(result == expected)

    return all(results)


def test_detect_session_boundary():
    """Test detect_session_boundary helper function."""
    test_cases = [
        # session_chain_id change → boundary
        ({"session_chain_id": "session-1"}, {"session_chain_id": "session-2"}, True),
        # Same session_chain_id → no boundary
        ({"session_chain_id": "session-1"}, {"session_chain_id": "session-1"}, False),
        # Missing session_chain_id → no boundary (graceful degradation)
        ({"type": "user"}, {"type": "assistant"}, False),
    ]

    print("\nTesting detect_session_boundary helper:")
    results = []
    for entry1, entry2, expected in test_cases:
        result = detect_session_boundary(entry2, entry1)
        status = "✓" if result == expected else "✗"
        print(
            f"  {status} {entry1.get('session_chain_id', 'None')} → {entry2.get('session_chain_id', 'None')}: {result} (expected {expected})"
        )
        results.append(result == expected)

    return all(results)


def test_performance_1000_entries():
    """Performance test: 1000-entry transcript should complete in < 100ms."""
    import time

    # Create 1000 synthetic entries
    entries = []
    for i in range(1000):
        entries.append(
            {
                "type": "user",
                "message": {"content": [f"Test message {i}"]},
                "timestamp": "2026-03-08T12:00:00Z",
            }
        )

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        temp_path = f.name

    try:
        create_test_transcript(entries, temp_path)

        start = time.perf_counter()
        result = extract_last_substantive_user_message(temp_path)
        elapsed = time.perf_counter() - start

        print("\nPerformance test (1000 entries):")
        print(f"  Result: {result}")
        print(f"  Time: {elapsed * 1000:.2f}ms")

        if elapsed < 0.100:  # < 100ms target
            print("  ✓ PASS: Performance target met (< 100ms)")
            return True
        else:
            print(f"  ✗ FAIL: Too slow: {elapsed * 1000:.2f}ms (target: <100ms)")
            return False
    finally:
        Path(temp_path).unlink()


def test_case_4_same_topic_returns_newest():
    """Regression test for #94: Two same-topic messages must return the LATEST, not the oldest.

    The backward scan finds message B (newest) first, then message A (older, same topic).
    Before the fix, previous_message_text was overwritten with A, so the goal was A.
    After the fix, first_substantive_message captures B and is returned.
    """
    entries = [
        {
            "type": "user",
            "message": {"content": ["Fix the handoff checksum validation bug in transcript.py"]},
            "timestamp": "2026-04-17T10:00:00Z",
        },
        {
            "type": "assistant",
            "message": {"content": ["I'll fix the checksum validation bug"]},
            "timestamp": "2026-04-17T10:00:01Z",
        },
        # Second user message on same topic (high keyword overlap with first)
        {
            "type": "user",
            "message": {"content": ["Update the handoff checksum validation to handle edge cases in transcript.py"]},
            "timestamp": "2026-04-17T11:00:00Z",
        },
        {
            "type": "assistant",
            "message": {"content": ["I'll update the checksum validation for edge cases"]},
            "timestamp": "2026-04-17T11:00:01Z",
        },
    ]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        temp_path = f.name

    try:
        create_test_transcript(entries, temp_path)
        result = extract_last_substantive_user_message(temp_path)

        expected = "Update the handoff checksum validation to handle edge cases in transcript.py"
        actual = result.get("goal", "") if isinstance(result, dict) else result
        assert actual == expected, (
            f"Expected LATEST same-topic message but got: {actual}"
        )
    finally:
        Path(temp_path).unlink()


if __name__ == "__main__":
    results = [
        test_case_1_skip_meta_instructions(),
        test_case_2_skip_side_question(),
        test_case_3_session_boundary(),
        test_case_4_same_topic_returns_newest(),
        test_is_meta_instruction(),
        test_is_same_topic(),
        test_detect_session_boundary(),
        test_performance_1000_entries(),
    ]

    print(f"\n{'=' * 60}")
    print(f"Results: {sum(results)}/{len(results)} tests passed")
    sys.exit(0 if all(results) else 1)

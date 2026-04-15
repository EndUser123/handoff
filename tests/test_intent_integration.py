"""Integration tests for handoff intent classification feature.

Tests the end-to-end flow from transcript to handoff capture,
including intent detection, prefix formatting, and concurrent access.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import threading
from pathlib import Path


# Load the transcript module directly
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPT_PATH = PACKAGE_ROOT / "scripts" / "hooks" / "__lib" / "transcript.py"

spec = importlib.util.spec_from_file_location("transcript", TRANSCRIPT_PATH)
transcript = importlib.util.module_from_spec(spec)
sys.modules["transcript"] = transcript
spec.loader.exec_module(transcript)

# Load handoff_v2 module
HANDOFF_V2_PATH = PACKAGE_ROOT / "scripts" / "hooks" / "__lib" / "handoff_v2.py"

spec2 = importlib.util.spec_from_file_location("handoff_v2", HANDOFF_V2_PATH)
handoff_v2 = importlib.util.module_from_spec(spec2)
sys.modules["handoff_v2"] = handoff_v2
spec2.loader.exec_module(handoff_v2)

# Import required functions
extract_last_substantive_user_message = transcript.extract_last_substantive_user_message
detect_message_intent = transcript.detect_message_intent
build_restore_message = handoff_v2.build_restore_message
build_resume_snapshot = handoff_v2.build_resume_snapshot
build_envelope = handoff_v2.build_envelope


def create_test_transcript_with_message(
    message: str, temp_dir: Path, filename: str = "test_transcript.jsonl"
) -> Path:
    """Create a minimal test transcript with a single user message.

    Args:
        message: The user message to include in the transcript
        temp_dir: Temporary directory for the transcript
        filename: Optional filename for the transcript (defaults to test_transcript.jsonl)

    Returns:
        Path to the created transcript file
    """
    transcript_file = temp_dir / filename

    # Use list format for content (matches real transcript structure)
    transcript_entry = {
        "type": "user",
        "message": {
            "content": [message],
        },
        "timestamp": "2026-03-20T00:00:00Z",
    }

    with open(transcript_file, "w") as f:
        f.write(json.dumps(transcript_entry) + "\n")

    return transcript_file


def create_envelope_with_goal(goal: str, message_intent: str) -> dict:
    """Create a test handoff envelope with goal and intent.

    Args:
        goal: The goal message
        message_intent: The intent classification

    Returns:
        Complete handoff envelope
    """
    snapshot = build_resume_snapshot(
        terminal_id="test_terminal",
        source_session_id="test_session",
        goal=goal,
        current_task="Testing",
        progress_percent=50,
        progress_state="in_progress",
        blockers=[],
        active_files=[],
        pending_operations=[],
        next_step="Complete test",
        decision_refs=[],
        evidence_refs=[],
        transcript_path="test_transcript.jsonl",
        message_intent=message_intent,
    )

    return build_envelope(
        resume_snapshot=snapshot,
        decision_register=[],
        evidence_index=[],
    )


class TestADRMotivatingScenario:
    """Test the exact scenario from the ADR problem statement."""

    def test_adr_motivating_scenario(self):
        """Test the exact scenario from the ADR problem statement.

        The message "Do this this is going a little over board with the connector bullet?"
        should be classified as a question and prefixed with "User asked:".
        """
        # The exact message from the ADR motivating scenario
        message = "Do this this is going a little over board with the connector bullet?"

        # Create test transcript with this message
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            transcript_file = create_test_transcript_with_message(message, temp_path)

            # Extract goal with intent
            result = extract_last_substantive_user_message(transcript_file)

            # Verify intent classification
            assert result["message_intent"] == "question", (
                f"Expected 'question' but got '{result['message_intent']}' "
                f"for message: {message}"
            )

            # Verify the goal was extracted
            assert result["goal"] == message

            # Build envelope and verify prefix in restore message
            envelope = create_envelope_with_goal(
                result["goal"], result["message_intent"]
            )
            restore_message = build_restore_message(envelope)

            # Verify "User asked:" prefix is present
            assert "User asked:" in restore_message, (
                f"Expected 'User asked:' prefix in restore message, got:\n{restore_message}"
            )

            # Verify the full message is present
            assert message in restore_message, (
                f"Expected original message in restore message, got:\n{restore_message}"
            )


class TestPreCompactHookIntegration:
    """Test PreCompact hook integration with intent classification."""

    def test_precompact_captures_intent(self):
        """Verify PreCompact hook captures message_intent in handoff."""
        import tempfile

        # Create a transcript with a question
        question_message = "Is the authentication system working correctly?"
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            transcript_file = create_test_transcript_with_message(
                question_message, temp_path
            )

            # Simulate what PreCompact hook does - extract goal with intent
            result = extract_last_substantive_user_message(transcript_file)

            # Verify intent was captured
            assert result["message_intent"] == "question", (
                f"Expected 'question' intent but got '{result['message_intent']}'"
            )

            # Build snapshot with intent (simulates PreCompact hook)
            snapshot = build_resume_snapshot(
                terminal_id="test_terminal",
                source_session_id="test_session",
                goal=result["goal"],
                current_task="Testing",
                progress_percent=50,
                progress_state="in_progress",
                blockers=[],
                active_files=[],
                pending_operations=[],
                next_step="Complete test",
                decision_refs=[],
                evidence_refs=[],
                transcript_path=str(transcript_file),
                message_intent=result["message_intent"],
            )

            # Verify snapshot includes message_intent
            assert "message_intent" in snapshot, (
                "Snapshot should include message_intent"
            )
            assert snapshot["message_intent"] == "question"

            # Build envelope and verify restore message
            envelope = build_envelope(
                resume_snapshot=snapshot,
                decision_register=[],
                evidence_index=[],
            )
            restore_message = build_restore_message(envelope)

            # Verify "User asked:" prefix in restore message
            assert "User asked:" in restore_message, (
                f"Expected 'User asked:' prefix for question intent, got:\n{restore_message}"
            )

    def test_precompact_instruction_intent(self):
        """Verify PreCompact hook captures instruction intent correctly."""
        import tempfile

        # Create a transcript with an instruction
        instruction_message = "Fix the bug in the authentication module"
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            transcript_file = create_test_transcript_with_message(
                instruction_message, temp_path
            )

            # Extract goal with intent
            result = extract_last_substantive_user_message(transcript_file)

            # Verify intent was classified as directive (imperative command)
            assert result["message_intent"] == "directive", (
                f"Expected 'directive' intent but got '{result['message_intent']}'"
            )

            # Build snapshot and verify restore message has "User requested:" prefix
            snapshot = build_resume_snapshot(
                terminal_id="test_terminal",
                source_session_id="test_session",
                goal=result["goal"],
                current_task="Testing",
                progress_percent=50,
                progress_state="in_progress",
                blockers=[],
                active_files=[],
                pending_operations=[],
                next_step="Complete test",
                decision_refs=[],
                evidence_refs=[],
                transcript_path=str(transcript_file),
                message_intent=result["message_intent"],
            )

            envelope = build_envelope(
                resume_snapshot=snapshot,
                decision_register=[],
                evidence_index=[],
            )
            restore_message = build_restore_message(envelope)

            # Verify "User requested:" prefix for instruction
            assert "User requested:" in restore_message, (
                f"Expected 'User requested:' prefix for instruction intent, got:\n{restore_message}"
            )


class TestConcurrentHandoffCreation:
    """Test concurrent handoff creation with intent classification."""

    def test_concurrent_intent_detection(self):
        """Verify intent detection works under concurrent access."""
        import queue

        results = queue.Queue()

        def detect_intent(message: str):
            """Detect intent for a message."""
            intent = detect_message_intent(message)
            results.put(intent)

        # Test messages with different intents
        messages = [
            ("Fix the bug", "directive"),
            ("Is this working?", "question"),
            ("Update the component", "directive"),
            ("What is the status?", "question"),
        ]

        # Create threads for concurrent intent detection
        threads = [
            threading.Thread(target=detect_intent, args=(msg,)) for msg, _ in messages
        ]

        # Start all threads
        for t in threads:
            t.start()

        # Wait for all threads to complete
        for t in threads:
            t.join()

        # Verify all intents were detected correctly
        intents = [results.get() for _ in messages]
        expected_intents = [intent for _, intent in messages]
        assert intents == expected_intents, (
            f"Expected intents {expected_intents} but got {intents}"
        )

    def test_concurrent_same_message_intent(self):
        """Verify concurrent classification of same message produces same result."""
        message = "Is this working?"
        expected_intent = "question"
        results = []

        def detect_intent_wrapper():
            intent = detect_message_intent(message)
            results.append(intent)

        # Create multiple threads to detect the same message
        threads = [threading.Thread(target=detect_intent_wrapper) for _ in range(5)]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # Verify all results are identical
        assert len(set(results)) == 1, (
            f"Expected all results to be identical but got: {results}"
        )
        assert results[0] == expected_intent, (
            f"Expected '{expected_intent}' but got '{results[0]}'"
        )


class TestChecksumExclusionIntegration:
    """Test that message_intent is properly excluded from checksum computation."""

    def test_all_intent_values_produce_same_checksum(self):
        """Verify all intent values produce the same checksum (FM-002)."""
        # First, create a base snapshot with instruction intent
        base_params = {
            "terminal_id": "test_terminal",
            "source_session_id": "test_session",
            "goal": "Test goal",
            "current_task": "Testing",
            "progress_percent": 50,
            "progress_state": "in_progress",
            "blockers": [],
            "active_files": [],
            "pending_operations": [],
            "next_step": "Complete test",
            "decision_refs": [],
            "evidence_refs": [],
            "n_1_transcript_path": "test_transcript.jsonl",
            "n_2_transcript_path": None,
            "message_intent": "instruction",
        }

        base_snapshot = build_resume_snapshot(**base_params)
        base_envelope = build_envelope(
            resume_snapshot=base_snapshot,
            decision_register=[],
            evidence_index=[],
        )
        base_checksum = base_envelope["checksum"]

        # Now test all intent values with the SAME snapshot (just updating message_intent)
        intents = [
            "question",
            "instruction",
            "correction",
            "meta",
            "unsupported_language",
        ]
        for intent in intents:
            # Update the same snapshot with different intent
            snapshot = base_snapshot.copy()
            snapshot["message_intent"] = intent

            # Recompute checksum with updated snapshot
            envelope = build_envelope(
                resume_snapshot=snapshot,
                decision_register=[],
                evidence_index=[],
            )

            # All checksums should be identical (message_intent excluded)
            assert envelope["checksum"] == base_checksum, (
                f"Expected checksum {base_checksum} but got {envelope['checksum']} "
                f"for intent '{intent}'"
            )


class TestMessageTypeValidation:
    """Test type validation for message_intent values."""

    def test_unsupported_language_uses_blocked_prefix(self):
        """Verify unsupported_language intent shows [NON-ENGLISH MESSAGE BLOCKED] prefix."""
        snapshot = {
            "schema_version": 2,
            "snapshot_id": "test-snapshot",
            "terminal_id": "test_terminal",
            "source_session_id": "test_session",
            "created_at": "2026-03-20T00:00:00Z",
            "expires_at": "2026-03-20T01:00:00:00Z",
            "status": "pending",
            "goal": "修复这个bug",  # Chinese message
            "current_task": "Testing",
            "progress_percent": 50,
            "progress_state": "in_progress",
            "blockers": [],
            "active_files": [],
            "pending_operations": [],
            "next_step": "Complete test",
            "decision_refs": [],
            "evidence_refs": [],
            "n_1_transcript_path": "test_transcript.jsonl",
            "n_2_transcript_path": None,
            "message_intent": "unsupported_language",  # Non-English detected
        }

        envelope = build_envelope(
            resume_snapshot=snapshot,
            decision_register=[],
            evidence_index=[],
        )

        restore_message = build_restore_message(envelope)

        # Verify blocked prefix is used
        assert "[NON-ENGLISH MESSAGE BLOCKED]:" in restore_message

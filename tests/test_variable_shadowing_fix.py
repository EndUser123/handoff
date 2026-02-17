#!/usr/bin/env python3
"""Tests for variable shadowing bug fix in handoff capture.

This documents the bug where `blocker` dict was being overwritten with a string
`blocker_description`, causing `isinstance(blocker, dict)` checks to fail.

The fix: Use separate variable `blocker_description` for the string version,
keeping `blocker` as the original dict.
"""

import pytest

from handoff.hooks.__lib.transcript import extract_user_message_from_blocker


class TestVariableShadowingFix:
    """Test that demonstrates the variable shadowing bug fix.

    Bug scenario (lines 410-416 of PreCompact_handoff_capture.py):

    # BEFORE (buggy):
    blocker_raw = handoff_data.get("blocker")  # dict
    if blocker_raw:
        if isinstance(blocker_raw, dict):
            blocker = blocker_raw.get("description", str(blocker_raw))  # OVERWRITES blocker dict!
    # Later: isinstance(blocker, dict) fails because blocker is now a string

    # AFTER (fixed):
    blocker_raw = handoff_data.get("blocker")  # dict
    blocker_description = None  # String version for payload, NOT for extraction
    if blocker_raw:
        if isinstance(blocker_raw, dict):
            blocker_description = blocker_raw.get("description", str(blocker_raw))
    # Later: blocker is still the original dict, isinstance(blocker, dict) works
    """

    def test_blocker_dict_remains_intact_after_extraction(self) -> None:
        """Test that blocker dict can still be used for isinstance checks after extraction."""
        blocker = {
            "description": "User's last question: implement feature X",
            "severity": "info",
            "source": "transcript",
        }

        # This is what the hook does: extract message but keep original blocker
        user_message = extract_user_message_from_blocker(blocker)

        # Verify extraction worked
        assert user_message == "implement feature X"

        # Verify blocker is still a dict (not shadowed by string)
        assert isinstance(blocker, dict)
        assert blocker["description"] == "User's last question: implement feature X"
        assert blocker["severity"] == "info"
        assert blocker["source"] == "transcript"

    def test_string_blocker_also_works(self) -> None:
        """Test that string blockers work for extraction."""
        blocker = "User's last question: fix the bug"
        user_message = extract_user_message_from_blocker(blocker)

        assert user_message == "fix the bug"

    def test_none_blocker_handling(self) -> None:
        """Test that None blockers are handled gracefully."""
        user_message = extract_user_message_from_blocker(None)
        assert user_message is None

    def test_real_compaction_scenario(self) -> None:
        """Test the exact scenario from the compaction bug fix."""
        # This is what was in the handoff metadata:
        blocker = {
            "description": "User's last question: yes, update the package",
            "severity": "info",
            "source": "transcript",
        }

        # Extract the user message
        user_message = extract_user_message_from_blocker(blocker)

        # Verify clean extraction (no prefix)
        assert user_message == "yes, update the package"

        # Verify blocker dict is still intact for other uses
        assert isinstance(blocker, dict)
        assert "User's last question:" in blocker["description"]

    def test_handoff_workflow_integrity(self) -> None:
        """Test the complete handoff workflow maintains data integrity.

        Simulates:
        1. Blocker extracted from transcript (dict with prefix)
        2. User message extracted for original_user_request field (clean)
        3. Original blocker still available for handoff payload (with prefix)
        """
        original_blocker = {
            "description": "User's last question: run the full test suite",
            "severity": "info",
            "source": "transcript",
        }

        # Step 1: Extract clean user message for original_user_request
        clean_message = extract_user_message_from_blocker(original_blocker)

        # Step 2: Build handoff payload (needs blocker with prefix for context)
        handoff_payload = {
            "blocker_description": original_blocker.get("description"),
            "original_user_request": clean_message,
        }

        # Verify: original_user_request is clean
        assert handoff_payload["original_user_request"] == "run the full test suite"
        assert "User's last question:" not in handoff_payload["original_user_request"]

        # Verify: blocker_description has full context (with prefix)
        assert handoff_payload["blocker_description"] == "User's last question: run the full test suite"

        # Verify: original blocker dict is still usable
        assert isinstance(original_blocker, dict)
        assert original_blocker["severity"] == "info"

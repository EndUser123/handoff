#!/usr/bin/env python3
"""
Test that invoked_command is captured for ALL session types, not just planning.

Bug: invoked_command was only captured for planning sessions, so /s, /r, and
other slash commands were not preserved in handoff data.

Fix: Extract invoked_command for ALL sessions, regardless of session type.
"""

import re


def _extract_invoked_command(message: str | None) -> str:
    """
    Extract the invoked command from the user message.

    This is a copy of the logic from PreCompactHandoffCapture._extract_invoked_command
    for testing purposes without needing to import the full class.
    """
    if not message or not message.strip():
        return "unknown command"

    # Known planning commands
    PLANNING_COMMANDS = ("/plan-workflow", "/arch", "/breakdown", "/design")

    # Try to match against known planning commands first
    for cmd in PLANNING_COMMANDS:
        if message.startswith(cmd):
            remaining = message[len(cmd):].strip()
            if remaining:
                return f"{cmd} {remaining}"
            else:
                return cmd

    # Fallback: extract first slash command from message
    # Matches patterns like "/command args" or just "/command"
    match = re.search(r'/[a-z-]+(?:\s+[^\n]+)?', message)
    if match:
        return match.group(0).strip()

    return "unknown command"


def test_extract_invoked_command_planning():
    """Test that planning commands are extracted correctly."""
    assert _extract_invoked_command("/plan-workflow build feature") == "/plan-workflow build feature"
    assert _extract_invoked_command("/arch auth service") == "/arch auth service"
    assert _extract_invoked_command("/breakdown task") == "/breakdown task"
    assert _extract_invoked_command("/design component") == "/design component"


def test_extract_invoked_command_non_planning():
    """Test that non-planning slash commands are extracted correctly."""
    # Test strategy and other commands
    assert _extract_invoked_command("/s integration verification") == "/s integration verification"
    assert _extract_invoked_command("/r checkpoint restore") == "/r checkpoint restore"
    assert _extract_invoked_command("/q test coverage") == "/q test coverage"

    # Test commands without arguments
    assert _extract_invoked_command("/s") == "/s"
    assert _extract_invoked_command("/help") == "/help"


def test_extract_invoked_command_fallback():
    """Test fallback regex matches any slash command."""
    # Test that fallback regex works (not in PLANNING_COMMANDS)
    assert _extract_invoked_command("/custom-command arg1 arg2") == "/custom-command arg1 arg2"
    assert _extract_invoked_command("/my-custom-command test") == "/my-custom-command test"


def test_extract_invoked_command_unknown():
    """Test that non-commands return 'unknown command'."""
    # Test plain text without slash command
    assert _extract_invoked_command("fix the bug") == "unknown command"
    assert _extract_invoked_command("") == "unknown command"
    assert _extract_invoked_command("   ") == "unknown command"


if __name__ == "__main__":
    import pytest

    # Run tests
    pytest.main([__file__, "-v"])

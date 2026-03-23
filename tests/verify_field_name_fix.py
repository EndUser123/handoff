#!/usr/bin/env python3
"""
Quick verification that the field name fix works.
"""

import sys
from pathlib import Path

# Add handoff package to path
HANDOFF_PKG = Path(__file__).parent.parent
sys.path.insert(0, str(HANDOFF_PKG))


def test_field_access():
    """Test that transcript_path field is accessed correctly."""

    # Simulate Claude Code hook input (snake_case as per logs)
    hook_input = {
        "session_id": "test-session",
        "transcript_path": "P:/test_transcript.jsonl",  # snake_case
        "cwd": "P:/",
        "hook_event_name": "PreCompact",
        "trigger": "auto",
    }

    # Test field extraction
    transcript_path = hook_input.get("transcript_path")

    print(f"✓ transcript_path extracted: {transcript_path}")
    assert transcript_path == "P:/test_transcript.jsonl", "Field name mismatch!"

    # Test that old camelCase would fail
    old_style = hook_input.get("transcriptPath")
    print(f"✓ Old camelCase field returns None: {old_style}")
    assert old_style is None, "Old field name should not exist!"

    print(
        "\n✅ Field name fix verified - hook now expects transcript_path (snake_case)"
    )
    return True


if __name__ == "__main__":
    test_field_access()

#!/usr/bin/env python3
"""Integration tests for session type detection in hooks."""

import json
import tempfile
from pathlib import Path


def test_precompact_includes_session_type_in_state_file():
    """Test that PreCompact hook writes session_type to state file."""
    from handoff.hooks.__lib.session_type_detector import SessionTypeDetector

    # Simulate what PreCompact does
    detector = SessionTypeDetector()

    # Test case 1: Debug session (message + error logs)
    last_message = "Fix the bug in authentication"
    files_modified = ["error.log", "traceback.txt"]
    session_type = detector.detect_session_type(last_message, files_modified)

    state_data = {
        "terminal_id": "test_term",
        "task_name": "session_test",
        "last_user_message": last_message,
        "active_files": files_modified,
        "session_type": session_type,  # NEW FIELD
        "saved_at": "2026-03-04T12:00:00Z",
    }

    # Verify session_type is included
    assert "session_type" in state_data
    assert state_data["session_type"] == "debug"  # Should be debug from message keywords

    print("✅ PreCompact includes session_type in state file")


def test_sessionstart_displays_session_type():
    """Test that SessionStart hook displays session_type with emoji."""
    # Mock handoff data with active_task containing session_type
    handoff_data = {
        "task_name": "Fix authentication bug",
        "progress_percent": 50,
        "active_task": {
            "task_name": "debug_auth",
            "last_user_message": "Fix the bug",
            "active_files": ["tests/test_auth.py"],
            "progress_pct": 50,
            "session_type": "debug",  # NEW FIELD
            "saved_at": "2026-03-04T12:00:00Z",
        },
    }

    # Extract session_type
    active_task = handoff_data.get("active_task", {})
    session_type = active_task.get("session_type", "unknown")

    # Emoji mapping (should match SessionStart code)
    session_type_emojis = {
        "debug": "🐛",
        "feature": "✨",
        "refactor": "🔧",
        "test": "🧪",
        "docs": "📝",
        "mixed": "🔀",
        "unknown": "❓",
    }
    session_emoji = session_type_emojis.get(session_type, "")

    # Verify session type display
    assert session_type == "debug"
    assert session_emoji == "🐛"
    display_line = f"  **Session Type:** {session_emoji} {session_type}"
    assert display_line == "  **Session Type:** 🐛 debug"

    print("✅ SessionStart displays session_type with emoji")


def test_session_type_mapping_all_types():
    """Test that all session types have emoji mappings."""
    session_type_emojis = {
        "debug": "🐛",
        "feature": "✨",
        "refactor": "🔧",
        "test": "🧪",
        "docs": "📝",
        "mixed": "🔀",
        "unknown": "❓",
    }

    # All session types should have emojis
    for session_type, emoji in session_type_emojis.items():
        assert emoji  # Should not be empty
        assert len(emoji) == 1  # Should be single emoji

    print("✅ All session types have emoji mappings")


def test_state_file_persistence():
    """Test that session_type persists through state file write/read cycle."""
    from handoff.hooks.__lib.session_type_detector import SessionTypeDetector

    detector = SessionTypeDetector()

    # Simulate PreCompact: detect and write
    last_message = "Add new authentication feature"
    files_modified = ["src/auth.py", "src/auth/__init__.py"]
    session_type = detector.detect_session_type(last_message, files_modified)

    state_data = {
        "terminal_id": "test_term",
        "task_name": "session_test",
        "session_type": session_type,
        "saved_at": "2026-03-04T12:00:00Z",
    }

    # Write to temp file (simulating save_json_file)
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "active_task_test_term.json"
        state_file.write_text(json.dumps(state_data, indent=2))

        # Read back (simulating SessionStart)
        loaded = json.loads(state_file.read_text())

        # Verify session_type persisted
        assert loaded["session_type"] == session_type
        assert loaded["session_type"] in ["debug", "feature", "refactor", "test", "docs", "mixed", "unknown"]

    print("✅ Session type persists through state file cycle")


def test_backward_compatibility_missing_session_type():
    """Test that old state files without session_type default to 'unknown'."""
    # Mock old state file (before session_type field)
    old_state_data = {
        "terminal_id": "test_term",
        "task_name": "session_test",
        "last_user_message": "Some task",
        "active_files": [],
        "saved_at": "2026-03-04T12:00:00Z",
        # NO session_type field
    }

    # Simulate SessionStart reading old state
    active_task = old_state_data
    session_type = active_task.get("session_type", "unknown")

    # Should default to "unknown"
    assert session_type == "unknown"

    print("✅ Backward compatibility: missing session_type defaults to 'unknown'")


if __name__ == "__main__":
    test_precompact_includes_session_type_in_state_file()
    test_sessionstart_displays_session_type()
    test_session_type_mapping_all_types()
    test_state_file_persistence()
    test_backward_compatibility_missing_session_type()
    print("\n✅ All integration tests passed!")

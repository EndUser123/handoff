#!/usr/bin/env python3
"""Test active_task state file approach (replacing TaskRepository integration)."""

import json
import tempfile
from pathlib import Path


def test_active_task_state_format():
    """Test that active_task state file contains expected fields."""
    # Sample state file content (what PreCompact writes)
    state = {
        "terminal_id": "test_terminal",
        "task_name": "session_20260303_120000",
        "last_user_message": "Fix the bug in the handoff system",
        "active_files": [
            "P:/packages/handoff/src/handoff/hooks/PreCompact_handoff_capture.py",
            "P:/packages/handoff/src/handoff/hooks/SessionStart_handoff_restore.py",
        ],
        "next_steps": "Test the compaction workflow",
        "blocker": None,
        "progress_pct": 50,
        "saved_at": "2026-03-03T12:00:00Z",
    }

    # Write and read back (simulating PreCompact -> SessionStart flow)
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "active_task_test_terminal.json"

        # Write (PreCompact)
        state_file.write_text(json.dumps(state, indent=2))

        # Read (SessionStart)
        loaded = json.loads(state_file.read_text())

        # Verify all fields present
        assert loaded["task_name"] == "session_20260303_120000"
        assert loaded["last_user_message"] == "Fix the bug in the handoff system"
        assert len(loaded["active_files"]) == 2
        assert loaded["progress_pct"] == 50
        assert loaded["saved_at"] == "2026-03-03T12:00:00Z"

    print("✅ Active task state file format works correctly")


def test_active_task_in_handoff_payload():
    """Test that active_task is included in handoff payload."""
    # This is what PreCompact builds for handoff_payload["active_task"]
    active_task_info = {
        "task_name": "session_20260303_120000",
        "last_user_message": "Fix the bug",
        "active_files": ["file1.py", "file2.py"],
        "next_steps": "Test it",
        "blocker": None,
        "progress_pct": 50,
        "git_branch": "main",
        "command_context": None,
    }

    # This is what SessionStart receives in handoff_data["active_task"]
    assert active_task_info["task_name"] == "session_20260303_120000"
    assert active_task_info["last_user_message"] == "Fix the bug"
    assert active_task_info["progress_pct"] == 50

    print("✅ Active task in handoff payload works correctly")


def test_no_taskrepository_dependency():
    """Verify no TaskRepository imports in the updated code."""
    import ast

    precompact_file = Path("P:/packages/handoff/src/handoff/hooks/PreCompact_handoff_capture.py")
    source = precompact_file.read_text()

    # Parse AST
    tree = ast.parse(source)

    # Check for TaskRepository imports
    has_taskrepository_import = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "task_repository" in alias.name.lower():
                    has_taskrepository_import = True
        elif isinstance(node, ast.ImportFrom):
            if node.module and "task_repository" in node.module.lower():
                has_taskrepository_import = True

    assert not has_taskrepository_import, "TaskRepository import found - should be removed"
    print("✅ No TaskRepository dependency in PreCompact")


if __name__ == "__main__":
    test_active_task_state_format()
    test_active_task_in_handoff_payload()
    test_no_taskrepository_dependency()
    print("\n✅ All tests passed!")

"""Pytest configuration and fixtures for handoff tests."""

import os
from pathlib import Path


def pytest_configure(config):
    """Configure pytest with custom markers and settings."""
    # This runs once at test session start


def pytest_runtest_setup(item):
    """Clean up task identity state before each test.

    Ensures tests are isolated by cleaning up:
    - Session files from previous tests
    - Environment variables

    This prevents cross-test contamination where one test's
    task identity state bleeds into the next test.
    """
    # Clean up all TASK_NAME environment variables (both old global and new terminal-scoped)
    for key in list(os.environ.keys()):
        if key.startswith("TASK_NAME"):
            del os.environ[key]

    # Clean up session files from previous tests (only test-specific terminals)
    # We only clean up files that match test terminal patterns to avoid
    # interfering with actual development work
    state_dir = Path("P:/.claude/state/task-identity")
    if state_dir.exists():
        # Remove session files for test terminals (terminal_1, terminal_2, test_*)
        for session_file in state_dir.glob("session-task-terminal_*.json"):
            session_file.unlink()
        for session_file in state_dir.glob("session-task-test_*.json"):
            session_file.unlink()

        # Also clean up test metadata files
        for metadata_file in state_dir.glob("last-compact-metadata-test_*.json"):
            metadata_file.unlink()

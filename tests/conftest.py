#!/usr/bin/env python3
"""pytest configuration for handoff package tests."""

import os
import sys
from pathlib import Path

import pytest

# Add package root to sys.path so tests can import 'core' module
package_root = Path(__file__).parent.parent
sys.path.insert(0, str(package_root))


# =============================================================================
# TEST FIXTURE REALITY HELPERS
# Prevents test fixtures from drifting away from production data structure.
# Memory: test_fixture_reality_principle.md
# =============================================================================


@pytest.fixture
def real_transcript_sample():
    """Return a sample transcript entry with REAL production structure.

    Use this in tests to ensure test fixtures match actual transcript format.
    When updating tests, first verify structure against: head -5 <real_transcript>.jsonl
    """
    return {
        "type": "assistant",
        "uuid": "test-uuid-001",
        "timestamp": "2026-03-16T20:00:00.000Z",
        "message": {
            "id": "msg_test_001",
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "call_test_001",
                    "name": "Read",
                    "input": {"file_path": "test/path/file.py"},
                }
            ],
        },
    }


def make_transcript_entry(
    tool_name: str, file_path: str, tool_use_id: str = "call_001"
):
    """Create a properly-structured transcript entry for tests.

    This helper ensures test entries match the NESTED structure of real transcripts:
    - Outer entry has type="assistant"
    - tool_use is nested inside entry.message.content array
    - All required fields present

    Args:
        tool_name: Name of the tool (e.g., "Read", "Write", "Edit")
        file_path: Path argument for the tool
        tool_use_id: Optional custom ID for the tool_use block

    Returns:
        A dict matching real transcript structure
    """
    return {
        "type": "assistant",
        "uuid": f"entry-{tool_use_id}",
        "timestamp": "2026-03-16T20:00:00.000Z",
        "message": {
            "id": f"msg_{tool_use_id}",
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": tool_use_id,
                    "name": tool_name,
                    "input": {"file_path": file_path},
                }
            ],
        },
    }


@pytest.fixture(autouse=True)
def handoff_test_root(tmp_path, monkeypatch):
    """Force all write-path tests to use a temp project root."""
    (tmp_path / ".claude" / "state" / "handoff").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HANDOFF_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("HANDOFF_TEST_ROOT", str(tmp_path))
    yield


def pytest_sessionstart(session):
    """Fail fast if a caller tries to run tests without a temp-root override."""
    del session
    os.environ.setdefault("HANDOFF_TEST_GUARD", "enabled")

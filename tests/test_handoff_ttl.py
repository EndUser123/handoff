#!/usr/bin/env python3
"""Tests for HANDOFF_TTL mechanism in handoff_context_injector.py

This tests the envelope expiration logic:
- Expired envelopes (created_at > HANDOFF_TTL ago) should be rejected
- Expired envelopes should be deleted from disk
- Fresh envelopes should be accepted

The injector reads from P:/.claude/state/handoff/{terminal_id}_handoff.json
matching the format written by PreCompact_handoff_capture.py.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

# Import from the hooks system (outside handoff package)
import sys
from pathlib import Path as PathlibPath

# Add hooks directory to path for import
_hooks_path = PathlibPath(__file__).parents[3] / ".claude" / "hooks"
if str(_hooks_path) not in sys.path:
    sys.path.insert(0, str(_hooks_path))

from UserPromptSubmit_modules.handoff_context_injector import (
    HANDOFF_TTL,
    load_handoff_envelope,
)


def _write_envelope(path: Path, created_at: float | None = None) -> None:
    """Write a test envelope to disk in the terminal_id format."""
    if created_at is None:
        created_at = time.time()

    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "session_id": "test_session",
        "transcript_path": "/tmp/test.jsonl",
        "created_at": created_at,
        "resume_snapshot": {
            "goal": "test goal",
            "current_task": "test task",
        },
    }
    path.write_text(json.dumps(data), encoding="utf-8")


def test_fresh_envelope_is_loaded(tmp_path):
    """Fresh envelopes (created within HANDOFF_TTL) should be loaded successfully."""
    # Override _HANDOFF_DIR for test
    import UserPromptSubmit_modules.handoff_context_injector as injector

    original_handoff_dir = injector._HANDOFF_DIR
    injector._HANDOFF_DIR = tmp_path

    try:
        # Use terminal_id filename format: {terminal_id}_handoff.json
        state_file = tmp_path / "console_test_terminal_handoff.json"
        _write_envelope(state_file, created_at=time.time())

        envelope = load_handoff_envelope("console_test_terminal")

        assert envelope is not None
        assert envelope["session_id"] == "test_session"
        assert envelope["resume_snapshot"]["goal"] == "test goal"
    finally:
        injector._HANDOFF_DIR = original_handoff_dir


def test_expired_envelope_is_rejected(tmp_path):
    """Expired envelopes (created_at > HANDOFF_TTL ago) should return None."""
    # Override _HANDOFF_DIR for test
    import UserPromptSubmit_modules.handoff_context_injector as injector

    original_handoff_dir = injector._HANDOFF_DIR
    injector._HANDOFF_DIR = tmp_path

    try:
        state_file = tmp_path / "console_test_terminal_handoff.json"
        # Create envelope that expired 1 second ago
        expired_time = time.time() - HANDOFF_TTL - 1
        _write_envelope(state_file, created_at=expired_time)

        envelope = load_handoff_envelope("console_test_terminal")

        # Expired envelope should return None
        assert envelope is None

        # File should be deleted
        assert not state_file.exists()
    finally:
        injector._HANDOFF_DIR = original_handoff_dir


def test_boundary_envelope_at_ttl_limit(tmp_path):
    """Envelope exactly at TTL boundary is rejected (uses > not >=)."""
    # Override _HANDOFF_DIR for test
    import UserPromptSubmit_modules.handoff_context_injector as injector

    original_handoff_dir = injector._HANDOFF_DIR
    injector._HANDOFF_DIR = tmp_path

    try:
        state_file = tmp_path / "console_test_terminal_handoff.json"
        # Create envelope exactly at TTL limit (should be expired)
        # The code uses: time.time() - created_at > HANDOFF_TTL
        # So at exactly HANDOFF_TTL, the envelope is expired
        boundary_time = time.time() - HANDOFF_TTL
        _write_envelope(state_file, created_at=boundary_time)

        envelope = load_handoff_envelope("console_test_terminal")

        # Boundary envelope should be expired (rejected)
        assert envelope is None

        # File should be deleted
        assert not state_file.exists()
    finally:
        injector._HANDOFF_DIR = original_handoff_dir


def test_missing_file_returns_none(tmp_path):
    """Missing handoff file should return None gracefully."""
    # Override _HANDOFF_DIR for test
    import UserPromptSubmit_modules.handoff_context_injector as injector

    original_handoff_dir = injector._HANDOFF_DIR
    injector._HANDOFF_DIR = tmp_path

    try:
        envelope = load_handoff_envelope("console_nonexistent_terminal")

        # Should return None for missing file
        assert envelope is None
    finally:
        injector._HANDOFF_DIR = original_handoff_dir


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])

#!/usr/bin/env python3
"""Tests for HANDOFF_TTL mechanism in handoff_context_injector.py

This tests the envelope expiration logic:
- Expired envelopes (created_at > HANDOFF_TTL ago) should be rejected
- Expired envelopes should be deleted from disk
- Fresh envelopes should be accepted
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
    delete_handoff_state,
    load_handoff_envelope,
)


def _write_envelope(path: Path, created_at: float | None = None) -> None:
    """Write a test envelope to disk."""
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
    # Override STATE_DIR for test
    import UserPromptSubmit_modules.handoff_context_injector as injector

    original_state_dir = injector.STATE_DIR
    injector.STATE_DIR = tmp_path

    try:
        state_file = tmp_path / "handoff_test_session.json"
        _write_envelope(state_file, created_at=time.time())

        envelope = load_handoff_envelope("test_session")

        assert envelope is not None
        assert envelope["session_id"] == "test_session"
        assert envelope["resume_snapshot"]["goal"] == "test goal"
    finally:
        injector.STATE_DIR = original_state_dir


def test_expired_envelope_is_rejected(tmp_path):
    """Expired envelopes (created_at > HANDOFF_TTL ago) should return None."""
    # Override STATE_DIR for test
    import UserPromptSubmit_modules.handoff_context_injector as injector

    original_state_dir = injector.STATE_DIR
    injector.STATE_DIR = tmp_path

    try:
        state_file = tmp_path / "handoff_test_session.json"
        # Create envelope that expired 1 second ago
        expired_time = time.time() - HANDOFF_TTL - 1
        _write_envelope(state_file, created_at=expired_time)

        envelope = load_handoff_envelope("test_session")

        # Expired envelope should return None
        assert envelope is None

        # File should be deleted
        assert not state_file.exists()
    finally:
        injector.STATE_DIR = original_state_dir


def test_boundary_envelope_at_ttl_limit(tmp_path):
    """Envelope exactly at TTL boundary is rejected (uses > not >=)."""
    # Override STATE_DIR for test
    import UserPromptSubmit_modules.handoff_context_injector as injector

    original_state_dir = injector.STATE_DIR
    injector.STATE_DIR = tmp_path

    try:
        state_file = tmp_path / "handoff_test_session.json"
        # Create envelope exactly at TTL limit (should be expired)
        # The code uses: time.time() - created_at > HANDOFF_TTL
        # So at exactly HANDOFF_TTL, the envelope is expired
        boundary_time = time.time() - HANDOFF_TTL
        _write_envelope(state_file, created_at=boundary_time)

        envelope = load_handoff_envelope("test_session")

        # Boundary envelope should be expired (rejected)
        assert envelope is None

        # File should be deleted
        assert not state_file.exists()
    finally:
        injector.STATE_DIR = original_state_dir


def test_delete_handoff_state_removes_file(tmp_path):
    """delete_handoff_state() should remove the state file."""
    # Override STATE_DIR for test
    import UserPromptSubmit_modules.handoff_context_injector as injector

    original_state_dir = injector.STATE_DIR
    injector.STATE_DIR = tmp_path

    try:
        state_file = tmp_path / "handoff_test_session.json"
        _write_envelope(state_file)

        # Verify file exists
        assert state_file.exists()

        # Delete it
        delete_handoff_state("test_session")

        # Verify file is gone
        assert not state_file.exists()
    finally:
        injector.STATE_DIR = original_state_dir


def test_delete_handoff_state_missing_file_is_graceful(tmp_path):
    """delete_handoff_state() should handle missing files gracefully."""
    # Override STATE_DIR for test
    import UserPromptSubmit_modules.handoff_context_injector as injector

    original_state_dir = injector.STATE_DIR
    injector.STATE_DIR = tmp_path

    try:
        # Try to delete non-existent file (should not raise)
        delete_handoff_state("nonexistent_session")

        # Should not raise any exception
    finally:
        injector.STATE_DIR = original_state_dir


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])

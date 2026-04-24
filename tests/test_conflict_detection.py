#!/usr/bin/env python3
"""Tests for git conflict detection in session restore."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def _get_current_head_short(project_root: Path) -> str | None:
    """Get current HEAD short hash for test fixtures."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True, text=True, cwd=str(project_root), timeout=5,
    )
    if result.returncode == 0:
        return result.stdout.strip()[:8]
    return None


def _build_restore_message_with_conflict_check(
    envelope: dict, project_root: Path,
) -> str:
    """Extracted conflict detection logic from SessionStart_handoff_restore.py.

    This mirrors the exact logic at lines 266-290 of the restore hook so we can
    test it in isolation without running the full SessionStart pipeline.
    """
    restoration_message = "Restored previous session context"

    try:
        env_ctx = envelope.get("environment_context")
        if env_ctx and isinstance(env_ctx, dict):
            git_st = env_ctx.get("git_state")
            if git_st and isinstance(git_st, dict):
                captured_commit = (git_st.get("last_commit") or {}).get("hash")
                if captured_commit and isinstance(captured_commit, str):
                    result = subprocess.run(
                        ["git", "rev-parse", "HEAD"],
                        capture_output=True, text=True, cwd=str(project_root), timeout=5,
                    )
                    if result.returncode == 0:
                        current_hash = result.stdout.strip()[:8]
                        if current_hash != captured_commit:
                            restoration_message += (
                                f"\n\n**Codebase has changed** since last session "
                                f"(captured: `{captured_commit}`, current: `{current_hash}`). "
                                f"Context may be stale."
                            )
    except Exception:
        pass

    return restoration_message


class TestConflictDetection:
    """Test git hash conflict detection during session restore."""

    def test_no_environment_context(self):
        """No env_context → no warning."""
        envelope = {"resume_snapshot": {}}
        msg = _build_restore_message_with_conflict_check(envelope, PACKAGE_ROOT)
        assert "Codebase has changed" not in msg

    def test_env_context_but_no_git_state(self):
        """env_context exists but git_state is None → no warning."""
        envelope = {"environment_context": {"git_state": None}}
        msg = _build_restore_message_with_conflict_check(envelope, PACKAGE_ROOT)
        assert "Codebase has changed" not in msg

    def test_git_state_but_no_last_commit(self):
        """git_state exists but last_commit is None → no warning."""
        envelope = {"environment_context": {"git_state": {"last_commit": None}}}
        msg = _build_restore_message_with_conflict_check(envelope, PACKAGE_ROOT)
        assert "Codebase has changed" not in msg

    def test_matching_hash_no_warning(self):
        """Captured hash matches current HEAD → no warning."""
        current = _get_current_head_short(PACKAGE_ROOT)
        if current is None:
            pytest.skip("Not inside a git repo")

        envelope = {
            "environment_context": {
                "git_state": {
                    "last_commit": {"hash": current},
                },
            },
        }
        msg = _build_restore_message_with_conflict_check(envelope, PACKAGE_ROOT)
        assert "Codebase has changed" not in msg

    def test_different_hash_produces_warning(self):
        """Captured hash differs from current HEAD → warning appended."""
        current = _get_current_head_short(PACKAGE_ROOT)
        if current is None:
            pytest.skip("Not inside a git repo")

        fake_hash = "deadbeef"
        # Make sure fake doesn't accidentally match
        if fake_hash == current:
            fake_hash = "cafebabe"

        envelope = {
            "environment_context": {
                "git_state": {
                    "last_commit": {"hash": fake_hash},
                },
            },
        }
        msg = _build_restore_message_with_conflict_check(envelope, PACKAGE_ROOT)
        assert "Codebase has changed" in msg
        assert fake_hash in msg
        assert current in msg

    def test_empty_hash_string_no_warning(self):
        """Empty string hash → no warning (not truthy)."""
        envelope = {
            "environment_context": {
                "git_state": {
                    "last_commit": {"hash": ""},
                },
            },
        }
        msg = _build_restore_message_with_conflict_check(envelope, PACKAGE_ROOT)
        assert "Codebase has changed" not in msg

    def test_non_string_hash_no_warning(self):
        """Non-string hash (e.g. int) → no warning."""
        envelope = {
            "environment_context": {
                "git_state": {
                    "last_commit": {"hash": 12345},
                },
            },
        }
        msg = _build_restore_message_with_conflict_check(envelope, PACKAGE_ROOT)
        assert "Codebase has changed" not in msg

    def test_non_dict_env_context_no_warning(self):
        """env_context is a string instead of dict → no warning."""
        envelope = {"environment_context": "not a dict"}
        msg = _build_restore_message_with_conflict_check(envelope, PACKAGE_ROOT)
        assert "Codebase has changed" not in msg

    def test_non_git_directory_graceful(self, tmp_path):
        """project_root is not a git repo → no crash, no warning."""
        envelope = {
            "environment_context": {
                "git_state": {
                    "last_commit": {"hash": "abc12345"},
                },
            },
        }
        # tmp_path is not a git repo — git rev-parse HEAD will fail
        msg = _build_restore_message_with_conflict_check(envelope, tmp_path)
        assert "Codebase has changed" not in msg

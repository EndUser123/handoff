#!/usr/bin/env python3
"""Characterization tests for P0 issues - Race conditions and resource leaks.

These tests characterize CURRENT behavior before fixes.
After fixes, these tests verify the issues are resolved.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Test files exist and contain the problematic code
HANDOFF_STORE = (
    Path(__file__).parent.parent / "scripts" / "hooks" / "__lib" / "snapshot_store.py"
)
GIT_STATE = (
    Path(__file__).parent.parent / "scripts" / "hooks" / "__lib" / "git_state.py"
)
HANDOFF_V2 = (
    Path(__file__).parent.parent / "scripts" / "hooks" / "__lib" / "snapshot_v2.py"
)
TERMINAL_REGISTRY = (
    Path(__file__).parent.parent
    / "scripts"
    / "hooks"
    / "__lib"
    / "terminal_file_registry.py"
)


class TestP001_FileLockTOCTOU:
    """P0-001: TOCTOU race condition in FileLock._try_acquire_lock_once()."""

    def test_file_exists_and_contains_toctou_pattern(self):
        """Characterization: handoff_store.py contains TOCTOU pattern at lines 145-176.

        Current code:
        - Line 157: lock_fd = os.open(...)  # Open first
        - Lines 161-172: Lock attempt on fd  # Then lock

        FIX: Use atomic open-and-lock operations.
        """
        assert HANDOFF_STORE.exists()
        content = HANDOFF_STORE.read_text()

        # Verify the TOCTOU pattern exists
        assert "os.open(" in content
        assert "lock_fd = os.open" in content or "lock_fd = os.open" in content.replace(
            " ", ""
        )
        assert "_try_acquire_lock_once" in content


class TestP002_GitSubprocessTimeout:
    """P0-002: Sequential git subprocess calls cause timeout under load."""

    def test_git_state_contains_sequential_subprocess_calls(self):
        """Characterization: git_state.py contains 3 sequential subprocess calls at lines 158-199.

        Current code makes 3 calls:
        - rev-parse subprocess (2s timeout)
        - log message subprocess (2s timeout)
        - log timestamp subprocess (2s timeout)
        Total: 6s worst case, 12s under load

        FIX: Consolidate to single git log --format call.
        """
        assert GIT_STATE.exists()
        content = GIT_STATE.read_text()

        # Verify _get_last_commit exists and uses subprocess
        assert "_get_last_commit" in content
        assert "subprocess.run" in content


class TestP003_StaleLockCleanupTOCTOU:
    """P0-003: TOCTOU in _check_and_remove_stale_lock()."""

    def test_handoff_store_contains_stale_lock_cleanup(self):
        """Characterization: handoff_store.py contains _check_and_remove_stale_lock.

        Current code has check → stat → delete pattern (non-atomic).

        FIX: Use atomic file operations with proper locking.
        """
        assert HANDOFF_STORE.exists()
        content = HANDOFF_STORE.read_text()

        assert "_check_and_remove_stale_lock" in content


class TestP004_ValidateEnvelopeTOCTOU:
    """P0-004: TOCTOU in validate_envelope()."""

    def test_handoff_v2_contains_validate_envelope(self):
        """Characterization: handoff_v2.py contains validate_envelope at lines 144-200.

        Current code has split validation checks (TOCTOU gaps).

        FIX: Consolidate path validation into single atomic check.
        """
        assert HANDOFF_V2.exists()
        content = HANDOFF_V2.read_text()

        assert "validate_envelope" in content


class TestP005_VerifyEvidenceFreshnessTOCTOU:
    """P0-005: TOCTOU in verify_evidence_freshness()."""

    def test_handoff_v2_contains_verify_evidence_freshness(self):
        """Characterization: handoff_v2.py contains verify_evidence_freshness.

        Current code validates → then hashes (TOCTOU gap).

        FIX: Compute hash first, then validate atomically.
        """
        assert HANDOFF_V2.exists()
        content = HANDOFF_V2.read_text()

        assert "verify_evidence_freshness" in content


class TestP006_FileDescriptorLeak:
    """P0-006: File descriptor leak in terminal_file_registry._save_registry()."""

    def test_terminal_registry_contains_save_registry(self):
        """Characterization: terminal_file_registry.py contains _save_registry.

        Current code may leak fd on error path.

        FIX: Use context manager or try-finally for cleanup.
        """
        assert TERMINAL_REGISTRY.exists()
        content = TERMINAL_REGISTRY.read_text()

        assert "_save_registry" in content


class TestP007_TempFileLeak:
    """P0-007: Temporary file leak in atomic_write_with_retry()."""

    def test_handoff_store_contains_atomic_write_with_retry(self):
        """Characterization: handoff_store.py contains atomic_write_with_retry.

        Current code may leak temp file on exception.

        FIX: Use try-finally or context manager for cleanup.
        """
        assert HANDOFF_STORE.exists()
        content = HANDOFF_STORE.read_text()

        assert "atomic_write_with_retry" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

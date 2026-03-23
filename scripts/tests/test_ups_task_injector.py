#!/usr/bin/env python3
"""Tests for userpromptsubmit_task_injector.py — post-compaction context injection.

Tests the public inject_task_context() function in isolation (no UPS registry needed).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


from scripts.hooks.userpromptsubmit_task_injector import (
    _build_injection,
    _is_fresh,
    inject_task_context,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_handoff(
    handoff_dir: Path,
    terminal_id: str,
    goal: str,
    next_step: str | None = None,
    status: str = "pending",
    age_minutes: int = 0,
) -> None:
    """Write a synthetic handoff JSON file."""
    handoff_dir.mkdir(parents=True, exist_ok=True)
    created_at = (
        datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
    ).isoformat()
    payload = {
        "created_at": created_at,
        "resume_snapshot": {
            "status": status,
            "terminal_id": terminal_id,
            "goal": goal,
            "next_step": next_step or "",
        },
    }
    (handoff_dir / f"{terminal_id}_handoff.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def _context(tmp_path: Path) -> dict:
    """Build a minimal context_data dict pointing at tmp_path as project root."""
    return {"cwd": str(tmp_path)}


# ---------------------------------------------------------------------------
# _is_fresh
# ---------------------------------------------------------------------------


def test_is_fresh_recent():
    ts = datetime.now(timezone.utc).isoformat()
    assert _is_fresh(ts, 120) is True


def test_is_fresh_old():
    ts = (datetime.now(timezone.utc) - timedelta(minutes=200)).isoformat()
    assert _is_fresh(ts, 120) is False


def test_is_fresh_invalid_string():
    assert _is_fresh("not-a-date", 120) is False


# ---------------------------------------------------------------------------
# _build_injection
# ---------------------------------------------------------------------------


def test_build_injection_with_next_step():
    text = _build_injection("Implement feature X", "Write tests first")
    assert "CURRENT TASK" in text
    assert "Implement feature X" in text
    assert "NEXT STEP" in text
    assert "Write tests first" in text


def test_build_injection_without_next_step():
    text = _build_injection("Implement feature X", None)
    assert "Implement feature X" in text
    assert "NEXT STEP" not in text


def test_build_injection_contains_resume_warning():
    text = _build_injection("goal", None)
    assert "POST-COMPACTION" in text or "compacted" in text.lower()


# ---------------------------------------------------------------------------
# inject_task_context — happy path
# ---------------------------------------------------------------------------


def test_inject_returns_text_for_pending_handoff(tmp_path):
    (tmp_path / ".claude").mkdir(exist_ok=True)
    handoff_dir = tmp_path / ".claude" / "state" / "handoff"
    _write_handoff(handoff_dir, "term1", "Backup HOOKS_CATALOG.md")

    result = inject_task_context(_context(tmp_path), "term1")

    assert result is not None
    assert "Backup HOOKS_CATALOG.md" in result


def test_inject_includes_next_step_when_present(tmp_path):
    (tmp_path / ".claude").mkdir(exist_ok=True)
    handoff_dir = tmp_path / ".claude" / "state" / "handoff"
    _write_handoff(
        handoff_dir, "term1", "Refactor auth module", next_step="Run tests first"
    )

    result = inject_task_context(_context(tmp_path), "term1")

    assert result is not None
    assert "Run tests first" in result


# ---------------------------------------------------------------------------
# inject_task_context — guard clauses
# ---------------------------------------------------------------------------


def test_inject_returns_none_for_empty_terminal_id(tmp_path):
    assert inject_task_context(_context(tmp_path), "") is None


def test_inject_returns_none_when_no_handoff_file(tmp_path):
    (tmp_path / ".claude").mkdir(exist_ok=True)
    result = inject_task_context(_context(tmp_path), "term1")
    assert result is None


def test_inject_returns_none_for_consumed_handoff(tmp_path):
    (tmp_path / ".claude").mkdir(exist_ok=True)
    handoff_dir = tmp_path / ".claude" / "state" / "handoff"
    _write_handoff(handoff_dir, "term1", "Old task", status="consumed")

    result = inject_task_context(_context(tmp_path), "term1")
    assert result is None


def test_inject_returns_none_for_terminal_mismatch(tmp_path):
    (tmp_path / ".claude").mkdir(exist_ok=True)
    handoff_dir = tmp_path / ".claude" / "state" / "handoff"
    # File is for term1, but we ask for term2
    _write_handoff(handoff_dir, "term1", "Some task")

    result = inject_task_context(_context(tmp_path), "term2")
    assert result is None


def test_inject_returns_none_for_stale_handoff(tmp_path):
    (tmp_path / ".claude").mkdir(exist_ok=True)
    handoff_dir = tmp_path / ".claude" / "state" / "handoff"
    _write_handoff(handoff_dir, "term1", "Old task", age_minutes=180)  # >120 min

    result = inject_task_context(_context(tmp_path), "term1")
    assert result is None


def test_inject_returns_none_for_empty_goal(tmp_path):
    (tmp_path / ".claude").mkdir(exist_ok=True)
    handoff_dir = tmp_path / ".claude" / "state" / "handoff"
    _write_handoff(handoff_dir, "term1", "")  # Empty goal

    result = inject_task_context(_context(tmp_path), "term1")
    assert result is None


# ---------------------------------------------------------------------------
# Double-injection prevention (marker file)
# ---------------------------------------------------------------------------


def test_inject_returns_none_on_second_call(tmp_path):
    (tmp_path / ".claude").mkdir(exist_ok=True)
    handoff_dir = tmp_path / ".claude" / "state" / "handoff"
    _write_handoff(handoff_dir, "term1", "Deploy to staging")

    first = inject_task_context(_context(tmp_path), "term1")
    second = inject_task_context(_context(tmp_path), "term1")

    assert first is not None
    assert second is None  # Marker file prevents double-injection


def test_inject_marker_file_written_after_first_call(tmp_path):
    (tmp_path / ".claude").mkdir(exist_ok=True)
    handoff_dir = tmp_path / ".claude" / "state" / "handoff"
    _write_handoff(handoff_dir, "term1", "Deploy to staging")

    inject_task_context(_context(tmp_path), "term1")

    marker = handoff_dir / "term1_ups_inject.marker"
    assert marker.exists()


def test_inject_handoff_status_remains_pending_after_injection(tmp_path):
    """Handoff file must stay 'pending' so SessionStart can still restore it."""
    (tmp_path / ".claude").mkdir(exist_ok=True)
    handoff_dir = tmp_path / ".claude" / "state" / "handoff"
    _write_handoff(handoff_dir, "term1", "Deploy to staging")

    inject_task_context(_context(tmp_path), "term1")

    payload = json.loads((handoff_dir / "term1_handoff.json").read_text())
    assert payload["resume_snapshot"]["status"] == "pending"


# ---------------------------------------------------------------------------
# cwd resolution
# ---------------------------------------------------------------------------


def test_inject_returns_none_when_no_cwd(tmp_path):
    result = inject_task_context({}, "term1")
    assert result is None


def test_inject_resolves_project_root_from_subdirectory(tmp_path):
    """Project root detection should walk up from any subdirectory."""
    (tmp_path / ".claude").mkdir(exist_ok=True)
    handoff_dir = tmp_path / ".claude" / "state" / "handoff"
    _write_handoff(handoff_dir, "term1", "Task in subdir")

    subdir = tmp_path / "packages" / "mylib"
    subdir.mkdir(parents=True)
    ctx = {"cwd": str(subdir)}

    result = inject_task_context(ctx, "term1")
    assert result is not None
    assert "Task in subdir" in result

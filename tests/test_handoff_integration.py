#!/usr/bin/env python3
"""Integration tests for the Handoff V2 compact/restore cycle."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from core.hooks.__lib.handoff_files import HandoffFileStorage
from core.hooks.__lib.handoff_v2 import compute_checksum

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
HOOKS_DIR = PACKAGE_ROOT / "scripts" / "hooks"


def _write_transcript(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry) + "\n")


def _run_hook(
    script_name: str, payload: dict, *, env: dict[str, str] | None = None
) -> dict:
    # Merge provided env with parent environment to preserve PATH and other vars
    import os

    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)

    result = subprocess.run(
        [sys.executable, str(HOOKS_DIR / script_name)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
        env=merged_env,
    )
    return json.loads(result.stdout)


def _capture_v2_snapshot(
    tmp_path, monkeypatch, terminal_id: str = "console_integration"
) -> tuple[Path, HandoffFileStorage]:
    monkeypatch.setenv("HANDOFF_PROJECT_ROOT", str(tmp_path))
    transcript_path = tmp_path / "transcripts" / "integration.jsonl"
    _write_transcript(
        transcript_path,
        [
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "text",
                            "text": "Finish the Handoff V2 migration and keep the restore payload minimal.",
                        }
                    ]
                },
            },
            {
                "type": "tool_use",
                "name": "Edit",
                "input": {
                    "file_path": "P:/packages/handoff/scripts/hooks/SessionStart_handoff_restore.py"
                },
            },
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "text",
                            "text": "Decision: keep the restore payload minimal. editing file P:/packages/handoff/scripts/hooks/SessionStart_handoff_restore.py and then run targeted tests.",
                        }
                    ]
                },
            },
        ],
    )

    precompact_payload = {
        "session_id": "source-session",
        "terminal_id": terminal_id,
        "transcript_path": str(transcript_path),
        "cwd": str(tmp_path),
        "hook_event_name": "PreCompact",
        "trigger": "manual",
    }
    output = _run_hook("PreCompact_handoff_capture.py", precompact_payload, env=None)
    assert output["decision"] == "approve"
    return transcript_path, HandoffFileStorage(tmp_path, terminal_id)


def test_full_compact_restore_cycle_consumes_snapshot(tmp_path, monkeypatch):
    _, storage = _capture_v2_snapshot(tmp_path, monkeypatch)

    restore_payload = {
        "session_id": "restore-session",
        "terminal_id": "console_integration",
        "cwd": str(tmp_path),
        "hook_event_name": "SessionStart",
        "trigger": "compact",
        "source": "compact",
    }
    output = _run_hook("SessionStart_handoff_restore.py", restore_payload)

    assert output["decision"] == "approve"
    assert output["reason"] == "Restored previous session context"
    assert "SESSION HANDOFF V2" in output["additionalContext"]
    assert "Finish the Handoff V2 migration" in output["additionalContext"]

    saved = storage.load_handoff()
    assert saved is not None
    assert saved["resume_snapshot"]["status"] == "consumed"
    assert saved["resume_snapshot"]["consumed_by_session_id"] == "restore-session"


def test_session_start_generic_startup_does_not_consume_snapshot(tmp_path, monkeypatch):
    _, storage = _capture_v2_snapshot(
        tmp_path, monkeypatch, terminal_id="console_generic"
    )

    startup_payload = {
        "session_id": "startup-session",
        "terminal_id": "console_generic",
        "cwd": str(tmp_path),
        "hook_event_name": "SessionStart",
        "trigger": "startup",
    }
    output = _run_hook("SessionStart_handoff_restore.py", startup_payload)

    assert "HANDOFF NOT RESTORED" in output["additionalContext"]
    assert "not a post-compact session start" in output["additionalContext"]

    saved = storage.load_handoff()
    assert saved is not None
    assert saved["resume_snapshot"]["status"] == "pending"


def test_stale_snapshot_is_rejected_with_metadata_only_hint(tmp_path, monkeypatch):
    _, storage = _capture_v2_snapshot(
        tmp_path, monkeypatch, terminal_id="console_stale"
    )
    payload = storage.load_raw_handoff()
    assert payload is not None
    payload["resume_snapshot"]["expires_at"] = "2000-01-01T00:00:00+00:00"
    payload["checksum"] = compute_checksum(payload)
    assert storage.save_handoff(payload)

    restore_payload = {
        "session_id": "stale-session",
        "terminal_id": "console_stale",
        "cwd": str(tmp_path),
        "hook_event_name": "SessionStart",
        "trigger": "compact",
        "source": "compact",
    }
    output = _run_hook("SessionStart_handoff_restore.py", restore_payload)

    assert "HANDOFF NOT RESTORED" in output["additionalContext"]
    assert "Snapshot Created:" in output["additionalContext"]
    assert "Source Session:" in output["additionalContext"]
    assert "Goal:" not in output["additionalContext"]

    rejected = storage.load_handoff()
    assert rejected is not None
    assert rejected["resume_snapshot"]["status"] == "rejected_stale"


def test_tasks_snapshot_flows_through_handoff_pipeline(tmp_path, monkeypatch):
    """Regression test: tasks_snapshot should flow from PreCompact through to restore message."""
    terminal_id = "console_tasks_test"
    monkeypatch.setenv("HANDOFF_PROJECT_ROOT", str(tmp_path))

    # Create task tracker state before PreCompact runs
    task_tracker_dir = tmp_path / ".claude" / "state" / "task_tracker"
    task_tracker_dir.mkdir(parents=True, exist_ok=True)
    task_file = task_tracker_dir / f"{terminal_id}_tasks.json"
    task_data = {
        "terminal_id": terminal_id,
        "tasks": {
            "task_list": [
                {"id": "1", "status": "in_progress", "description": "Fix the bug in handler"},
                {"id": "2", "status": "pending", "description": "Write regression test"},
                {"id": "3", "status": "completed", "description": "Review PR"},
            ]
        },
    }
    with open(task_file, "w", encoding="utf-8") as f:
        json.dump(task_data, f)

    # Create transcript - use same structure as working _capture_v2_snapshot
    transcript_path = tmp_path / "transcripts" / "tasks.jsonl"
    _write_transcript(
        transcript_path,
        [
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "text",
                            "text": "Finish the Handoff V2 migration and pass task status through.",
                        }
                    ]
                },
            },
            {
                "type": "tool_use",
                "name": "Edit",
                "input": {
                    "file_path": "P:/packages/handoff/scripts/hooks/SessionStart_handoff_restore.py"
                },
            },
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "text",
                            "text": "Decision: pass task status through handoff. editing the handoff restore file.",
                        }
                    ]
                },
            },
        ],
    )

    # Run PreCompact
    precompact_payload = {
        "session_id": "source-session-tasks",
        "terminal_id": terminal_id,
        "transcript_path": str(transcript_path),
        "cwd": str(tmp_path),
        "hook_event_name": "PreCompact",
        "trigger": "manual",
    }
    output = _run_hook("PreCompact_handoff_capture.py", precompact_payload, env=None)
    assert output["decision"] == "approve"

    # Verify tasks_snapshot was stored in the envelope
    storage = HandoffFileStorage(tmp_path, terminal_id)
    saved = storage.load_handoff()
    assert saved is not None
    assert "tasks_snapshot" in saved["resume_snapshot"]
    # Should have 2 pending/in_progress tasks (not completed)
    task_snapshot = saved["resume_snapshot"]["tasks_snapshot"]
    pending = [t for t in task_snapshot if t.get("status") not in ("completed", "done")]
    assert len(pending) == 2

    # Run SessionStart restore
    restore_payload = {
        "session_id": "restore-session-tasks",
        "terminal_id": terminal_id,
        "cwd": str(tmp_path),
        "hook_event_name": "SessionStart",
        "trigger": "compact",
        "source": "compact",
    }
    restore_output = _run_hook("SessionStart_handoff_restore.py", restore_payload)

    # Verify tasks appear in restore message
    context = restore_output["additionalContext"]
    assert "## Current Tasks" in context
    assert "[in_progress]" in context
    assert "[pending]" in context
    assert "Fix the bug in handler" in context
    assert "Write regression test" in context
    # Completed tasks should not appear
    assert "Review PR" not in context


def test_invalid_checksum_is_rejected_without_task_context(tmp_path, monkeypatch):
    _, storage = _capture_v2_snapshot(
        tmp_path, monkeypatch, terminal_id="console_invalid"
    )
    payload = storage.load_raw_handoff()
    assert payload is not None
    payload["checksum"] = "sha256:deadbeef"
    handoff_file = storage.handoff_file
    with open(handoff_file, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)

    restore_payload = {
        "session_id": "invalid-session",
        "terminal_id": "console_invalid",
        "cwd": str(tmp_path),
        "hook_event_name": "SessionStart",
        "trigger": "compact",
        "source": "compact",
    }
    output = _run_hook("SessionStart_handoff_restore.py", restore_payload)

    assert "HANDOFF NOT RESTORED" in output["additionalContext"]
    # LOGIC-002: Checksum validation now happens early in SessionStart (before evaluate_for_restore)
    assert "checksum mismatch" in output["additionalContext"]
    assert "Goal:" not in output["additionalContext"]

    # Note: SessionStart rejects checksum mismatches early, before status update
    # The handoff file is still on disk with original status (not updated to rejected_invalid)
    # Use load_raw_handoff() to verify it wasn't modified
    raw = storage.load_raw_handoff()
    assert raw is not None
    assert (
        raw["resume_snapshot"]["status"] == "pending"
    )  # Status unchanged (early rejection)


def test_changed_transcript_rejects_restore_as_stale_snapshot(tmp_path, monkeypatch):
    transcript_path, storage = _capture_v2_snapshot(
        tmp_path, monkeypatch, terminal_id="console_changed"
    )
    transcript_path.write_text(
        '{"type":"user","message":{"content":[{"type":"text","text":"different"}]}}\n',
        encoding="utf-8",
    )

    restore_payload = {
        "session_id": "changed-session",
        "terminal_id": "console_changed",
        "cwd": str(tmp_path),
        "hook_event_name": "SessionStart",
        "trigger": "compact",
        "source": "compact",
    }
    output = _run_hook("SessionStart_handoff_restore.py", restore_payload)

    assert "HANDOFF NOT RESTORED" in output["additionalContext"]
    assert "snapshot evidence changed" in output["additionalContext"]

    rejected = storage.load_handoff()
    assert rejected is not None
    assert rejected["resume_snapshot"]["status"] == "rejected_stale"

#!/usr/bin/env python3
"""Terminal isolation tests for V2 handoff storage."""

from __future__ import annotations


from core.hooks.__lib.handoff_files import HandoffFileStorage
from core.hooks.__lib.handoff_v2 import build_envelope, build_resume_snapshot


def _payload(terminal_id: str, *, goal: str, transcript_path: str) -> dict:
    snapshot = build_resume_snapshot(
        terminal_id=terminal_id,
        source_session_id="source",
        goal=goal,
        current_task=goal,
        progress_percent=40,
        progress_state="in_progress",
        blockers=[],
        active_files=[f"{goal}.py"],
        pending_operations=[],
        next_step="Continue",
        decision_refs=[],
        evidence_refs=["ev_1"],
        transcript_path=transcript_path,
        message_intent="instruction",
    )
    return build_envelope(
        resume_snapshot=snapshot,
        decision_register=[],
        evidence_index=[
            {
                "id": "ev_1",
                "type": "transcript",
                "label": "transcript",
                "path": transcript_path,
            }
        ],
    )


def test_storage_keeps_terminals_separate(tmp_path):
    # Create real transcript files for validation
    transcript_a = tmp_path / "transcript_a.jsonl"
    transcript_b = tmp_path / "transcript_b.jsonl"
    transcript_a.write_text('{"role": "user", "content": "task_a"}')
    transcript_b.write_text('{"role": "user", "content": "task_b"}')

    storage_a = HandoffFileStorage(tmp_path, "console_a")
    storage_b = HandoffFileStorage(tmp_path, "console_b")

    assert storage_a.save_handoff(
        _payload("console_a", goal="task_a", transcript_path=str(transcript_a))
    )
    assert storage_b.save_handoff(
        _payload("console_b", goal="task_b", transcript_path=str(transcript_b))
    )

    loaded_a = storage_a.load_handoff()
    loaded_b = storage_b.load_handoff()

    assert loaded_a is not None
    assert loaded_b is not None
    assert loaded_a["resume_snapshot"]["goal"] == "task_a"
    assert loaded_b["resume_snapshot"]["goal"] == "task_b"


def test_storage_rejects_wrong_terminal_file_contents(tmp_path):
    # Create real transcript file for validation
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text('{"role": "user", "content": "test"}')

    storage = HandoffFileStorage(tmp_path, "console_target")
    wrong_storage = HandoffFileStorage(tmp_path, "console_source")

    assert wrong_storage.save_handoff(
        _payload("console_source", goal="wrong", transcript_path=str(transcript))
    )

    raw = wrong_storage.load_raw_handoff()
    assert raw is not None
    storage.handoff_dir.mkdir(parents=True, exist_ok=True)
    with open(storage.handoff_file, "w", encoding="utf-8") as handle:
        import json

        json.dump(raw, handle, indent=2)

    assert storage.load_handoff() is None

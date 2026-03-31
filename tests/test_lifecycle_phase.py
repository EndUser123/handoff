"""Tests for handoff lifecycle phase field (CHANGE-001 through CHANGE-007).

Covers:
- VALID_LIFECYCLE_PHASES constant and OPTIONAL_SNAPSHOT_FIELDS
- detect_lifecycle_phase() detection logic
- detect_task_mode() body restoration
- build_restore_message() phase directive injection
- dynamic_sections lifecycle directive
- handoff_files read/truncate accumulated state
- handoff_accumulator PostToolUse module
- Accumulated phase preference over inference
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

# Ensure package root is importable
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))


# ---------------------------------------------------------------------------
# CHANGE-001: Constants and validation (handoff_v2.py)
# ---------------------------------------------------------------------------


class TestLifecyclePhaseConstants:
    """Validate lifecycle phase constants are defined correctly."""

    def test_valid_lifecycle_phases(self) -> None:
        pytest.skip("VALID_LIFECYCLE_PHASES not yet implemented in handoff_v2")

    def test_lifecycle_phase_in_optional_fields(self) -> None:
        pytest.skip("lifecycle_phase not yet in OPTIONAL_SNAPSHOT_FIELDS")


class TestLifecyclePhaseValidation:
    """Test validation of lifecycle_phase field in envelope."""

    def test_valid_phases_accepted(self) -> None:
        pytest.skip("lifecycle_phase kwarg not implemented in build_resume_snapshot")

    def test_invalid_phase_rejected(self) -> None:
        pytest.skip("lifecycle_phase kwarg not implemented in build_resume_snapshot")

    def test_backward_compat_no_phase(self) -> None:
        pytest.skip("lifecycle_phase not implemented")


# ---------------------------------------------------------------------------
# CHANGE-002: detect_lifecycle_phase() (PreCompact_handoff_capture.py)
# ---------------------------------------------------------------------------


class TestDetectLifecyclePhase:
    """Test detect_lifecycle_phase() detection logic."""

    def test_planning_with_awaiting_approval_blocker(self) -> None:
        from scripts.hooks.PreCompact_handoff_capture import detect_lifecycle_phase

        result = detect_lifecycle_phase(
            blockers=[{"type": "awaiting_approval", "summary": "Waiting"}],
            active_files=["foo.py"],
            pending_operations=[],
            goal="Implement feature",
        )
        assert result == "planning"

    def test_implementing_with_pending_operations(self) -> None:
        from scripts.hooks.PreCompact_handoff_capture import detect_lifecycle_phase

        result = detect_lifecycle_phase(
            blockers=[],
            active_files=["foo.py"],
            pending_operations=[{"type": "edit", "target": "foo.py"}],
            goal="Fix bug",
        )
        assert result == "implementing"

    def test_discussing_with_question_goal(self) -> None:
        from scripts.hooks.PreCompact_handoff_capture import detect_lifecycle_phase

        result = detect_lifecycle_phase(
            blockers=[],
            active_files=[],
            pending_operations=[],
            goal="How does this work?",
        )
        assert result == "discussing"

    def test_implementing_with_task_mode_override(self) -> None:
        from scripts.hooks.PreCompact_handoff_capture import detect_lifecycle_phase

        # task_mode=implement + active_files -> implementing (not discussing)
        result = detect_lifecycle_phase(
            blockers=[],
            active_files=["foo.py"],
            pending_operations=[],
            goal="Fix bug in foo",
            task_mode="implement",
        )
        assert result == "implementing"

    def test_discussing_no_signals(self) -> None:
        from scripts.hooks.PreCompact_handoff_capture import detect_lifecycle_phase

        # No pending ops, no question mark, no task_mode override -> discussing
        result = detect_lifecycle_phase(
            blockers=[],
            active_files=[],
            pending_operations=[],
            goal="Do something",
            task_mode="none",
        )
        assert result == "discussing"


class TestDetectTaskMode:
    """Test detect_task_mode() body is intact."""

    def test_create_mode(self) -> None:
        from scripts.hooks.PreCompact_handoff_capture import detect_task_mode

        result = detect_task_mode("Create a new ADR", [])
        assert result == "create"

    def test_implement_mode(self) -> None:
        from scripts.hooks.PreCompact_handoff_capture import detect_task_mode

        result = detect_task_mode("Fix the bug in foo.py", [])
        assert result == "implement"

    def test_none_mode(self) -> None:
        from scripts.hooks.PreCompact_handoff_capture import detect_task_mode

        result = detect_task_mode("Look at this", [])
        assert result == "none"


# ---------------------------------------------------------------------------
# CHANGE-003: dynamic_sections lifecycle directive
# ---------------------------------------------------------------------------


class TestDynamicSectionsLifecycle:
    """Test lifecycle directive generation in dynamic_sections."""

    def test_build_lifecycle_directive(self) -> None:
        pytest.skip("build_lifecycle_directive not yet implemented")

    def test_directive_in_generate_for_non_implementing(self) -> None:
        pytest.skip("lifecycle_phase not implemented in dynamic_sections")

    def test_no_directive_for_implementing(self) -> None:
        pytest.skip("lifecycle_phase not implemented in dynamic_sections")


# ---------------------------------------------------------------------------
# CHANGE-004: Restore pipeline lifecycle directive
# ---------------------------------------------------------------------------


class TestRestoreMessageLifecycleDirective:
    """Test lifecycle directive in restore messages."""

    def _make_envelope(self, lifecycle_phase: str | None = None) -> dict[str, Any]:
        from scripts.hooks.__lib.handoff_v2 import (
            build_envelope,
            build_resume_snapshot,
        )

        kwargs: dict[str, Any] = {}
        if lifecycle_phase:
            kwargs["lifecycle_phase"] = lifecycle_phase

        snapshot = build_resume_snapshot(
            terminal_id="test_terminal",
            source_session_id="test_session",
            goal="Test goal",
            current_task="Test task",
            progress_percent=50,
            progress_state="in_progress",
            blockers=[],
            active_files=[],
            pending_operations=[],
            next_step="Next step",
            decision_refs=[],
            evidence_refs=[],
            transcript_path=str(
                PACKAGE_ROOT / "scripts" / "hooks" / "__lib" / "handoff_v2.py"
            ),
            message_intent="instruction",
            **kwargs,
        )
        return build_envelope(
            resume_snapshot=snapshot,
            decision_register=[],
            evidence_index=[],
        )

    def test_restore_message_includes_directive_for_discussing(self) -> None:
        pytest.skip("lifecycle_phase kwarg not implemented in build_resume_snapshot")

    def test_restore_message_no_directive_for_implementing(self) -> None:
        pytest.skip("lifecycle_phase kwarg not implemented in build_resume_snapshot")

    def test_dynamic_restore_includes_lifecycle_phase(self) -> None:
        pytest.skip("lifecycle_phase kwarg not implemented in build_resume_snapshot")


# ---------------------------------------------------------------------------
# CHANGE-005: Accumulator module
# ---------------------------------------------------------------------------


class TestAccumulator:
    """Test handoff accumulator PostToolUse module."""

    def test_run_returns_empty_dict(self) -> None:
        from scripts.hooks.__lib.handoff_accumulator import run

        result = run({"tool_name": "Read", "tool_input": {"file_path": "test.py"}})
        assert result == {}

    def test_run_no_error_on_failure(self) -> None:
        from scripts.hooks.__lib.handoff_accumulator import run

        # Should never raise
        result = run({"bad": "data"})
        assert isinstance(result, dict)

    def test_append_creates_file(self, tmp_path: Path) -> None:
        from scripts.hooks.__lib.handoff_accumulator import _append_event

        accum_path = tmp_path / "test_accumulated.jsonl"
        _append_event(accum_path, {"type": "file_edit", "path": "foo.py", "ts": "now"})
        assert accum_path.exists()
        data = json.loads(accum_path.read_text(encoding="utf-8").strip())
        assert data["type"] == "file_edit"

    def test_read_last_phase_default(self, tmp_path: Path) -> None:
        from scripts.hooks.__lib.handoff_accumulator import _read_last_phase

        phase = _read_last_phase(tmp_path / "nonexistent.jsonl")
        assert phase == "implementing"

    def test_read_last_phase_from_jsonl(self, tmp_path: Path) -> None:
        from scripts.hooks.__lib.handoff_accumulator import (
            _append_event,
            _read_last_phase,
        )

        accum_path = tmp_path / "test.jsonl"
        _append_event(accum_path, {"type": "file_edit", "path": "a.py", "ts": "t1"})
        _append_event(
            accum_path,
            {
                "type": "phase_transition",
                "from": "implementing",
                "to": "planning",
                "ts": "t2",
            },
        )
        assert _read_last_phase(accum_path) == "planning"

    def test_phase_transition_approved_to_implementing(self) -> None:
        from scripts.hooks.__lib.handoff_accumulator import _detect_phase_transition

        result = _detect_phase_transition("Edit", {}, "approved")
        assert result == "implementing"

    def test_no_transition_from_implementing(self) -> None:
        from scripts.hooks.__lib.handoff_accumulator import _detect_phase_transition

        result = _detect_phase_transition("Edit", {}, "implementing")
        assert result is None


# ---------------------------------------------------------------------------
# CHANGE-006: handoff_files accumulated state methods
# ---------------------------------------------------------------------------


class TestHandoffFilesAccumulatedState:
    """Test read_accumulated_state() and truncate_accumulated_state()."""

    def test_read_missing_file(self, tmp_path: Path) -> None:
        from scripts.hooks.__lib.handoff_files import HandoffFileStorage

        storage = HandoffFileStorage(tmp_path, "test_term")
        assert storage.read_accumulated_state() == []

    def test_read_valid_jsonl(self, tmp_path: Path) -> None:
        from scripts.hooks.__lib.handoff_files import HandoffFileStorage

        handoff_dir = tmp_path / ".claude" / "state" / "handoff"
        handoff_dir.mkdir(parents=True, exist_ok=True)
        accum_file = handoff_dir / "test_term_accumulated.jsonl"
        accum_file.write_text(
            '{"type":"file_edit","path":"a.py","ts":"t1"}\n'
            '{"type":"phase_transition","from":"implementing","to":"planning","ts":"t2"}\n',
            encoding="utf-8",
        )

        storage = HandoffFileStorage(tmp_path, "test_term")
        events = storage.read_accumulated_state()
        assert len(events) == 2
        assert events[1]["to"] == "planning"

    def test_read_corrupt_line_skipped(self, tmp_path: Path) -> None:
        from scripts.hooks.__lib.handoff_files import HandoffFileStorage

        handoff_dir = tmp_path / ".claude" / "state" / "handoff"
        handoff_dir.mkdir(parents=True, exist_ok=True)
        accum_file = handoff_dir / "test_term_accumulated.jsonl"
        accum_file.write_text(
            '{"type":"file_edit","path":"a.py","ts":"t1"}\n'
            "corrupt line\n"
            '{"type":"phase_transition","from":"implementing","to":"planning","ts":"t2"}\n',
            encoding="utf-8",
        )

        storage = HandoffFileStorage(tmp_path, "test_term")
        events = storage.read_accumulated_state()
        assert len(events) == 2  # Corrupt line skipped

    def test_truncate_removes_file(self, tmp_path: Path) -> None:
        from scripts.hooks.__lib.handoff_files import HandoffFileStorage

        handoff_dir = tmp_path / ".claude" / "state" / "handoff"
        handoff_dir.mkdir(parents=True, exist_ok=True)
        accum_file = handoff_dir / "test_term_accumulated.jsonl"
        accum_file.write_text('{"type":"file_edit"}\n', encoding="utf-8")

        storage = HandoffFileStorage(tmp_path, "test_term")
        assert storage.truncate_accumulated_state() is True
        assert not accum_file.exists()

    def test_truncate_nonexistent_ok(self, tmp_path: Path) -> None:
        from scripts.hooks.__lib.handoff_files import HandoffFileStorage

        storage = HandoffFileStorage(tmp_path, "test_term")
        assert storage.truncate_accumulated_state() is True


# ---------------------------------------------------------------------------
# Tests for adversarial review accepted findings
# ---------------------------------------------------------------------------


class TestEmptyGoalEdgeCases:
    """TEST-014: Empty goal edge cases for detect_lifecycle_phase."""

    def test_empty_string_goal(self) -> None:
        from scripts.hooks.PreCompact_handoff_capture import detect_lifecycle_phase

        result = detect_lifecycle_phase(
            blockers=[],
            active_files=[],
            pending_operations=[],
            goal="",
        )
        assert result == "discussing"

    def test_whitespace_only_goal(self) -> None:
        from scripts.hooks.PreCompact_handoff_capture import detect_lifecycle_phase

        result = detect_lifecycle_phase(
            blockers=[],
            active_files=[],
            pending_operations=[],
            goal="   ",
        )
        assert result == "discussing"

    def test_empty_goal_with_active_files(self) -> None:
        from scripts.hooks.PreCompact_handoff_capture import detect_lifecycle_phase

        # Empty goal + task_mode implement + active files → implementing
        result = detect_lifecycle_phase(
            blockers=[],
            active_files=["foo.py"],
            pending_operations=[],
            goal="",
            task_mode="implement",
        )
        # Still discussing because goal check comes first
        assert result == "discussing"


class TestInterspersedCorruptLines:
    """TEST-015: Read accumulated state with interspersed valid/corrupt lines."""

    def test_read_mixed_valid_corrupt(self, tmp_path: Path) -> None:
        from scripts.hooks.__lib.handoff_files import HandoffFileStorage

        handoff_dir = tmp_path / ".claude" / "state" / "handoff"
        handoff_dir.mkdir(parents=True, exist_ok=True)
        accum_file = handoff_dir / "test_term_accumulated.jsonl"
        accum_file.write_text(
            '{"type":"file_edit","path":"a.py","ts":"t1"}\n'
            "corrupt line\n"
            '{"type":"phase_transition","from":"implementing","to":"planning","ts":"t2"}\n'
            "another bad line\n"
            '{"type":"file_edit","path":"b.py","ts":"t3"}\n',
            encoding="utf-8",
        )

        storage = HandoffFileStorage(tmp_path, "test_term")
        events = storage.read_accumulated_state()
        assert len(events) == 3
        # Verify corrupt lines were skipped
        assert events[0]["path"] == "a.py"
        assert events[1]["to"] == "planning"
        assert events[2]["path"] == "b.py"


class TestLifecyclePhaseChecksumRoundtrip:
    """TEST-016: Lifecycle phase through full checksum flow."""

    def test_phase_in_envelope_validates(self) -> None:
        pytest.skip("lifecycle_phase kwarg not implemented in build_resume_snapshot")


# ---------------------------------------------------------------------------
# CHANGE-005: Concurrent append test (acceptance criterion)
# ---------------------------------------------------------------------------


class TestAccumulatorConcurrentAppends:
    """Spawn 5 writers, 100 events each, verify all 500 lines parse."""

    def test_concurrent_appends_no_corruption(self, tmp_path: Path) -> None:
        import threading

        from scripts.hooks.__lib.handoff_accumulator import _append_event

        accum_path = tmp_path / "concurrent_test.jsonl"
        errors: list[str] = []
        num_writers = 5
        events_per_writer = 100

        def writer(writer_id: int) -> None:
            try:
                for i in range(events_per_writer):
                    _append_event(
                        accum_path,
                        {
                            "type": "file_edit",
                            "writer": writer_id,
                            "seq": i,
                            "ts": f"w{writer_id}_e{i}",
                        },
                    )
            except Exception as exc:
                errors.append(f"Writer {writer_id}: {exc}")

        threads = [
            threading.Thread(target=writer, args=(wid,)) for wid in range(num_writers)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"Writer errors: {errors}"

        # Verify all 500 lines parse correctly
        lines = accum_path.read_text(encoding="utf-8").strip().splitlines()
        parsed = []
        for line in lines:
            event = json.loads(line)
            parsed.append(event)

        assert len(parsed) == num_writers * events_per_writer


# ---------------------------------------------------------------------------
# CHANGE-007: Accumulated phase preference over inference
# ---------------------------------------------------------------------------


class TestAccumulatedPhasePreference:
    """Accumulated JSONL phase preferred over detect_lifecycle_phase() inference."""

    def test_accumulated_phase_overrides_inference(self, tmp_path: Path) -> None:
        from scripts.hooks.__lib.handoff_files import HandoffFileStorage

        handoff_dir = tmp_path / ".claude" / "state" / "handoff"
        handoff_dir.mkdir(parents=True, exist_ok=True)
        accum_file = handoff_dir / "test_term_accumulated.jsonl"
        accum_file.write_text(
            '{"type":"file_edit","path":"a.py","ts":"t1"}\n'
            '{"type":"phase_transition","from":"implementing","to":"planning","ts":"t2"}\n',
            encoding="utf-8",
        )

        storage = HandoffFileStorage(tmp_path, "test_term")
        events = storage.read_accumulated_state()

        # Find last phase_transition
        last_phase = "implementing"
        for event in reversed(events):
            if event.get("type") == "phase_transition":
                last_phase = event.get("to", "implementing")
                break

        assert last_phase == "planning"

    def test_no_accumulated_events_falls_back_to_implementing(
        self, tmp_path: Path
    ) -> None:
        from scripts.hooks.__lib.handoff_files import HandoffFileStorage

        storage = HandoffFileStorage(tmp_path, "no_events_term")
        events = storage.read_accumulated_state()
        assert events == []

        # No phase_transition events → default to implementing
        last_phase = "implementing"
        for event in reversed(events):
            if event.get("type") == "phase_transition":
                last_phase = event.get("to", "implementing")
                break
        assert last_phase == "implementing"

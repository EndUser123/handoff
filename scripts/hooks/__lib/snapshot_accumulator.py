#!/usr/bin/env python3
"""PostToolUse accumulator for incremental handoff state.

Registered as an in-process module in the PostToolUse registry via
create_registry(). NOT a standalone stdin script.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.hooks.__lib.snapshot_store import FileLock

logger = logging.getLogger(__name__)

VALID_PHASES = {"discussing", "planning", "approved", "implementing", "reviewing"}


def _get_accumulator_path(terminal_id: str, project_root: Path) -> Path:
    """Return the per-terminal JSONL accumulator path."""
    handoff_dir = project_root / ".claude" / "state" / "handoff"
    handoff_dir.mkdir(parents=True, exist_ok=True)
    return handoff_dir / f"{terminal_id}_accumulated.jsonl"


def _append_event(path: Path, event: dict[str, Any]) -> None:
    """Append a single JSONL line with FileLock for Windows safety."""
    line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    lock_path = path.with_suffix(".lock")
    with FileLock(lock_path, timeout=2.0):
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def _read_last_phase(accum_path: Path) -> str:
    """Read the last known phase from accumulated JSONL, or default to implementing."""
    if not accum_path.exists():
        return "implementing"
    try:
        with open(accum_path, encoding="utf-8") as f:
            for line in reversed(list(f)):
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    if event.get("type") == "phase_transition":
                        return event.get("to", "implementing")
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return "implementing"


def _detect_phase_transition(
    tool_name: str,
    tool_input: dict[str, Any],
    current_phase: str,
) -> str | None:
    """Detect if a phase transition should occur. Returns new phase or None."""
    # Edit/Write after approval -> implementing
    if current_phase == "approved" and tool_name in ("Edit", "Write"):
        return "implementing"

    # No transition detected
    return None


def run(data: dict[str, Any]) -> dict[str, Any]:
    """PostToolUse accumulator entry point (in-process module interface).

    Args:
        data: PostToolUse payload from Claude Code.

    Returns:
        Empty dict (no injection output).
    """
    try:
        tool_name = data.get("tool_name", "")
        tool_input = data.get("tool_input", {})

        # Derive terminal_id and project root
        terminal_id = data.get(
            "terminal_id", os.environ.get("CLAUDE_TERMINAL_ID", "default")
        )
        project_root_str = os.environ.get("SNAPSHOT_PROJECT_ROOT")
        if project_root_str:
            project_root = Path(project_root_str)
        else:
            project_root = Path(__file__).resolve().parents[2]

        accum_path = _get_accumulator_path(terminal_id, project_root)
        now = datetime.now(UTC).isoformat()

        # Record file edits
        if tool_name in ("Edit", "Write"):
            file_path = tool_input.get("file_path", "")
            if file_path:
                _append_event(
                    accum_path,
                    {
                        "type": "file_edit",
                        "path": file_path,
                        "ts": now,
                    },
                )

        # Phase transition detection -- read current phase from JSONL
        current_phase = _read_last_phase(accum_path)
        transition = _detect_phase_transition(tool_name, tool_input, current_phase)
        if transition:
            _append_event(
                accum_path,
                {
                    "type": "phase_transition",
                    "from": current_phase,
                    "to": transition,
                    "ts": now,
                    "trigger": f"{tool_name} tool",
                },
            )

    except Exception as exc:
        # Accumulator is best-effort -- never block the tool pipeline
        # But log the failure for debugging instead of silent swallowing
        logger.debug("[snapshot_accumulator] Failed: %s", exc)

    return {}


if __name__ == "__main__":
    # Standalone invocation for testing only
    import sys

    raw = sys.stdin.read().strip()
    if raw:
        result = run(json.loads(raw))
        print(json.dumps(result))
    else:
        print("{}")

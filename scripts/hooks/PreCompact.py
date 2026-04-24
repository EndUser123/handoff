#!/usr/bin/env python3
"""
PreCompact - Lean Router v2.0
=============================

Replaces monolithic PreCompact_handoff_router.py.
Ensures session continuity by capturing handoff and checkpoint state before compaction.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

_HOOKS_DIR = Path(__file__).resolve().parent
try:
    _HOOK_TIMEOUT = float(os.environ.get("PRECOMPACT_HOOK_TIMEOUT", "30.0"))
except ValueError:
    _HOOK_TIMEOUT = 30.0
_log = logging.getLogger(__name__)

# sequence (Priority-ordered)
SEQUENCE = [
    "PreCompact_handoff_capture.py",
    "PreCompact_commitment_tracker.py",
]


def run_task(hook_name: str, input_data: str):
    """Run a child hook, return structured dict or None on silent success."""
    hook_path = _HOOKS_DIR / hook_name
    creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        result = subprocess.run(
            [sys.executable, hook_path.as_posix()],
            input=input_data.encode(),
            capture_output=True,
            timeout=_HOOK_TIMEOUT,
            creationflags=creation_flags,
        )
        stdout_text = result.stdout.decode(errors="replace").strip()
        stderr_text = result.stderr.decode(errors="replace").strip()

        if stdout_text:
            try:
                hook_output = json.loads(stdout_text)
                if isinstance(hook_output, dict) and "additionalContext" in hook_output:
                    return {"type": "warning", "hook": hook_name, "message": hook_output["additionalContext"]}
                else:
                    return {"type": "warning", "hook": hook_name, "message": f"{hook_name}: {stdout_text}"}
            except json.JSONDecodeError:
                return {"type": "warning", "hook": hook_name, "message": f"{hook_name}: {stdout_text}"}

        if result.returncode != 0:
            return {"type": "error", "hook": hook_name, "exit_code": result.returncode, "message": f"{hook_name}: exit={result.returncode} {stderr_text}".strip()}

        return None
    except subprocess.TimeoutExpired:
        return {"type": "error", "hook": hook_name, "exit_code": -1, "message": f"{hook_name}: timeout after {_HOOK_TIMEOUT}s (see PRECOMPACT_HOOK_TIMEOUT env var)"}
    except FileNotFoundError:
        return {"type": "error", "hook": hook_name, "exit_code": -1, "message": f"{hook_name}: not found at {hook_path}"}
    except Exception as e:
        return {"type": "error", "hook": hook_name, "exit_code": -1, "message": f"{hook_name}: exception={type(e).__name__}: {e}"}


_REQUIRED_INPUT_FIELDS = frozenset({"session_id", "transcript_path", "cwd", "hook_event_name", "trigger"})


def main():
    raw_input = sys.stdin.read().strip()
    if not raw_input:
        sys.exit(0)

    try:
        raw_input = raw_input.lstrip("\ufeff")
        data = json.loads(raw_input)
    except json.JSONDecodeError:
        print(json.dumps({"decision": "block", "reason": "PreCompact: invalid JSON input"}))
        sys.exit(1)

    missing = _REQUIRED_INPUT_FIELDS - set(data.keys())
    if missing:
        reason = f"PreCompact: missing required fields: {', '.join(sorted(missing))}"
        _log.warning(reason)
        print(json.dumps({"decision": "block", "reason": reason}))
        sys.exit(1)

    warnings, errors = [], []
    for task_name in SEQUENCE:
        result = run_task(task_name, json.dumps(data))
        if result:
            warnings.append(result)
            if result["type"] == "error":
                errors.append(result)

    for w in warnings:
        _log.warning("%s: %s", w["hook"], w["message"])

    if errors:
        error_summaries = "; ".join(e["message"] for e in errors)
        print(json.dumps({"decision": "block", "reason": f"PreCompact child hook(s) failed: {error_summaries}"}))
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()

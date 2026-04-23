#!/usr/bin/env python3
"""SessionStart restore hook for Handoff V2."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

# sys.path must be set up BEFORE importing scripts.hooks modules
PACKAGE_ROOT = Path(__file__).resolve().parents[2]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from scripts.hooks.userpromptsubmit_task_injector import _clear_marker

logger = logging.getLogger(__name__)

# Configure logging to ensure diagnostic output is captured
# Logs will be written to .claude/logs/handoff_restore.log
_log_file_path = (
    Path(__file__).resolve().parents[2] / ".claude" / "logs" / "handoff_restore.log"
)
_log_file_path.parent.mkdir(parents=True, exist_ok=True)
if not logger.handlers:
    _handler = logging.FileHandler(_log_file_path, encoding="utf-8")
    _handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    logger.addHandler(_handler)
logger.setLevel(logging.DEBUG)

from scripts.hooks.__lib.handoff_files import HandoffFileStorage
from scripts.hooks.__lib.handoff_v2 import (
    SNAPSHOT_CONSUMED,
    SNAPSHOT_REJECTED_INVALID,
    SNAPSHOT_REJECTED_STALE,
    build_no_snapshot_hint,
    build_restore_message_dynamic,
    build_stale_hint,
    compute_checksum,
    evaluate_for_restore,
)
from scripts.hooks.__lib.hook_input_validation import (
    HookInputError,
    validate_hook_input,
)
from scripts.hooks.__lib.terminal_detection import resolve_terminal_key
from scripts.hooks.__lib.project_root import detect_project_root


def _read_hook_input() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        raise ValueError("SessionStart hook received empty stdin")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("SessionStart hook input must be a JSON object")
    return payload


def _normalize_session_start_source(input_data: dict[str, Any]) -> str | None:
    source = input_data.get("source")
    trigger = input_data.get("trigger")

    values = []
    if isinstance(source, str):
        values.append(source.strip().lower())
    if isinstance(trigger, str):
        values.append(trigger.strip().lower())

    compact_markers = {
        "compact",
        "post_compact",
        "post-compact",
        "resume_after_compact",
        "compaction",
    }

    for value in values:
        if value in compact_markers:
            return "compact"

    return None


def _build_output(reason: str, additional_context: str | None = None) -> dict[str, Any]:
    output: dict[str, Any] = {"decision": "approve", "reason": reason}
    if additional_context:
        output["additionalContext"] = additional_context
    return output


def _reject_if_possible(
    storage: HandoffFileStorage,
    payload: dict[str, Any] | None,
    *,
    session_id: str,
    status: str,
    reason: str,
) -> None:
    if not payload:
        return
    try:
        storage.update_snapshot_status_from_payload(
            payload,
            status=status,
            session_id=session_id,
            reason=reason,
        )
    except Exception as exc:
        logger.warning("[SessionStart V2] Failed to persist rejection state: %s", exc)


def main() -> None:
    """Restore a fresh V2 handoff snapshot after compact."""
    try:
        input_data = _read_hook_input()
        validate_hook_input(input_data, hook_type="SessionStart")

        session_id = input_data.get("session_id", "")
        terminal_id = resolve_terminal_key(input_data.get("terminal_id"))
        source = _normalize_session_start_source(input_data)

        # Write active-session file for multi-terminal session detection (used by chs_cli.py)
        # This enables /chs export to auto-detect the current session without --session-id
        if session_id and terminal_id:
            try:
                active_session_file = (
                    Path.home() / ".claude" / f"active-session-{terminal_id}.txt"
                )
                active_session_file.parent.mkdir(parents=True, exist_ok=True)
                tmp = active_session_file.with_suffix(".tmp")
                tmp.write_text(session_id + "\n")
                if active_session_file.exists():
                    active_session_file.unlink()
                tmp.rename(active_session_file)
            except Exception as exc:
                logger.warning(
                    "[SessionStart V2] Failed to write active-session file: %s", exc
                )

        # CRITICAL: For handoff package, detect project root with testing support
        # Priority: 1) HANDOFF_PROJECT_ROOT env var (for testing), 2) cwd (production)
        # Use Path.cwd() instead of __file__-derived path because Claude Code
        # invokes hooks as plugin commands from the project root (cwd = P:/), while
        # __file__ resolves to P:/packages/handoff/scripts/hooks/. This ensures
        # state files are read from P:/.claude/ (project root) not P:/packages/handoff/.claude/
        env_project_root = os.environ.get("HANDOFF_PROJECT_ROOT")
        if env_project_root:
            project_root = Path(env_project_root)
            logger.info(
                f"[SessionStart V2] Using project root from environment: {project_root}"
            )
        else:
            project_root = detect_project_root(current_dir=Path.cwd(), strict=False)
            logger.info(
                f"[SessionStart V2] Using project root from detect_project_root: {project_root}"
            )
        storage = HandoffFileStorage(project_root, terminal_id)
        raw_payload = storage.load_raw_handoff()

        if not raw_payload:
            print(
                json.dumps(
                    _build_output(
                        "No previous handoff found - starting fresh session",
                        build_no_snapshot_hint("no handoff file for this terminal"),
                    ),
                    indent=2,
                )
            )
            sys.exit(0)

        # CRITICAL: Verify checksum before attempting restore
        # LOGIC-002: Reject missing checksum field (inverted from allow-through)
        stored_checksum = raw_payload.get("checksum")
        if not stored_checksum:
            logger.error(
                "[SessionStart V2] Missing checksum field - rejecting restore as unsafe"
            )
            print(
                json.dumps(
                    _build_output(
                        "No safe current handoff found - checksum field missing",
                        build_no_snapshot_hint(
                            "checksum field missing - data may be incomplete"
                        ),
                    ),
                    indent=2,
                )
            )
            sys.exit(0)

        # QUAL-002: Use ERROR level for checksum mismatches (consistent with handoff_files.py)
        computed_checksum = compute_checksum(raw_payload)
        if computed_checksum != stored_checksum:
            logger.error(
                "[SessionStart V2] Checksum mismatch: expected=%s, computed=%s",
                stored_checksum,
                computed_checksum,
            )
            # Reject handoff with invalid checksum
            print(
                json.dumps(
                    _build_output(
                        "No safe current handoff found - checksum validation failed",
                        build_no_snapshot_hint(
                            "checksum mismatch - data may be corrupted"
                        ),
                    ),
                    indent=2,
                )
            )
            sys.exit(0)

        restore_decision = evaluate_for_restore(
            raw_payload,
            terminal_id=terminal_id,
            source=source,
            project_root=storage.project_root,
        )
        if restore_decision.ok and restore_decision.envelope:
            restoration_message = build_restore_message_dynamic(
                restore_decision.envelope,
                restore_session_id=session_id,
            )
            storage.update_snapshot_status(
                status=SNAPSHOT_CONSUMED,
                session_id=session_id,
                reason="restored after compact",
            )
            # Clear the UPS marker so UserPromptSubmit doesn't re-inject the same snapshot
            _clear_marker(terminal_id)

            # TASK-6: Inject conversation_summary into restore message
            # Field takes precedence; sidecar is fallback for older handoffs
            summary_text: str | None = None
            snapshot = restore_decision.envelope.get("resume_snapshot", {})
            if snapshot.get("conversation_summary"):
                summary_text = snapshot["conversation_summary"]
            elif snapshot.get("n_1_transcript_path"):
                # Fallback: check sidecar for older handoffs without field
                try:
                    from scripts.hooks.__lib.handoff_files import load_summary_for_envelope
                    envelope_path = Path(storage.handoff_file)
                    sidecar_text = load_summary_for_envelope(envelope_path)
                    if sidecar_text and sidecar_text.strip().upper() != "SKIP":
                        summary_text = sidecar_text
                except Exception:
                    pass

            if summary_text:
                # Inject summary into additionalContext under ## Session Summary
                summary_block = f"\n\n## Session Summary\n\n{summary_text}"
                restoration_message = restoration_message + summary_block

            # ADR-006: Inject verbatim last user message for post-compact disambiguation
            last_user_msg = snapshot.get("last_user_message")
            if last_user_msg and isinstance(last_user_msg, str) and last_user_msg.strip():
                restoration_message += f"\n\n**Last user message (verbatim):** {last_user_msg.strip()}"

            print(
                json.dumps(
                    _build_output(
                        "Restored previous session context", restoration_message
                    ),
                    indent=2,
                )
            )
            sys.exit(0)

        reason = restore_decision.reason or "restore rejected"
        payload = raw_payload if isinstance(raw_payload, dict) else None

        if reason == "snapshot expired" or reason.startswith("snapshot evidence "):
            _reject_if_possible(
                storage,
                payload,
                session_id=session_id,
                status=SNAPSHOT_REJECTED_STALE,
                reason=reason,
            )
            message = (
                build_stale_hint(payload, reason)
                if payload
                else build_no_snapshot_hint(reason)
            )
            output_reason = "No safe current handoff found - stale snapshot rejected"
        elif reason.startswith("invalid handoff:") or reason == "terminal mismatch":
            _reject_if_possible(
                storage,
                payload,
                session_id=session_id,
                status=SNAPSHOT_REJECTED_INVALID,
                reason=reason,
            )
            message = build_no_snapshot_hint(reason)
            output_reason = "No safe current handoff found - invalid snapshot rejected"
        else:
            message = build_no_snapshot_hint(reason)
            output_reason = "No safe current handoff restored - starting fresh session"

        print(json.dumps(_build_output(output_reason, message), indent=2))
        sys.exit(0)

    except HookInputError as exc:
        print(
            json.dumps(
                {
                    "decision": "error",
                    "reason": f"Hook input validation failed: {exc}",
                    "additionalContext": (
                        "Handoff V2 restore could not validate the SessionStart payload. "
                        f"Details: {exc}"
                    ),
                },
                indent=2,
            )
        )
        sys.exit(1)
    except Exception as exc:
        logger.error("[SessionStart V2] Restore failed: %s", exc)
        print(
            json.dumps(
                _build_output(
                    "Handoff restore failed - starting fresh",
                    f"⚠️ Handoff V2 restore error: {exc}",
                ),
                indent=2,
            )
        )
        sys.exit(0)


if __name__ == "__main__":
    main()

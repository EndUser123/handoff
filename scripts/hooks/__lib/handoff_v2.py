#!/usr/bin/env python3
"""Handoff V2 schema, validation, and restore formatting utilities."""

from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

# Import dynamic sections for content generation
from scripts.hooks.__lib import dynamic_sections  # type: ignore

SCHEMA_VERSION = 2
DEFAULT_FRESHNESS_MINUTES = int(os.getenv("HANDOFF_FRESHNESS_MINUTES", "20"))
SNAPSHOT_PENDING = "pending"
SNAPSHOT_CONSUMED = "consumed"
SNAPSHOT_REJECTED_STALE = "rejected_stale"
SNAPSHOT_REJECTED_INVALID = "rejected_invalid"
VALID_SNAPSHOT_STATUSES = {
    SNAPSHOT_PENDING,
    SNAPSHOT_CONSUMED,
    SNAPSHOT_REJECTED_STALE,
    SNAPSHOT_REJECTED_INVALID,
}

# Valid state transitions: from_state -> {allowed_to_states}
VALID_STATE_TRANSITIONS: dict[str, set[str]] = {
    SNAPSHOT_PENDING: {
        SNAPSHOT_CONSUMED,
        SNAPSHOT_REJECTED_STALE,
        SNAPSHOT_REJECTED_INVALID,
    },
    SNAPSHOT_CONSUMED: set(),  # Terminal state
    SNAPSHOT_REJECTED_STALE: set(),  # Terminal state
    SNAPSHOT_REJECTED_INVALID: set(),  # Terminal state
}
VALID_DECISION_KINDS = {"constraint", "settled_decision", "blocker_rule", "anti_goal"}
VALID_EVIDENCE_TYPES = {"file", "transcript", "test", "log", "git"}
VALID_MESSAGE_INTENTS = {
    "question",
    "instruction",
    "correction",
    "meta",
    "unsupported_language",
    "directive",  # Added for imperative commands (detect_message_intent returns this)
}
OPTIONAL_DECISION_FIELDS = set()  # Optional fields allowed in decisions
OPTIONAL_SNAPSHOT_FIELDS = {"quality_score"}  # Optional fields allowed in snapshot
MUTABLE_METADATA_FIELDS = {
    "consumed_at",
    "consumed_by_session_id",
    "rejected_at",
    "rejected_by_session_id",
    "rejection_reason",
    "message_intent",  # Excluded from checksum - intent classification doesn't affect content validity
}


class HandoffValidationError(ValueError):
    """Raised when a V2 handoff envelope is malformed."""


@dataclass(slots=True)
class RestoreDecision:
    """Result of evaluating a V2 snapshot for automatic restore."""

    ok: bool
    reason: str | None = None
    envelope: dict[str, Any] | None = None


def utcnow() -> datetime:
    """Return the current UTC time."""
    return datetime.now(UTC)


def iso_now() -> str:
    """Return the current UTC time as ISO-8601."""
    return utcnow().isoformat()


def parse_iso8601(value: str) -> datetime:
    """Parse an ISO-8601 datetime string."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def make_decision_id() -> str:
    """Return a stable decision identifier using full UUID to prevent collisions."""
    return f"dec_{uuid4().hex}"


def make_evidence_id() -> str:
    """Return a stable evidence identifier using full UUID to prevent collisions."""
    return f"ev_{uuid4().hex}"


def _normalize_for_checksum(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(payload)
    normalized.pop("checksum", None)

    snapshot = normalized.get("resume_snapshot", {})
    if isinstance(snapshot, dict):
        for field in MUTABLE_METADATA_FIELDS:
            snapshot.pop(field, None)

    return normalized


def compute_checksum(payload: dict[str, Any]) -> str:
    """Compute the V2 envelope checksum."""
    normalized = _normalize_for_checksum(payload)
    serialized = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"


def compute_file_content_hash(path: str | Path) -> str | None:
    """Return a stable content hash for a file, or None if unreadable."""
    try:
        target = Path(path)
        if not target.exists() or not target.is_file():
            return None
        digest = hashlib.sha256()
        with open(target, "rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        return f"sha256:{digest.hexdigest()}"
    except OSError:
        return None


def _require_fields(obj: dict[str, Any], fields: list[str], prefix: str) -> None:
    missing = [field for field in fields if field not in obj]
    if missing:
        raise HandoffValidationError(
            f"{prefix} missing required fields: {', '.join(missing)}"
        )


def validate_envelope(payload: dict[str, Any]) -> None:
    """Validate the V2 handoff envelope."""
    if not isinstance(payload, dict):
        raise HandoffValidationError("handoff payload must be a dict")

    _require_fields(
        payload, ["resume_snapshot", "decision_register", "evidence_index"], "envelope"
    )

    snapshot = payload["resume_snapshot"]
    decisions = payload["decision_register"]
    evidence = payload["evidence_index"]

    if not isinstance(snapshot, dict):
        raise HandoffValidationError("resume_snapshot must be a dict")
    if not isinstance(decisions, list):
        raise HandoffValidationError("decision_register must be a list")
    if not isinstance(evidence, list):
        raise HandoffValidationError("evidence_index must be a list")

    _require_fields(
        snapshot,
        [
            "schema_version",
            "snapshot_id",
            "terminal_id",
            "source_session_id",
            "created_at",
            "expires_at",
            "status",
            "goal",
            "current_task",
            "progress_percent",
            "progress_state",
            "blockers",
            "active_files",
            "pending_operations",
            "next_step",
            "decision_refs",
            "evidence_refs",
            "transcript_path",
        ],
        "resume_snapshot",
    )

    if snapshot["schema_version"] != SCHEMA_VERSION:
        raise HandoffValidationError(
            f"unsupported schema_version: {snapshot['schema_version']}"
        )

    if snapshot["status"] not in VALID_SNAPSHOT_STATUSES:
        raise HandoffValidationError(
            f"invalid resume_snapshot.status: {snapshot['status']}"
        )

    for field in [
        "goal",
        "current_task",
        "next_step",
        "terminal_id",
        "source_session_id",
    ]:
        if not isinstance(snapshot[field], str):
            raise HandoffValidationError(f"resume_snapshot.{field} must be a string")

    for field in [
        "active_files",
        "pending_operations",
        "blockers",
        "decision_refs",
        "evidence_refs",
    ]:
        if not isinstance(snapshot[field], list):
            raise HandoffValidationError(f"resume_snapshot.{field} must be a list")

    if not isinstance(snapshot["progress_percent"], int):
        raise HandoffValidationError(
            "resume_snapshot.progress_percent must be an integer"
        )
    if snapshot["progress_percent"] < 0 or snapshot["progress_percent"] > 100:
        raise HandoffValidationError(
            "resume_snapshot.progress_percent must be between 0 and 100"
        )

    parse_iso8601(snapshot["created_at"])
    parse_iso8601(snapshot["expires_at"])

    # Validate transcript_path exists and is safe (SEC-001: Path traversal protection)
    transcript_path = snapshot.get("transcript_path")
    if isinstance(transcript_path, str) and transcript_path:
        transcript_file = Path(transcript_path).resolve()

        # SEC-001: Find project root by locating .claude directory in path hierarchy
        # This is more flexible than using cwd() and works in test environments
        project_root = None
        current = transcript_file
        for _ in range(5):  # Check up to 5 levels up
            if (current / ".claude").exists():
                project_root = current
                break
            parent = current.parent
            if parent == current:  # Reached filesystem root
                break
            current = parent

        # If no .claude directory found, reject the path as unsafe
        # SEC-001: Path security requires project boundary verification
        if project_root is None:
            raise HandoffValidationError(
                "resume_snapshot.transcript_path must be within project directory (no .claude boundary found)"
            )

        # SEC-001: Verify path is within project root to prevent traversal attacks
        try:
            transcript_file.relative_to(project_root)
        except ValueError:
            raise HandoffValidationError(
                "resume_snapshot.transcript_path must be within project directory"
            )

        # SEC-002: Sanitized error messages (don't leak actual paths)
        if not transcript_file.exists():
            raise HandoffValidationError(
                "resume_snapshot.transcript_path file does not exist"
            )
        if not transcript_file.is_file():
            raise HandoffValidationError(
                "resume_snapshot.transcript_path is not a file"
            )

    decision_ids = set()
    for index, decision in enumerate(decisions):
        if not isinstance(decision, dict):
            raise HandoffValidationError(f"decision_register[{index}] must be a dict")
        _require_fields(
            decision,
            [
                "id",
                "kind",
                "summary",
                "details",
                "priority",
                "applies_when",
                "source_refs",
            ],
            f"decision_register[{index}]",
        )
        if decision["kind"] not in VALID_DECISION_KINDS:
            raise HandoffValidationError(f"decision_register[{index}].kind is invalid")
        decision_ids.add(decision["id"])

    evidence_ids = set()
    for index, item in enumerate(evidence):
        if not isinstance(item, dict):
            raise HandoffValidationError(f"evidence_index[{index}] must be a dict")
        _require_fields(
            item, ["id", "type", "label", "path"], f"evidence_index[{index}]"
        )
        if item["type"] not in VALID_EVIDENCE_TYPES:
            raise HandoffValidationError(f"evidence_index[{index}].type is invalid")
        evidence_ids.add(item["id"])

    for ref in snapshot["decision_refs"]:
        if ref not in decision_ids:
            raise HandoffValidationError(
                f"resume_snapshot.decision_refs contains unknown id: {ref}"
            )

    for ref in snapshot["evidence_refs"]:
        if ref not in evidence_ids:
            raise HandoffValidationError(
                f"resume_snapshot.evidence_refs contains unknown id: {ref}"
            )

    # LOGIC-002: Require checksum field - reject envelopes without checksum
    checksum = payload.get("checksum")
    if checksum is None:
        raise HandoffValidationError("resume_snapshot.checksum is required")
    if checksum != compute_checksum(payload):
        raise HandoffValidationError("handoff checksum mismatch")


def build_resume_snapshot(
    *,
    terminal_id: str,
    source_session_id: str,
    goal: str,
    current_task: str,
    progress_percent: int,
    progress_state: str,
    blockers: list[dict[str, Any]],
    active_files: list[str],
    pending_operations: list[dict[str, Any]],
    next_step: str,
    decision_refs: list[str],
    evidence_refs: list[str],
    transcript_path: str,
    message_intent: str,  # Intent classification of the goal (required)
    freshness_minutes: int = DEFAULT_FRESHNESS_MINUTES,
    quality_score: float | None = None,
    tasks_snapshot: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the V2 resume snapshot."""
    # QUAL-005: Validate message_intent is a recognized value
    if message_intent not in VALID_MESSAGE_INTENTS:
        raise ValueError(
            f"Invalid message_intent: '{message_intent}'. "
            f"Valid values: {sorted(VALID_MESSAGE_INTENTS)}"
        )

    now = utcnow()
    expires = now + timedelta(minutes=freshness_minutes)
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": str(uuid4()),
        "terminal_id": terminal_id,
        "source_session_id": source_session_id,
        "created_at": now.isoformat(),
        "expires_at": expires.isoformat(),
        "status": SNAPSHOT_PENDING,
        "goal": goal,
        "current_task": current_task,
        "progress_percent": max(0, min(100, progress_percent)),
        "progress_state": progress_state,
        "blockers": blockers,
        "active_files": active_files,
        "pending_operations": pending_operations,
        "next_step": next_step,
        "decision_refs": decision_refs,
        "evidence_refs": evidence_refs,
        "transcript_path": transcript_path,
        "message_intent": message_intent,  # Required field
    }
    if quality_score is not None:
        snapshot["quality_score"] = quality_score
    if tasks_snapshot is not None:
        snapshot["tasks_snapshot"] = tasks_snapshot
    return snapshot


def build_envelope(
    *,
    resume_snapshot: dict[str, Any],
    decision_register: list[dict[str, Any]],
    evidence_index: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build and checksum the V2 handoff envelope."""
    payload = {
        "resume_snapshot": resume_snapshot,
        "decision_register": decision_register,
        "evidence_index": evidence_index,
    }
    payload["checksum"] = compute_checksum(payload)
    return payload


def mark_snapshot_status(
    payload: dict[str, Any],
    *,
    status: str,
    session_id: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """Return a copy of the envelope with updated snapshot status.

    Raises:
        HandoffValidationError: If the status transition is invalid.
    """
    updated = deepcopy(payload)
    snapshot = updated["resume_snapshot"]
    current_status = snapshot["status"]

    # Validate state transition
    if status not in VALID_SNAPSHOT_STATUSES:
        raise HandoffValidationError(f"invalid target status: {status}")

    allowed_transitions = VALID_STATE_TRANSITIONS.get(current_status, set())
    if status not in allowed_transitions:
        raise HandoffValidationError(
            f"invalid state transition: {current_status} -> {status} "
            f"(allowed: {', '.join(sorted(allowed_transitions)) or 'none (terminal state)'})"
        )

    snapshot["status"] = status

    if status == SNAPSHOT_CONSUMED:
        snapshot["consumed_at"] = iso_now()
        snapshot["consumed_by_session_id"] = session_id
        snapshot.pop("rejected_at", None)
        snapshot.pop("rejected_by_session_id", None)
        snapshot.pop("rejection_reason", None)
    elif status in {SNAPSHOT_REJECTED_STALE, SNAPSHOT_REJECTED_INVALID}:
        snapshot["rejected_at"] = iso_now()
        snapshot["rejected_by_session_id"] = session_id
        snapshot["rejection_reason"] = reason or status
        snapshot.pop("consumed_at", None)
        snapshot.pop("consumed_by_session_id", None)

    updated["checksum"] = compute_checksum(updated)
    return updated


def evaluate_for_restore(
    payload: dict[str, Any],
    *,
    terminal_id: str,
    source: str | None,
    now: datetime | None = None,
) -> RestoreDecision:
    """Evaluate whether the snapshot is safe to auto-restore."""
    try:
        validate_envelope(payload)
    except HandoffValidationError as exc:
        return RestoreDecision(ok=False, reason=f"invalid handoff: {exc}")

    if source != "compact":
        return RestoreDecision(ok=False, reason="not a post-compact session start")

    snapshot = payload["resume_snapshot"]
    if snapshot["terminal_id"] != terminal_id:
        return RestoreDecision(ok=False, reason="terminal mismatch")

    if snapshot["status"] != SNAPSHOT_PENDING:
        return RestoreDecision(
            ok=False, reason=f"snapshot status is {snapshot['status']}"
        )

    current_time = now or utcnow()
    if parse_iso8601(snapshot["expires_at"]) < current_time:
        return RestoreDecision(ok=False, reason="snapshot expired")

    evidence_failure = verify_evidence_freshness(payload)
    if evidence_failure:
        return RestoreDecision(ok=False, reason=evidence_failure)

    return RestoreDecision(ok=True, envelope=payload)


def verify_evidence_freshness(payload: dict[str, Any]) -> str | None:
    """Reject restore when captured evidence no longer matches current disk state."""
    # SEC-001: Extract project root from validated transcript_path
    # The transcript_path has already been validated by validate_envelope()
    snapshot = payload.get("resume_snapshot", {})
    transcript_path = snapshot.get("transcript_path")

    # Derive project root from validated transcript_path
    project_root = None
    if isinstance(transcript_path, str) and transcript_path:
        transcript_file = Path(transcript_path).resolve()
        # Find project root by locating .claude directory
        current = transcript_file
        for _ in range(5):  # Check up to 5 levels up
            if (current / ".claude").exists():
                project_root = current
                break
            parent = current.parent
            if parent == current:  # Reached filesystem root
                break
            current = parent

    for item in payload.get("evidence_index", []):
        if not isinstance(item, dict):
            continue
        if item.get("type") not in {"transcript", "file"}:
            continue
        recorded_hash = item.get("content_hash")
        if not isinstance(recorded_hash, str) or not recorded_hash:
            continue
        path = item.get("path")
        if not isinstance(path, str) or not path:
            continue

        # CRIT-004 FIX: TOCTOU vulnerability - validate path AFTER hash computation
        # Resolve path first, then compute hash, THEN validate again
        # This prevents an attacker from replacing the file with a symlink between validation and hash computation
        evidence_file = Path(path).resolve()
        label = item.get("label") if isinstance(item.get("label"), str) else path
        current_hash = compute_file_content_hash(str(evidence_file))

        # Validate resolved path is still within project root AFTER hash computation
        if project_root is not None:
            try:
                evidence_file.relative_to(project_root)
            except ValueError:
                # Path traversal detected - return safe error message
                return "snapshot evidence path outside project directory"
        if current_hash is None:
            return f"snapshot evidence missing: {label}"
        if current_hash != recorded_hash:
            return f"snapshot evidence changed: {label}"
    return None


# Intent prefix mapping for goal display in restore message
intent_prefixes = {
    "question": "User asked:",
    "instruction": "User requested:",
    "correction": "User corrected:",
    "meta": "User noted:",
    "unsupported_language": "[NON-ENGLISH MESSAGE BLOCKED]:",
}


def build_restore_message(payload: dict[str, Any]) -> str:
    """Format the V2 automatic restore prompt."""
    snapshot = payload["resume_snapshot"]
    decisions_by_id = {
        decision["id"]: decision for decision in payload["decision_register"]
    }

    # Get intent prefix from message_intent field
    # TEST-001: Backward compatibility - old handoffs may not have message_intent
    message_intent = snapshot.get("message_intent", "instruction")
    intent_prefix = intent_prefixes.get(message_intent, "User requested:")

    lines = [
        "SESSION HANDOFF V2",
        "",
        f"Goal: {intent_prefix} {snapshot['goal']}",
        f"Current Task: {snapshot['current_task']}",
        f"Progress: {snapshot['progress_percent']}% ({snapshot['progress_state']})",
    ]

    if snapshot["blockers"]:
        lines.append("Blockers:")
        for blocker in snapshot["blockers"][:3]:
            summary = blocker.get("summary", "Unspecified blocker")
            btype = blocker.get("type", "blocker")
            lines.append(f"- {btype}: {summary}")

    if snapshot["active_files"]:
        lines.append("Active Files:")
        for path in snapshot["active_files"][:5]:
            lines.append(f"- {path}")

    if snapshot["pending_operations"]:
        lines.append("Pending Operations:")
        for operation in snapshot["pending_operations"][:3]:
            op_type = operation.get("type", "operation")
            target = operation.get("target", "unknown")
            state = operation.get("state", "in_progress")
            lines.append(f"- {op_type}: {target} ({state})")

    lines.extend(
        [
            f"Next Step: {snapshot['next_step']}",
            f"Transcript: {snapshot['transcript_path']}",
        ]
    )

    if snapshot["decision_refs"]:
        lines.append("Active Decisions:")
        for ref in snapshot["decision_refs"][:5]:
            decision = decisions_by_id.get(ref)
            if not decision:
                continue
            lines.append(f"- [{decision['kind']}] {decision['summary']}")

    # CONTEXT-001: Inject recent user context from transcript
    # This preserves user clarifications and refinements across compactions
    transcript_path = snapshot.get("transcript_path")
    if transcript_path:
        user_context = _extract_and_format_user_context(
            transcript_path, max_messages=15
        )
        if user_context:
            lines.extend(["", user_context])

    return "\n".join(lines)


def build_restore_message_compact(payload: dict[str, Any]) -> str:
    """Format the V2 restore message as a compact machine-oriented continuation block.

    This produces a structured <compact-restore> block that provides all necessary
    state for task continuation without verbose prose or retrospective sections.
    """
    snapshot = payload["resume_snapshot"]

    # Intent prefix mapping
    message_intent = snapshot.get("message_intent", "instruction")
    intent_prefix_map = {
        "question": "User asked:",
        "instruction": "User requested:",
        "directive": "User requested:",
        "correction": "User corrected:",
        "meta": "User noted:",
        "unsupported_language": "[NON-ENGLISH MESSAGE BLOCKED]:",
    }
    intent_prefix = intent_prefix_map.get(message_intent, "User requested:")

    # Format blockers requiring user input
    user_blockers = [
        b.get("summary", "Unspecified")
        for b in snapshot.get("blockers", [])
        if b.get("type") == "awaiting_approval"
    ]
    blockers_str = "; ".join(user_blockers) if user_blockers else "none"

    # Format active files
    active_files = snapshot.get("active_files", [])
    active_files_str = "\n".join(f"- {f}" for f in active_files) if active_files else "none"

    # Format pending operations
    pending_ops = snapshot.get("pending_operations", [])
    pending_str = ""
    if pending_ops:
        pending_lines = []
        for op in pending_ops[:5]:
            op_type = op.get("type", "operation")
            target = op.get("target", "unknown")
            pending_lines.append(f"- {op_type}: {target}")
        pending_str = "\n" + "\n".join(pending_lines)

    lines = [
        "<compact-restore>",
        f"status: restored",
        f"goal: {intent_prefix} {snapshot['goal']}",
        f"current_task: {snapshot['current_task']}",
        f"progress_state: {snapshot['progress_state']}",
        f"progress_percent: {snapshot['progress_percent']}",
        f"next_step: {snapshot['next_step']}",
        f"blockers_requiring_user: {blockers_str}",
        f"active_files:",
        active_files_str,
        f"pending_operations: {len(pending_ops)} pending",
        pending_str,
        "continuation_rule: Continue the current task. Do not ask the user to restate context. Ask only if blocked by missing user input.",
        "</compact-restore>",
    ]

    return "\n".join(lines)


def build_restore_message_dynamic(payload: dict[str, Any]) -> str:
    """Format the V2 restore message using dynamic sections.

    DEPRECATED: This produces Pre-Mortem format which is wrong for restore.
    Use build_restore_message_compact() for continuation blocks instead.
    """
    # For now, delegate to compact format to avoid breaking existing callers
    return build_restore_message_compact(payload)


def build_stale_hint(payload: dict[str, Any], reason: str) -> str:
    """Format the stale or rejected snapshot notice."""
    snapshot = payload["resume_snapshot"]
    return "\n".join(
        [
            "HANDOFF NOT RESTORED",
            "",
            "No safe current handoff was restored for this session.",
            f"Reason: {reason}",
            f"Snapshot Created: {snapshot['created_at']}",
            f"Source Session: {snapshot['source_session_id']}",
            "A stale handoff exists and may be inspected manually if needed.",
        ]
    )


def build_no_snapshot_hint(reason: str) -> str:
    """Format the missing handoff notice."""
    return "\n".join(
        [
            "HANDOFF NOT RESTORED",
            "",
            "No safe current handoff is available for this session.",
            f"Reason: {reason}",
        ]
    )


def short_task_name(goal: str) -> str:
    """Derive a concise current task label from the goal."""
    cleaned = " ".join(goal.split()).strip()
    if not cleaned:
        return "Unknown task"
    return cleaned


def ensure_progress_state(
    blockers: list[dict[str, Any]], pending_operations: list[dict[str, Any]]
) -> str:
    """Infer a coarse progress state."""
    if blockers:
        return "blocked"
    if pending_operations:
        return "in_progress"
    return "ready"


def _extract_and_format_user_context(
    transcript_path: str, max_messages: int = 15
) -> str | None:
    """Extract and format recent user messages from transcript for context injection.

    This function is called at RESTORE time (SessionStart or UserPromptSubmit)
    to inject recent user context into the restoration message. It reads the
    transcript, extracts user messages, and formats them concisely.

    Args:
        transcript_path: Path to the transcript JSONL file
        max_messages: Maximum number of user messages to extract (default: 15)

    Returns:
        Formatted string with recent user context, or None if extraction fails.
        Returns empty string if no user messages found.

    Edge cases handled:
    - Transcript file missing: Returns None, logs warning
    - Corrupted transcript entries: Skipped, continues with remaining entries
    - Very long messages: Truncated at 2000 chars with pointer to transcript
    - Session boundaries: Respected (stops at session_chain_id change)
    - Empty/short transcripts: Returns empty string (not None)
    """
    from scripts.hooks.__lib.transcript import gather_context_with_boundaries

    try:
        entries = gather_context_with_boundaries(
            transcript_path, max_messages=max_messages
        )
    except Exception as exc:
        # Log but don't fail - context injection is optional
        import logging

        logging.getLogger(__name__).warning(
            "[handoff_v2] Failed to gather context from transcript: %s", exc
        )
        return None

    if not entries:
        return ""

    # Extract user messages only, in chronological order (entries are reversed)
    user_messages = []
    for entry in reversed(entries):
        if entry.get("type") != "user":
            continue

        # Extract message text from various entry formats
        message_text = ""
        if "message" in entry:
            message = entry["message"]
            if isinstance(message, str):
                message_text = message
            elif isinstance(message, dict):
                content = message.get("content", [])
                if isinstance(content, str):
                    message_text = content
                elif isinstance(content, list):
                    # Concatenate text content from list
                    text_parts = []
                    for item in content:
                        if isinstance(item, str):
                            text_parts.append(item)
                        elif isinstance(item, dict):
                            text_parts.append(item.get("text", ""))
                    message_text = " ".join(text_parts)

        message_text = message_text.strip()
        if not message_text:
            continue

        # Truncate very long messages (code blocks, large pastes)
        # Full context available in transcript if needed
        if len(message_text) > 2000:
            message_text = (
                message_text[:2000] + "... [truncated, see transcript for full]"
            )

        user_messages.append(message_text)

    if not user_messages:
        return ""

    # Format: show last 5 in full, summarize earlier ones
    lines = []
    if len(user_messages) > 5:
        lines.append(f"Recent Context ({len(user_messages)} user messages):")
        lines.append(f"... {len(user_messages) - 5} earlier messages omitted")
        for msg in user_messages[-5:]:
            lines.append(f"- {msg[:200]}{'...' if len(msg) > 200 else ''}")
    else:
        lines.append(f"Recent Context ({len(user_messages)} user messages):")
        for msg in user_messages:
            lines.append(f"- {msg[:200]}{'...' if len(msg) > 200 else ''}")

    return "\n".join(lines)

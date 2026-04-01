#!/usr/bin/env python3
"""PreCompact capture hook for Handoff V2."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Configure logging to ensure diagnostic output is captured
# Logs will be written to .claude/logs/handoff_capture.log
_log_file_path = (
    Path(__file__).resolve().parents[2] / ".claude" / "logs" / "handoff_capture.log"
)
_log_file_path.parent.mkdir(parents=True, exist_ok=True)
_handler = logging.FileHandler(_log_file_path, encoding="utf-8")
_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(_handler)
logger.setLevel(logging.DEBUG)


def _find_project_root(start: Path) -> Path:
    """Walk up from start to find the project root (directory containing .claude)."""
    return detect_project_root(current_dir=start, strict=False)


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

# Import V1 features for integration
from scripts.config import cleanup_old_handoffs
from scripts.hooks.__lib.handoff_files import HandoffFileStorage
from scripts.hooks.__lib.handoff_v2 import (
    HandoffValidationError,
    build_envelope,
    build_resume_snapshot,
    compute_file_content_hash,
    ensure_progress_state,
    make_decision_id,
    make_evidence_id,
    short_task_name,
)
from scripts.hooks.__lib.dynamic_sections import calculate_quality_score_dynamic
from scripts.hooks.__lib.hook_input_validation import (
    HookInputError,
    validate_hook_input,
)
from scripts.hooks.__lib.terminal_detection import resolve_terminal_key
from scripts.hooks.__lib.transcript import (  # type: ignore
    TranscriptParser,
    extract_last_substantive_user_message,
)
from scripts.hooks.__lib.transcript import (  # noqa: F401
    is_meta_discussion,
    is_clarification_message,
    extract_preceding_message,
)

SESSION_PATTERNS = {
    "planning": [
        r"/plan-workflow",
        r"/arch",
        r"\bplan\b",
        r"\barchitecture\b",
        r"\bdesign\b",
    ],
    "debug": [r"\bfix\b", r"\bbug\b", r"\berror\b", r"\bfail", r"\bcrash\b"],
    "feature": [r"\bimplement\b", r"\bbuild\b", r"\bcreate\b", r"\badd\b"],
    "test": [r"\btest\b", r"\bverify\b", r"\bcoverage\b"],
    "docs": [r"\bdocument\b", r"\breadme\b", r"\bexplain\b"],
}
SESSION_EMOJIS = {
    "planning": "📋",
    "debug": "🐛",
    "feature": "✨",
    "test": "🧪",
    "docs": "📝",
    "general": "📍",
}
DECISION_PATTERNS = [
    (
        re.compile(r"\bmust\b|\bdo not\b|\bdon't\b|\bnever\b", re.IGNORECASE),
        "constraint",
    ),
    (
        re.compile(
            r"\bdecided to\b|\bdecision:\b|\bgoing with\b|\bchose\b", re.IGNORECASE
        ),
        "settled_decision",
    ),
    (
        re.compile(r"\bwaiting for approval\b|\bawaiting approval\b", re.IGNORECASE),
        "blocker_rule",
    ),
    (re.compile(r"\bavoid\b|\bshould not\b", re.IGNORECASE), "anti_goal"),
]


def detect_session_type(user_message: str, active_files: list[str]) -> tuple[str, str]:
    """Infer a coarse session type from the active request."""
    haystack = " ".join([user_message, *active_files]).lower()
    best_match = "general"
    best_score = 0
    for session_type, patterns in SESSION_PATTERNS.items():
        score = sum(
            1 for pattern in patterns if re.search(pattern, haystack, re.IGNORECASE)
        )
        if score > best_score:
            best_match = session_type
            best_score = score
    return best_match, SESSION_EMOJIS.get(best_match, "📍")


# CREATE vs IMPLEMENT task mode patterns
# Distinguishes creating new artifacts from implementing/fixing existing ones
CREATE_PATTERNS = [
    re.compile(r"^\s*(?:create|write|add|new)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:create|write|add)\s+(?:an?\s+)?(?:new\s+)?(?:adr|artifact|document|file|module|component)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:create|make|build)\s+(?:an?\s+)?(?:new\s+)?(?:skill|hook|agent|system)\b",
        re.IGNORECASE,
    ),
]
IMPLEMENT_PATTERNS = [
    re.compile(r"^\s*(?:implement|fix|repair|resolve)\b", re.IGNORECASE),
    re.compile(r"\b(?:implement|fix|repair|resolve|debug)\s+", re.IGNORECASE),
    re.compile(
        r"\b(?:refactor|update|modify|change|improve|enhance|optimize)\s+(?:the\s+)?",
        re.IGNORECASE,
    ),
]


def detect_task_mode(user_message: str, active_files: list[str]) -> str:
    """Detect whether task is CREATE (new artifact) or IMPLEMENT (existing work).

    Distinguishes between:
    - CREATE: Making new artifacts (ADR, documentation, new features, skills, hooks)
    - IMPLEMENT: Fixing, refactoring, improving existing code/features
    - none: Cannot determine or not applicable

    Args:
        user_message: The user's goal message
        active_files: List of active file paths

    Returns:
        "create", "implement", or "none"
    """
    haystack = " ".join([user_message, *active_files]).lower()
    c_score = sum(1 for p in CREATE_PATTERNS if p.search(haystack))
    i_score = sum(1 for p in IMPLEMENT_PATTERNS if p.search(haystack))
    if c_score > i_score:
        return "create"
    elif i_score > c_score:
        return "implement"
    return "none"


def detect_lifecycle_phase(
    blockers: list[dict[str, Any]],
    active_files: list[str],
    pending_operations: list[dict[str, Any]],
    goal: str,
    task_mode: str = "none",
) -> str:
    """Detect conversation lifecycle phase from already-extracted data.

    Returns one of: "discussing", "planning", "implementing".
    Default is "implementing" (preserves current behavior).

    Note: "approved" and "reviewing" are declared in VALID_LIFECYCLE_PHASES
    but are not produced by this function. They are reserved for future
    JSONL-based detection (Phase 2) or UserPromptSubmit hook detection.
    """
    if not goal or not goal.strip():
        # Edge case: empty goal with no other signals → discussing
        return "discussing"

    # If awaiting_approval blocker exists, session is in planning
    if any(b.get("type") == "awaiting_approval" for b in blockers):
        return "planning"

    has_pending = bool(pending_operations)

    # If pending operations exist with no blockers, implementing
    if has_pending:
        return "implementing"

    # No pending ops — check if goal ends with question mark
    if goal.strip().endswith("?"):
        return "discussing"

    # Use task_mode as override signal:
    # If task_mode indicates active implementation work, trust it over
    # the absence of pending_operations (handles early-compact scenario)
    if task_mode in ("implement", "create") and any(active_files):
        return "implementing"

    # No edits, no pending ops, no clear implementation signal → discussing
    return "discussing"


def detect_planning_session(
    user_message: str, active_files: list[str]
) -> dict[str, Any] | None:
    """Return an explicit planning blocker if the session is in approval state."""
    del active_files
    lowered = user_message.lower()
    if any(token in lowered for token in ["/plan-workflow", "/arch"]) or (
        "plan" in lowered and "implement" not in lowered
    ):
        return {
            "type": "awaiting_approval",
            "summary": "Plan exists but requires user approval before implementation.",
        }
    return None


def _read_hook_input() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        raise ValueError("PreCompact hook received empty stdin")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("PreCompact hook input must be a JSON object")
    return payload


def _extract_active_files(parser: TranscriptParser) -> list[str]:
    files: list[str] = []
    try:
        # First, extract from Edit operations (modifications)
        for modification in parser.extract_modifications(limit=20):
            path = modification.get("file")
            if isinstance(path, str) and path not in files:
                files.append(path)

        # Second, scan all tool_use entries for file-related operations
        # This captures Read, Edit, Write, and other file tools even if no Edit completed
        for entry in parser._get_parsed_entries():
            # Extract tool_use content blocks from message.content array
            # Transcript structure: entry.message.content is a list of content blocks
            msg_obj = entry.get("message", {})
            if not isinstance(msg_obj, dict):
                continue

            content = msg_obj.get("content", [])
            if not isinstance(content, list):
                continue

            # Find tool_use blocks in content array
            for content_block in content:
                if not isinstance(content_block, dict):
                    continue
                if content_block.get("type") != "tool_use":
                    continue

                tool_name = content_block.get("name", "")
                tool_input = content_block.get("input", {})
                if not isinstance(tool_input, dict):
                    continue

                # Extract file path from specific tools based on their input schema
                file_path = None
                if tool_name == "Read":
                    file_path = tool_input.get("file_path")
                elif tool_name == "Edit":
                    file_path = tool_input.get("file_path")
                elif tool_name == "Write":
                    file_path = tool_input.get("file_path")
                elif tool_name in ("Grep", "Glob"):
                    # For search tools, capture the pattern but don't count as file
                    continue
                elif tool_name == "Bash":
                    # Skip bash commands (not file paths)
                    continue
                else:
                    # Fallback: check common file path keys
                    for key in ("file_path", "path", "target"):
                        value = tool_input.get(key)
                        if (
                            isinstance(value, str)
                            and ("/" in value or "\\" in value)
                            and not value.startswith(("http:", "https:", "git:"))
                        ):
                            file_path = value
                            break

                # Validate and add file path
                if isinstance(file_path, str) and file_path not in files:
                    # Exclude non-file paths (URLs, pure flags, etc.)
                    # Accept any path with separators that looks like a file
                    if (
                        any(sep in file_path for sep in ("/", "\\"))
                        and not file_path.startswith(
                            ("http:", "https:", "git:", "ftp:")
                        )
                        and len(file_path) > 3  # Minimum reasonable path length
                    ):
                        files.append(file_path)

        return files[:10]
    except Exception as exc:
        logger.warning("[PreCompact V2] Failed to extract active files: %s", exc)
        return files[:10]


def _normalize_pending_operations(parser: TranscriptParser) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    try:
        for operation in parser.extract_pending_operations()[:5]:
            normalized.append(
                {
                    "type": operation.get("type", "command"),
                    "target": operation.get("target", "unknown"),
                    "state": operation.get("state", "in_progress"),
                }
            )
    except Exception as exc:
        logger.warning("[PreCompact V2] Failed to extract pending operations: %s", exc)
    return normalized


def _extract_last_assistant_text(parser: TranscriptParser) -> str:
    try:
        for entry in reversed(parser._get_parsed_entries()):
            if entry.get("type") == "assistant":
                text = parser._extract_text_from_entry(entry).strip()
                if text:
                    return text
    except Exception as exc:
        logger.warning("[PreCompact V2] Failed to read last assistant message: %s", exc)
    return ""


def _infer_next_step(
    last_assistant_text: str, pending_operations: list[dict[str, Any]], goal: str
) -> str:
    if pending_operations:
        operation = pending_operations[0]
        return f"Resume {operation.get('type', 'work')} on {operation.get('target', 'unknown')}."

    for line in last_assistant_text.splitlines():
        candidate = line.strip().lstrip("-*• ").strip()
        if len(candidate) >= 12 and not candidate.lower().startswith(
            ("here", "summary", "analysis")
        ):
            return candidate[:220]

    if goal:
        return f"Continue working on: {goal[:180]}"
    return "Ask the user for the next concrete step."


def _is_decision_noise(text: str) -> bool:
    """Check if text is noise that should not be captured as a decision.

    Filters out:
    - Skill definition headers ("Base directory for this skill:", "##", etc.)
    - User feedback/corrections ("You don't quite seem to be thinking...")
    - Code fragments and partial lines
    - Table/formatted content that's not a decision
    """
    if not text or not isinstance(text, str):
        return True

    text_lower = text.strip().lower()
    text_stripped = text.strip()

    # Skip skill definition headers
    skill_noise_patterns = [
        "base directory for this skill",
        "skill description:",
        "usage:",
        "examples:",
        "##",
        "###",
        "---",
        "===",
    ]
    for pattern in skill_noise_patterns:
        if pattern in text_lower:
            return True

    # Skip user feedback/corrections (second-person criticism)
    feedback_patterns = [
        "you don't ",
        "you didn't ",
        "you seem ",
        "you aren't ",
        "you're not ",
    ]
    for pattern in feedback_patterns:
        if pattern in text_lower:
            return True

    # Skip lines that start with markdown list markers (likely fragments)
    if re.match(r"^[\s]*(\-|\*|\+|\d+\.)[\s]+", text_stripped):
        # Allow if it's a complete sentence (has period at end)
        if not text_stripped.endswith("."):
            return True

    # Skip lines that are mostly punctuation/symbols (formatted content)
    symbol_ratio = sum(1 for c in text_stripped if c in "|[]{}<>+-=/\\_*#") / max(
        len(text_stripped), 1
    )
    if symbol_ratio > 0.3:
        return True

    # Skip very short fragments (less than 15 chars after stripping)
    if len(text_stripped) < 15:
        return True

    return False


def _build_decisions(
    parser: TranscriptParser, transcript_evidence_id: str
) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    seen: set[str] = set()
    try:
        # Only scan recent entries to avoid picking up old conversations
        # from previous sessions in compacted transcripts
        all_entries = parser._get_parsed_entries()
        recent_entries = all_entries[-200:] if len(all_entries) > 200 else all_entries

        for entry in recent_entries:
            if entry.get("type") not in {"assistant", "user"}:
                continue
            text = parser._extract_text_from_entry(entry).strip()
            if len(text) < 20:
                continue

            # Skip noise before pattern matching
            if _is_decision_noise(text):
                logger.debug(
                    "[PreCompact V2] Skipping decision noise: %s...", text[:50]
                )
                continue

            # Skip meta-discussion (conversational fragments about the system itself)
            if is_meta_discussion(text):
                logger.debug(
                    "[PreCompact V2] Skipping meta-discussion: %s...", text[:50]
                )
                continue

            for pattern, decision_kind in DECISION_PATTERNS:
                if not pattern.search(text):
                    continue
                summary = " ".join(text.split())
                if summary in seen:
                    break
                seen.add(summary)

                decisions.append(
                    {
                        "id": make_decision_id(),
                        "kind": decision_kind,
                        "summary": summary,
                        "details": summary,
                        "priority": "high"
                        if decision_kind in {"constraint", "blocker_rule"}
                        else "medium",
                        "applies_when": "Continue the current task after compact.",
                        "source_refs": [transcript_evidence_id],
                    }
                )
                break
            if len(decisions) >= 5:
                break
    except Exception as exc:
        logger.warning("[PreCompact V2] Failed to extract decisions: %s", exc)
    return decisions


def _resolve_evidence_path(path: str, project_root: Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    return candidate.resolve()


def _build_evidence_index(
    project_root: Path, transcript_path: str, active_files: list[str]
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    transcript_id = make_evidence_id()
    resolved_transcript_path = _resolve_evidence_path(transcript_path, project_root)
    evidence.append(
        {
            "id": transcript_id,
            "type": "transcript",
            "label": "Current compact transcript",
            "path": str(resolved_transcript_path),
            "content_hash": compute_file_content_hash(resolved_transcript_path),
        }
    )
    for path in active_files[:5]:
        resolved_path = _resolve_evidence_path(path, project_root)
        evidence_item: dict[str, Any] = {
            "id": make_evidence_id(),
            "type": "file",
            "label": Path(path).name or path,
            "path": str(resolved_path),
        }
        content_hash = compute_file_content_hash(resolved_path)
        if content_hash:
            evidence_item["content_hash"] = content_hash
        evidence.append(evidence_item)
    return evidence


def _estimate_progress(
    blockers: list[dict[str, Any]], pending_operations: list[dict[str, Any]], goal: str
) -> int:
    if blockers and any(
        blocker.get("type") == "awaiting_approval" for blocker in blockers
    ):
        return 100
    if pending_operations:
        return 65
    if goal:
        return 35
    return 0


def main() -> None:
    """Capture the current session into a V2 handoff envelope."""
    try:
        input_data = _read_hook_input()
        validate_hook_input(input_data, hook_type="PreCompact")
        transcript_path = input_data.get("transcript_path")
        if not transcript_path:
            raise ValueError("PreCompact hook requires transcript_path")

        terminal_id = resolve_terminal_key(input_data.get("terminal_id"))

        # CRITICAL: For handoff package, detect project root with testing support
        # Priority: 1) HANDOFF_PROJECT_ROOT env var (for testing), 2) walk up from cwd to .claude
        # Use walk-up from cwd instead of raw Path.cwd() because Claude Code may invoke
        # PreCompact from a skill subdirectory (e.g. P:/.claude/skills/s/) where cwd would
        # be that subdirectory. The walk-up finds the actual project root containing .claude.
        env_project_root = os.environ.get("HANDOFF_PROJECT_ROOT")
        if env_project_root:
            project_root = Path(env_project_root)
            logger.info(
                f"[PreCompact V2] Using project root from environment: {project_root}"
            )
        else:
            project_root = _find_project_root(Path.cwd())
            logger.info(
                f"[PreCompact V2] Using project root from walk-up: {project_root}"
            )

        # CRITICAL: Validate transcript_path exists and is readable
        transcript_file = Path(transcript_path)
        if not transcript_file.exists():
            raise HandoffValidationError(
                f"Transcript file does not exist: {transcript_path}"
            )
        if not transcript_file.is_file():
            raise HandoffValidationError(
                f"Transcript path is not a file: {transcript_path}"
            )
        # LOGIC-003: Fixed inverted condition - warn when test transcripts are detected
        # QUAL-005: Changed to ERROR level for test transcript warnings
        if "test" in transcript_file.name.lower():
            logger.error(
                "[PreCompact V2] Test transcript detected: %s - this may indicate wrong transcript_path",
                transcript_file.name,
            )

        # Cleanup old handoffs before creating new one
        try:
            cleanup_old_handoffs(project_root)
        except Exception as exc:
            logger.warning("[PreCompact V2] Cleanup old handoffs failed: %s", exc)

        parser = TranscriptParser(transcript_path)

        # Extract goal with observability data
        goal_result = extract_last_substantive_user_message(transcript_path)
        goal = goal_result.get("goal", "Unknown task")
        message_intent = goal_result.get("message_intent", "instruction")

        # Log observability data for monitoring
        logger.info(
            "[PreCompact V2] Goal extraction observability: "
            f"messages_scanned={goal_result.get('messages_scanned', 0)}, "
            f"corrections_skipped={goal_result.get('corrections_skipped', 0)}, "
            f"meta_skipped={goal_result.get('meta_skipped', 0)}, "
            f"session_boundary={goal_result.get('session_boundary_hit', False)}, "
            f"topic_shift={goal_result.get('topic_shift_hit', False)}, "
            f"scan_pattern={goal_result.get('scan_pattern', 'unknown')}, "
            f"intent={message_intent}"
        )

        # Handle fallback for unknown or meta-discussion goals
        if not goal or goal == "Unknown task" or is_meta_discussion(goal):
            fallback_goal = parser.extract_last_user_message()
            # Also check fallback_goal for meta-discussion
            if fallback_goal and is_meta_discussion(fallback_goal):
                # If both goal and fallback are meta-discussion, use context
                goal = "Continue current task (meta-discussion filtered)"
            else:
                goal = fallback_goal or "Unknown task"
                # For fallback goals, use default intent since we don't have classified intent
                message_intent = "instruction"

        # Check if the last substantive action was a skill invocation
        # If so, capture skill output instead of skill definition
        skill_output = parser.extract_last_skill_output(max_length=800)
        skill_name_for_decision = None
        if skill_output:
            skill_name_for_decision = skill_output.get("skill_name", "unknown")
            # If goal looks like skill definition, replace with skill invocation context
            if goal.lower().startswith("base directory for this skill:"):
                goal = f"Skill /{skill_name_for_decision} invoked - analyzing results"

        active_files = _extract_active_files(parser)
        pending_operations = _normalize_pending_operations(parser)
        current_task = short_task_name(goal)
        planning_blocker = detect_planning_session(goal, active_files)
        blockers = [planning_blocker] if planning_blocker else []
        progress_percent = _estimate_progress(blockers, pending_operations, goal)
        progress_state = ensure_progress_state(blockers, pending_operations)
        last_assistant_text = _extract_last_assistant_text(parser)
        next_step = _infer_next_step(last_assistant_text, pending_operations, goal)

        # Detect task mode (CREATE vs IMPLEMENT) for handoff envelope
        task_mode = detect_task_mode(goal, active_files)
        logger.debug("[PreCompact V2] Task mode detected: %s", task_mode)

        # Detect lifecycle phase (discussing/planning/implementing)
        # Prefer accumulated JSONL state over inference when available
        accumulated_lifecycle_phase = None
        try:
            storage_for_accum = HandoffFileStorage(project_root, terminal_id)
            accumulated_events = storage_for_accum.read_accumulated_state()
            # Find the last phase_transition event
            for event in reversed(accumulated_events):
                if event.get("type") == "phase_transition":
                    accumulated_lifecycle_phase = event.get("to")
                    break
        except Exception as exc:
            logger.debug("[PreCompact V2] Accumulated state read failed: %s", exc)

        if accumulated_lifecycle_phase:
            lifecycle_phase = accumulated_lifecycle_phase
            logger.info(
                "[PreCompact V2] Using accumulated lifecycle phase: %s",
                lifecycle_phase,
            )
        else:
            lifecycle_phase = detect_lifecycle_phase(
                blockers,
                active_files,
                pending_operations,
                goal,
                task_mode,
            )
            logger.debug(
                "[PreCompact V2] Lifecycle phase detected (inferred): %s",
                lifecycle_phase,
            )

        # Extract preceding context if goal is a clarification message
        preceding_task_context = ""
        if is_clarification_message(goal):
            preceding_msg = extract_preceding_message(transcript_path, goal)
            if preceding_msg:
                preceding_task_context = preceding_msg
                logger.info(
                    "[PreCompact V2] Goal is clarification - captured preceding context: %s...",
                    preceding_msg[:80],
                )

        evidence_index = _build_evidence_index(
            project_root, transcript_path, active_files
        )
        transcript_evidence_id = evidence_index[0]["id"]
        decision_register = _build_decisions(parser, transcript_evidence_id)

        # Add skill invocation to decision register if one was detected
        if skill_output and skill_name_for_decision:
            skill_decision = {
                "id": make_decision_id(),
                "kind": "skill_invocation",
                "summary": f"User ran /{skill_name_for_decision} skill",
                "details": f"Skill output: {skill_output.get('output', '')[:300]}",
                "priority": "high",
                "applies_when": "Continue the current task after compact.",
                "source_refs": [transcript_evidence_id],
            }
            decision_register.insert(0, skill_decision)

        # Calculate quality score for the handoff using dynamic sections
        quality_score = None
        try:
            # Map existing handoff data to dynamic sections schema
            dynamic_session_data = {
                "goal": goal,
                "active_files": active_files,
                "decision_register": decision_register,
                "known_issues": blockers,  # Map blockers to known_issues
                "final_actions": pending_operations,  # Map pending to actions
                "has_errors": any(
                    b.get("type") == "awaiting_approval" for b in blockers
                ),
            }
            quality_score = calculate_quality_score_dynamic(dynamic_session_data)
            logger.debug("[PreCompact V2] Quality score (dynamic): %.2f", quality_score)
        except Exception as exc:
            logger.warning(
                "[PreCompact V2] Dynamic quality score calculation failed: %s", exc
            )

        # Read task state from task tracker for handoff
        tasks_snapshot: list[dict[str, Any]] = []
        try:
            task_tracker_dir = project_root / ".claude" / "state" / "task_tracker"
            task_file_path = task_tracker_dir / f"{terminal_id}_tasks.json"
            if task_file_path.exists():
                with open(task_file_path, encoding="utf-8") as f:
                    task_data = json.load(f)
                # Extract tasks list from the task tracker file
                tasks_snapshot = task_data.get("tasks", {}).get("task_list", [])
                logger.debug(
                    "[PreCompact V2] Loaded %d tasks from task tracker",
                    len(tasks_snapshot),
                )
        except Exception as exc:
            logger.warning("[PreCompact V2] Failed to read task state: %s", exc)

        resume_snapshot = build_resume_snapshot(
            terminal_id=terminal_id,
            source_session_id=input_data.get("session_id", ""),
            goal=goal,
            current_task=current_task,
            progress_percent=progress_percent,
            progress_state=progress_state,
            blockers=blockers,
            active_files=active_files,
            pending_operations=pending_operations,
            next_step=next_step,
            decision_refs=[decision["id"] for decision in decision_register],
            evidence_refs=[item["id"] for item in evidence_index],
            transcript_path=transcript_path,
            message_intent=message_intent,
            quality_score=quality_score,
            tasks_snapshot=tasks_snapshot,
        )
        envelope = build_envelope(
            resume_snapshot=resume_snapshot,
            decision_register=decision_register,
            evidence_index=evidence_index,
        )

        storage = HandoffFileStorage(project_root, terminal_id)

        # Diagnostic logging before save
        logger.info(
            "[PreCompact V2] Attempting to save handoff: terminal=%s, handoff_file=%s",
            terminal_id,
            storage.handoff_file,
        )
        logger.debug(
            "[PreCompact V2] Envelope keys: %s",
            list(envelope.keys()),
        )
        logger.debug(
            "[PreCompact V2] Snapshot keys: %s",
            list(envelope.get("resume_snapshot", {}).keys()),
        )

        if not storage.save_handoff(envelope):
            logger.error(
                "[PreCompact V2] save_handoff returned False: terminal=%s, file=%s",
                terminal_id,
                storage.handoff_file,
            )
            raise HandoffValidationError("failed to persist V2 handoff envelope")

        # Verify file was actually created
        if not storage.handoff_file.exists():
            logger.error(
                "[PreCompact V2] File does not exist after save: %s",
                storage.handoff_file,
            )
            raise HandoffValidationError(
                f"handoff file not created after save: {storage.handoff_file}"
            )

        logger.info(
            "[PreCompact V2] Handoff saved successfully: %s (%d bytes)",
            storage.handoff_file.name,
            storage.handoff_file.stat().st_size,
        )

        # Write compaction marker so UserPromptSubmit hook can detect intra-session compaction
        # and inject restoration context on the first prompt after compaction.
        try:
            marker_dir = project_root / ".claude" / "hooks" / "state"
            marker_dir.mkdir(parents=True, exist_ok=True)
            marker_path = marker_dir / f"compaction_marker_{terminal_id}.json"
            marker_payload = {
                "timestamp": time.time(),
                "handoff_path": str(storage.handoff_file),
            }
            with marker_path.open("w", encoding="utf-8") as fh:
                json.dump(marker_payload, fh)
            logger.debug("[PreCompact V2] Compaction marker written: %s", marker_path)
        except Exception as exc:
            # Marker write failure is non-fatal — handoff is already saved.
            # UserPromptSubmit will fall back to SessionStart restore.
            logger.warning("[PreCompact V2] Failed to write compaction marker: %s", exc)

        output = {
            "decision": "approve",
            "reason": f"Captured Handoff V2 for terminal {terminal_id}",
            "additionalContext": (
                f"Saved V2 handoff snapshot.\n"
                f"Goal: {goal}\n"
                f"Next Step: {next_step}\n"
                f"Active Files: {len(active_files)}\n"
                f"Pending Operations: {len(pending_operations)}"
            ),
        }
        print(json.dumps(output, indent=2))
        sys.exit(0)
    except HookInputError as exc:
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": f"Handoff V2 capture input validation failed: {exc}",
                    "additionalContext": f"🚫 Handoff V2 capture rejected invalid hook input: {exc}",
                },
                indent=2,
            )
        )
        sys.exit(1)
    except HandoffValidationError as exc:
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": f"Handoff V2 capture validation failed: {exc}",
                    "additionalContext": f"🚫 Handoff V2 envelope validation failed: {exc}",
                },
                indent=2,
            )
        )
        sys.exit(1)
    except Exception as exc:
        logger.error("[PreCompact V2] Capture failed: %s", exc, exc_info=True)
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": f"Handoff V2 capture failed: {exc}",
                    "additionalContext": f"🚫 Handoff V2 capture failed: {exc}",
                },
                indent=2,
            )
        )
        sys.exit(1)


if __name__ == "__main__":
    main()

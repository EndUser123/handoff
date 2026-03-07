#!/usr/bin/env python3
"""
SessionStart Hook - Handoff Restore Version

Restores handoff on session start when continue_session task exists.

Flow:
  1. Check for active_session/continue_session task with handoff metadata
  2. Validate handoff data (schema, checksum)
  3. Build restoration prompt with context
  4. Inject into conversation context

Renamed from checkpoint package to handoff package.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import re
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., int])

logger = logging.getLogger(__name__)

# Configure logging to output to stderr so diagnostic messages are visible
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Hook directory resolution
HOOKS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = HOOKS_DIR.parent

# Add handoff package to path
# Handoff package is in P:/packages/handoff/src/, not P:/.claude/src/
HANDOFF_PACKAGE = PROJECT_ROOT / "packages" / "handoff" / "src"
if str(HANDOFF_PACKAGE) not in sys.path:
    sys.path.insert(0, str(HANDOFF_PACKAGE))

from handoff.migrate import compute_metadata_checksum  # noqa: E402

# Add hooks dir for terminal detection (use existing comprehensive implementation)
# Path: {hooks_dir}/SessionStart_handoff_restore.py
# Need to reach: {project_root}/.claude/hooks/terminal_detection.py
claude_hooks_dir = PROJECT_ROOT / ".claude" / "hooks"
if str(claude_hooks_dir) not in sys.path:
    sys.path.insert(0, str(claude_hooks_dir))

try:
    from terminal_detection import detect_terminal_id
except ImportError:
    logger.debug("[SessionStart] terminal_detection module not available")

    def detect_terminal_id() -> str:
        return f"term_{os.getpid()}"


try:
    from __lib.hook_base import hook_main
except ImportError:
    logger.debug("[SessionStart] hook_base module not available, using no-op decorator")

    def hook_main(func: F) -> F:
        """No-op decorator if hook_base not available."""
        return func


def _validate_handoff_schema(handoff_data: dict[str, Any]) -> tuple[bool, str | None]:
    """Validate handoff data schema.

    Args:
        handoff_data: Handoff data dict to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    required_fields = ["task_name", "saved_at"]

    for field in required_fields:
        if field not in handoff_data:
            error_msg = f"Missing required field: {field}"
            logger.warning(f"[SessionStart] Schema validation failed: {error_msg}")
            return False, error_msg

    # Validate timestamp
    try:
        datetime.fromisoformat(handoff_data["saved_at"])
    except (ValueError, TypeError):
        error_msg = f"Invalid saved_at timestamp: {handoff_data.get('saved_at')}"
        logger.warning(f"[SessionStart] Schema validation failed: {error_msg}")
        return False, error_msg

    return True, None


def _verify_handoff_checksum(handoff_data: dict[str, Any]) -> tuple[bool, str | None]:
    """Verify handoff data checksum.

    Args:
        handoff_data: Handoff data dict with checksum field

    Returns:
        Tuple of (is_valid, error_message)
    """
    stored_checksum = handoff_data.get("checksum")
    if not stored_checksum:
        return True, None  # No checksum to verify

    # Remove checksum for recomputation
    data_for_hash = {k: v for k, v in handoff_data.items() if k != "checksum"}
    computed = compute_metadata_checksum(data_for_hash)

    if not hmac.compare_digest(stored_checksum, computed):
        return False, (
            f"Checksum mismatch: stored={stored_checksum[:16]}... computed={computed[:16]}..."
        )
    return True, None


def _migrate_handoff_hash(handoff_data: dict[str, Any]) -> None:
    """Migrate handoff data to include hash verification fields.

    Detects handoffs without original_user_request_hash and logs migration event.
    Existing handoffs continue to work with checksum verification only.

    Args:
        handoff_data: Handoff data dict (modified in place if migration needed)
    """
    original_request = handoff_data.get("original_user_request")
    request_hash = handoff_data.get("original_user_request_hash")

    # Migration: Detect missing hash field
    if original_request and not request_hash:
        logger.info(
            "[SessionStart] Legacy handoff detected (no hash field). "
            "Relying on full metadata checksum for integrity verification. "
            "Handoff will be upgraded on next compaction."
        )
        # Note: We don't add the hash here because:
        # 1. Computing hash requires hashlib import
        # 2. We don't want to modify handoff data during restore (read-only)
        # 3. Next compaction will automatically add the hash
        # 4. Full checksum verification provides integrity protection


def _build_last_command_section(handoff_data: dict[str, Any]) -> list[str]:
    """Build the last command section from original_user_request.

    Args:
        handoff_data: Validated handoff data

    Returns:
        List of formatted lines
    """
    original_request = handoff_data.get("original_user_request")
    request_hash = handoff_data.get("original_user_request_hash")
    request_timestamp = handoff_data.get("original_user_request_timestamp")
    last_command_section = []

    if original_request:
        # Build verification header if hash available
        verification_header = []
        if request_hash:
            verification_header = [
                f"**Verification Token:** `{request_hash}`",
            ]
            if request_timestamp:
                verification_header.append(
                    f"**Timestamp:** {request_timestamp}"
                )
            verification_header.extend([
                "",
                "**⚠️ VERIFY:** If this command seems wrong, the handoff data may be corrupted.",
                "",
                "",
            ])

        last_command_section = [
            "## ⚠️  THE USER'S LAST COMMAND (AUTHENTIC - READ THIS FIRST)",
            "",
            *verification_header,
            original_request,  # FULL content, no truncation
            "",
            "",
            "───",
            "**CRITICAL:** This IS the user's last command. Start from here.",
            "Do NOT guess, do NOT search memory, do NOT hallucinate.",
            "",
            "",
        ]

    return last_command_section


def _build_quick_reference_section(handoff_data: dict[str, Any]) -> list[str]:
    """Build the quick reference section with transcript path.

    Args:
        handoff_data: Validated handoff data

    Returns:
        List of formatted lines
    """
    lines = []
    transcript_path = handoff_data.get("transcript_path", "")

    if transcript_path:
        lines.extend(
            [
                "## 📌 QUICK REFERENCE - PREVIOUS CHAT HISTORY",
                "",
                f"**Path:** `{transcript_path}`",
                "",
                "**When user asks about previous chat/transcript:**",
                f"→ For more context on this task: read `{transcript_path}`",
                "→ To go further back: that file itself contains an earlier restoration",
                "  prompt referencing the session before it — follow the chain.",
                "→ DO NOT search for files, DO NOT look in checkpoints",
                "",
                "",
            ]
        )

    return lines


def _build_task_status_section(handoff_data: dict[str, Any]) -> list[str]:
    """Build the task status section with progress, blocker, and implementation status.

    Args:
        handoff_data: Validated handoff data

    Returns:
        List of formatted lines
    """
    lines = []

    # Task location and progress
    lines.extend(
        [
            "## 📍 WHERE WE ARE IN THE TASK",
            "",
            f"**Task:** {handoff_data.get('task_name', 'unknown')}",
            f"**Progress:** {handoff_data.get('progress_percent', 0)}%",
            "",
        ]
    )

    # Add active task context from state file if available
    active_task = handoff_data.get("active_task")
    if active_task and isinstance(active_task, dict):
        # Cache all lookups (efficiency: single dict access)
        task_name = active_task.get("task_name", "")
        last_message = active_task.get("last_user_message", "")
        active_files = active_task.get("active_files", [])
        next_steps = active_task.get("next_steps", "")
        task_progress = active_task.get("progress_pct", 0)
        session_type = active_task.get("session_type", "unknown")

        lines.extend(
            [
                "**What You Were Working On:**",
            ]
        )

        # Add session type with emoji if available
        session_type_emojis = {
            "debug": "🐛",
            "feature": "✨",
            "refactor": "🔧",
            "test": "🧪",
            "docs": "📝",
            "mixed": "🔀",
            "unknown": "❓",
        }
        session_emoji = session_type_emojis.get(session_type, "")
        if session_emoji:
            lines.append(f"  **Session Type:** {session_emoji} {session_type}")

        # Show invoked command if present (for planning sessions)
        invoked_command = active_task.get("invoked_command")
        if invoked_command and invoked_command != "unknown command":
            lines.append(f"  **Invoked Command:** {invoked_command}")

        if task_name:
            lines.append(f"  **Task:** {task_name}")

        if last_message:
            # Truncate long messages (cache len check)
            msg_display = last_message[:200] + "..." if len(last_message) > 200 else last_message
            lines.append(f"  **Last request:** {msg_display}")

        if active_files:
            # Show up to 5 active files
            files_to_show = active_files[:5]
            files_display = ", ".join(files_to_show)
            if len(active_files) > 5:
                files_display += f" (+{len(active_files) - 5} more)"
            lines.append(f"  **Files:** {files_display}")

        if next_steps:
            # Show first line of next_steps (split only once)
            first_line = next_steps.split("\n", 1)[0]
            steps_preview = first_line[:100] + "..." if len(first_line) > 100 else first_line
            lines.append(f"  **Next:** {steps_preview}")

        lines.extend(
            [
                f"  **Progress:** {task_progress}%",
                "",
                "**→ This is the context from your last session.**",
                "",
            ]
        )

    # Add blocker if present
    blocker = handoff_data.get("blocker")
    if blocker:
        # Check if this is an awaiting_approval blocker (planning session)
        blocker_type = None
        if isinstance(blocker, dict):
            blocker_type = blocker.get("type")
            blocker_desc = blocker.get("description", str(blocker))
            invoked_command = blocker.get("invoked_command", "")
        else:
            blocker_desc = str(blocker)

        # Show prominent warning for awaiting_approval blockers
        if blocker_type == "awaiting_approval":
            lines.extend(
                [
                    "",
                    "⚠️ **BLOCKER: Awaiting User Approval**",
                    "",
                    "Plan has been created but **NOT approved**.",
                    "DO NOT proceed with implementation until user reviews.",
                    "",
                ]
            )
            if invoked_command:
                lines.append(f"**Invoked Command:** {invoked_command}")
            lines.extend(
                [
                    "",
                    f"**Plan Status:** {blocker_desc}",
                    "",
                ]
            )
        else:
            # Regular blocker display
            lines.extend(
                [
                    f"**Current Blocker:** {blocker_desc}",
                    "",
                ]
            )

    # Add pending operations
    pending_operations = handoff_data.get("pending_operations", [])
    if pending_operations:
        lines.extend(
            [
                "⚠️ **Pending Operations:** (work in progress when compacted)",
            ]
        )
        for op in pending_operations[:5]:  # Limit to 5
            op_type = op.get("type", "unknown")
            op_target = op.get("target", "unknown")
            op_state = op.get("state", "unknown")
            lines.append(f"  - [{op_type.upper()}] {op_target} ({op_state})")
        lines.append("")

    # Add implementation status
    impl_status = handoff_data.get("implementation_status")
    if impl_status and isinstance(impl_status, dict):
        completion_state = impl_status.get("completion_state", "unknown")
        if completion_state != "unknown":
            state_emoji = {
                "verified": "✅",
                "implemented": "🔄",
                "in_progress": "🔄",
                "blocked": "🚫",
                "failed": "❌",
            }.get(completion_state, "❓")
            lines.extend(
                [
                    f"**Status at compaction:** {state_emoji} `{completion_state}`",
                    "",
                ]
            )

        test_results = impl_status.get("test_results")
        if test_results and isinstance(test_results, dict):
            passed = test_results.get("passed", 0)
            failed = test_results.get("failed", 0)
            if passed or failed:
                status_icon = "✅" if failed == 0 else "❌"
                lines.extend(
                    [
                        f"**Tests at compaction:** {status_icon} {passed} passed, {failed} failed",
                        "",
                    ]
                )

    # Add next steps
    next_steps = handoff_data.get("next_steps", "")
    if next_steps:
        lines.extend(
            [
                "**Next Steps:**",
                next_steps,
                "",
            ]
        )

    return lines


def _build_task_context_section(handoff_data: dict[str, Any]) -> list[str]:
    """Build the task context section with active files, git branch, and modifications.

    Args:
        handoff_data: Validated handoff data

    Returns:
        List of formatted lines
    """
    lines = ["## 📋 TASK CONTEXT", ""]

    # Add active files
    active_files = handoff_data.get("active_files", [])
    if active_files:
        lines.extend(
            [
                "**Active Files:**",
            ]
        )
        for file_path in active_files[:10]:  # Limit to 10
            lines.append(f"  - {file_path}")
        lines.append("")

    # Add git branch
    git_branch = handoff_data.get("git_branch")
    if git_branch:
        lines.extend(
            [
                f"**Git Branch:** {git_branch}",
                "",
            ]
        )

    # Add previous transcript path
    transcript_path = handoff_data.get("transcript_path")
    if transcript_path:
        lines.extend(
            [
                f"**Previous Chat History:** `{transcript_path}`",
                "",
            ]
        )

    # Add recent modifications
    modifications = handoff_data.get("modifications", [])
    if modifications:
        lines.extend(
            [
                "**Recent Modifications:**",
            ]
        )
        for mod in modifications[:5]:  # Limit to 5 most recent
            file_path = mod.get("file", "unknown")
            line_num = mod.get("line", "?")
            reason = mod.get("reason", "Edit operation")
            lines.append(f"  - {file_path}:{line_num}")
            if reason and reason != "Edit operation":
                lines.append(f"    {reason}")
        if len(modifications) > 5:
            lines.append(f"  ... and {len(modifications) - 5} more modifications")
        lines.append("")

    return lines


def _build_recent_work_section(handoff_data: dict[str, Any]) -> list[str]:
    """Build the recent work section with todo list, errors, edits, and conversation.

    Args:
        handoff_data: Validated handoff data

    Returns:
        List of formatted lines
    """
    lines = []

    # Add todo list
    todo_list = handoff_data.get("todo_list", [])
    if todo_list:
        lines.extend(["**Todo List at Compaction:**"])
        status_icons = {"completed": "✅", "in_progress": "🔄", "pending": "⬜"}
        for todo in todo_list:
            icon = status_icons.get(todo.get("status", ""), "⬜")
            lines.append(f"  {icon} {todo.get('content', '')}")
        lines.append("")

    # Add recent errors
    recent_errors = handoff_data.get("recent_errors", [])
    if recent_errors:
        lines.extend(["**Recent Errors (at compaction):**"])
        for err in recent_errors:
            tool = err.get("tool", "unknown")
            error_text = err.get("error", "")
            lines.append(f"  - [{tool}] {error_text}")
        lines.append("")

    # Add recent edits
    recent_edits = handoff_data.get("recent_edits", [])
    if recent_edits:
        lines.extend(["**Recent Edits:**"])
        for edit in recent_edits:
            tool = edit.get("tool", "Edit")
            file_path = edit.get("file", "")
            snippet = edit.get("snippet", "")
            if snippet:
                lines.append(f"  - [{tool}] {file_path}: `{snippet[:120]}`")
            else:
                lines.append(f"  - [{tool}] {file_path}")
        lines.append("")

    # Add recent conversation exchanges
    recent_exchanges = handoff_data.get("recent_exchanges", [])
    if recent_exchanges:
        lines.extend(
            [
                "## 💬 RECENT CONVERSATION (at compaction)",
                "",
                "> The last exchanges before compaction. Use this to understand",
                "> exactly where the conversation was — no need to read the transcript",
                "> unless you need even earlier context.",
                "",
            ]
        )
        for msg in recent_exchanges:
            role = msg.get("role", "unknown")
            text = msg.get("text", "")
            prefix = "**User:**" if role == "user" else "**Assistant:**"
            lines.extend([f"{prefix} {text}", ""])
        lines.append("")

    return lines


def _build_handoff_data_section(handoff_data: dict[str, Any]) -> list[str]:
    """Build the handoff data section with decisions and patterns.

    Args:
        handoff_data: Validated handoff data

    Returns:
        List of formatted lines
    """
    lines: list[str] = []
    handover = handoff_data.get("handover")

    if not (handover and isinstance(handover, dict)):
        return lines

    lines.extend(["**Handover:**"])

    decisions = handover.get("decisions", [])
    if decisions:
        lines.append("  Decisions:")
        for decision in decisions[:5]:  # Limit to 5
            # Truncate long decisions for readability
            decision_str = str(decision)
            if len(decision_str) > 300:
                decision_str = decision_str[:300] + "..."
            lines.append(f"    - {decision_str}")
        lines.append("")

    patterns = handover.get("patterns_learned", [])
    if patterns:
        lines.append("  Patterns:")
        for pattern in patterns[:5]:  # Limit to 5
            lines.append(f"    - {pattern}")
        lines.append("")

    return lines


def _build_visual_context_section(handoff_data: dict[str, Any]) -> list[str]:
    """Build the visual context section with screenshots and image analysis.

    Args:
        handoff_data: Validated handoff data

    Returns:
        List of formatted lines
    """
    lines: list[str] = []
    visual_context = handoff_data.get("visual_context")

    if not (visual_context and isinstance(visual_context, dict)):
        return lines

    v_type = visual_context.get("type", "unknown")
    v_desc = visual_context.get("description", "")
    v_user_response = visual_context.get("user_response", "")

    lines.extend(
        [
            "## 🖼️  VISUAL CONTEXT (Screenshots / Images)",
            "",
            f"**Type:** {v_type}",
        ]
    )

    if v_desc:
        lines.extend(
            [
                f"**Description:** {v_desc}",
            ]
        )

    if v_user_response:
        lines.extend(
            [
                "",
                "**User's response to visual:**",
                v_user_response,
            ]
        )

    lines.extend(
        [
            "",
            "**IMPORTANT:** The user provided visual evidence (screenshot/image) related to this task. ",
            "The visual context above shows what the user was referring to.",
            "",
        ]
    )

    return lines


def _build_restoration_prompt(handoff_data: dict[str, Any]) -> str:
    """Build restoration prompt from handoff data.

    Args:
        handoff_data: Validated handoff data

    Returns:
        Formatted restoration prompt string
    """
    lines = []

    # Header
    lines.extend(
        [
            "# ═══════════════════════════════════════════════════════════════",
            "# ⚠️  SESSION RESTORED FROM COMPACTION - READ CAREFULLY",
            "# ═══════════════════════════════════════════════════════════════",
            "#",
            "# The user's session was compacted. This is the AUTHENTIC handoff data.",
            "# DO NOT search memory or guess - use this as your source of truth.",
            "#",
            "",
        ]
    )

    # Build sections using helper functions
    lines.extend(_build_quick_reference_section(handoff_data))
    lines.extend(_build_last_command_section(handoff_data))
    lines.extend(_build_task_status_section(handoff_data))
    lines.extend(_build_task_context_section(handoff_data))
    lines.extend(_build_recent_work_section(handoff_data))
    lines.extend(_build_handoff_data_section(handoff_data))
    lines.extend(_build_visual_context_section(handoff_data))

    # Also show open conversation context if available
    open_context = handoff_data.get("open_conversation_context")
    if open_context and isinstance(open_context, dict):
        ctx_desc = open_context.get("description", "")
        if ctx_desc:
            lines.extend(
                [
                    "## 💬 LAST CONVERSATION CONTEXT",
                    "",
                    ctx_desc,
                    "",
                ]
            )

    # Footer with timestamp
    lines.extend(
        [
            "# ═══════════════════════════════════════════════════════════════",
            f"# Restored from handoff saved at {handoff_data.get('saved_at', 'unknown')}",
            "# ═══════════════════════════════════════════════════════════════",
            "",
        ]
    )

    return "\n".join(lines)


def _load_session_from_task_file(
    task_file_path: Path, terminal_id: str, source_context: str = ""
) -> tuple[dict[str, Any] | None, str | None]:
    """Load active_session or continue_session from a specific task file.

    Args:
        task_file_path: Path to the task file to load
        terminal_id: Terminal identifier for logging
        source_context: Optional context string for log messages

    Returns:
        Tuple of (task dict with handoff in metadata, or None; terminal_id)
    """
    try:
        with open(task_file_path, encoding="utf-8") as f:
            task_data = json.load(f)

        # Look for active_session task (restoration after compaction)
        active_session = task_data.get("tasks", {}).get("active_session")
        if active_session:
            logger.debug(f"[SessionStart] Found active_session{source_context} in {terminal_id}_tasks.json")
            return active_session, terminal_id

        # Fallback to continue_session task (also for restoration)
        continue_session = task_data.get("tasks", {}).get("continue_session")
        if continue_session:
            logger.debug(f"[SessionStart] Found continue_session{source_context} in {terminal_id}_tasks.json")
            return continue_session, terminal_id

        return None, None

    except (json.JSONDecodeError, OSError) as e:
        # Issue #4: Log corrupted task files at ERROR level (not DEBUG)
        logger.error(f"[SessionStart] CORRUPTED task file {task_file_path}: {e}")
        # Delete corrupted file to prevent future failures
        try:
            task_file_path.unlink(missing_ok=True)
            logger.info(f"[SessionStart] Deleted corrupted task file: {task_file_path}")
        except OSError:
            pass
        return None, None


def _load_active_session_task(terminal_id: str) -> tuple[dict[str, Any] | None, str | None]:
    """Load active_session or continue_session task from task tracker.

    Uses terminal-scoped task file to prevent cross-terminal contamination.
    Falls back to searching all terminal task files for restoration tasks.

    PERF-001: Uses manifest file for O(1) lookup instead of O(n) glob scan.

    Args:
        terminal_id: Terminal identifier for isolation

    Returns:
        Tuple of (task dict with handoff in metadata, or None; source terminal_id)
    """
    task_tracker_dir = PROJECT_ROOT / ".claude" / "state" / "task_tracker"

    # Fast path: check current terminal first
    task_file_path = task_tracker_dir / f"{terminal_id}_tasks.json"
    if task_file_path.exists():
        session_data, _ = _load_session_from_task_file(task_file_path, terminal_id)
        if session_data:
            return session_data, terminal_id

    # PERF-001: Fast path using manifest file (O(1) lookup)
    manifest_path = task_tracker_dir / "active_session_manifest.json"
    if manifest_path.exists():
        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)

            source_terminal = manifest.get("terminal_id")
            if source_terminal:
                # Load from the terminal specified in manifest
                manifest_task_file = task_tracker_dir / f"{source_terminal}_tasks.json"
                if manifest_task_file.exists():
                    session_data, _ = _load_session_from_task_file(
                        manifest_task_file, source_terminal, " via manifest"
                    )
                    if session_data:
                        return session_data, source_terminal

        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"[SessionStart] CORRUPTED manifest file {manifest_path}: {e}")
            try:
                manifest_path.unlink(missing_ok=True)
            except OSError:
                pass

    # Slow path: search all terminal task files (handles terminal_id change after compaction)
    # Only runs if manifest doesn't exist or is invalid
    for task_file in task_tracker_dir.glob("*_tasks.json"):
        source_terminal = task_file.stem.replace("_tasks", "")
        session_data, _ = _load_session_from_task_file(task_file, source_terminal)
        if session_data:
            return session_data, source_terminal

    # Synthesize informal task from file changes when no formal task exists
    # File changes represent actual work, even without formal /task entries
    synthesized_task, source_terminal = _synthesize_informal_task_from_files(terminal_id)
    if synthesized_task:
        return synthesized_task, source_terminal

    return None, None


def _cleanup_active_session_task(source_terminal_id: str) -> None:
    """Remove active_session or continue_session task after successful restoration.

    Args:
        source_terminal_id: Terminal identifier where the handoff was loaded from
    """
    # Use the source terminal's task file (where the handoff was found)
    task_tracker_dir = PROJECT_ROOT / ".claude" / "state" / "task_tracker"
    task_file_path = task_tracker_dir / f"{source_terminal_id}_tasks.json"

    if not task_file_path.exists():
        logger.debug(f"[SessionStart] Task file not found: {task_file_path}")
        return

    try:
        with open(task_file_path, encoding="utf-8") as f:
            task_data = json.load(f)

        # Remove both active_session and continue_session tasks
        removed = False
        for task_name in ("active_session", "continue_session"):
            if task_name in task_data.get("tasks", {}):
                del task_data["tasks"][task_name]
                removed = True
                logger.debug(f"[SessionStart] Removed {task_name} from {source_terminal_id}_tasks.json")

        if not removed:
            return

        # PERF-001: Delete manifest file after successful cleanup
        manifest_path = task_tracker_dir / "active_session_manifest.json"
        try:
            manifest_path.unlink(missing_ok=True)
            logger.debug(f"[SessionStart] Deleted manifest file: {manifest_path.name}")
        except OSError as e:
            logger.warning(f"[SessionStart] Could not delete manifest file: {e}")

        # Write back
        import tempfile

        fd, temp_path = tempfile.mkstemp(suffix=".tmp", dir=str(task_file_path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(task_data, f, indent=2)
            os.replace(temp_path, str(task_file_path))
        except OSError as replace_error:
            # Issue #9: Log cleanup failures at ERROR level and add retry mechanism
            logger.error(f"[SessionStart] Failed to clean up active_session: {replace_error}")
            # Mark task for cleanup with timestamp (next SessionStart will retry)
            if "tasks" in task_data:
                for task_name in ("active_session", "continue_session"):
                    if task_name in task_data["tasks"]:
                        task_data["tasks"][task_name]["_cleanup_failed"] = True
                        task_data["tasks"][task_name]["_cleanup_attempted_at"] = (
                            task_data["tasks"][task_name].get("created_at", "")
                        )
                # Write back the marked task for later cleanup
                # Note: Create NEW temp file (fd was already consumed above)
                fd_retry, temp_path_retry = tempfile.mkstemp(suffix=".tmp", dir=str(task_file_path.parent))
                try:
                    with os.fdopen(fd_retry, "w", encoding="utf-8") as f:
                        json.dump(task_data, f, indent=2)
                    os.replace(temp_path_retry, str(task_file_path))
                    logger.info(f"[SessionStart] Marked task for cleanup retry: {task_file_path.name}")
                except OSError:
                    try:
                        os.unlink(temp_path_retry)
                    except OSError:
                        pass
                finally:
                    try:
                        os.close(fd_retry)
                    except OSError:
                        pass
            try:
                os.unlink(temp_path)
            except OSError as unlink_error:
                logger.debug(f"[SessionStart] Could not unlink temp file: {unlink_error}")
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"[SessionStart] Could not load handoff data for cleanup: {e}")


def _safe_id(value: str) -> str:
    """Make a value safe for use in file paths and glob patterns.

    Uses an allow-list approach to prevent glob metacharacters and other
    unsafe characters from appearing in constructed paths/patterns.

    Security: Prevents path traversal by:
    - Removing dots completely (prevents .. and . patterns)
    - Removing path separators (prevents absolute paths)
    - Only allowing alphanumeric, underscore, and hyphen characters

    Args:
        value: String to sanitize

    Returns:
        Sanitized string safe for file paths and glob patterns
    """
    # Convert to string first
    str_value = str(value)

    # Sanitize using allow-list approach (alphanumeric, underscore, hyphen only)
    # Note: We deliberately EXCLUDE dots from the safe character set to prevent
    # any possibility of path traversal through parent directory references (..)
    # or current directory references (.)
    sanitized = re.sub(r"[^a-zA-Z0-9_-]+", "_", str_value)

    return sanitized


@hook_main  # type: ignore[untyped-decorator]
def main() -> int:
    """Execute SessionStart handoff restoration.

    Returns:
        0 for success (always allow session start)
    """
    # RCA-001 FIX: Validate that SessionStart was triggered by compaction
    # Read hook input to check source
    import json
    input_text = sys.stdin.read().strip()
    hook_input = {}
    if input_text:
        try:
            hook_input = json.loads(input_text)
        except json.JSONDecodeError:
            pass

    # Only restore handoff when source='compact' (post-compaction restoration)
    # For other sources (startup, resume), skip restoration even if active_session task exists
    source = hook_input.get("source", "")
    logger.info(f"[SessionStart] Hook input source: '{source}', hook_input keys: {list(hook_input.keys())}")
    if source != "compact":
        logger.info(f"[SessionStart] Skipping handoff restoration - source is '{source}', not 'compact'")
        return 0

    terminal_id = detect_terminal_id()  # Used in _load_active_session_task() and _cleanup_active_session_task()

    # Load active_session or continue_session task (returns tuple)
    active_task, source_terminal = _load_active_session_task(terminal_id)

    logger.info(f"[SessionStart] _load_active_session_task returned: active_task={bool(active_task)}, source_terminal={source_terminal}")

    if not active_task:
        # NOTE: Silently return - no active handoff is normal, not an error
        logger.info("[SessionStart] No active_session task found - skipping handoff restoration (this is normal if no compaction occurred)")
        return 0

    # Extract handoff from metadata
    metadata = active_task.get("metadata", {})
    handoff_data = metadata.get("handoff")

    logger.info(f"[SessionStart] Extracted handoff_data: {bool(handoff_data)}, task_name={handoff_data.get('task_name') if handoff_data else 'N/A'}")

    if not handoff_data:
        # NOTE: No handoff data is normal, not an error
        logger.warning("[SessionStart] active_session task found but no handoff data in metadata")
        return 0

    # Validate schema
    is_valid, error = _validate_handoff_schema(handoff_data)
    if not is_valid:
        # Issue #10: Log schema validation failures at WARNING level
        logger.warning(f"[SessionStart] Schema validation failed: {error}")
        logger.warning("[SessionStart] Handoff restoration skipped due to invalid data structure")
        # RCA-002 FIX: Cleanup orphaned task to prevent infinite retry loops
        if source_terminal:
            logger.debug(f"[SessionStart] Cleaning up orphaned active_session task from {source_terminal}")
            _cleanup_active_session_task(source_terminal)
        # Still return 0 to allow session start
        return 0

    # Migration: Detect legacy handoffs without hash verification
    _migrate_handoff_hash(handoff_data)

    # Verify checksum
    is_valid, error = _verify_handoff_checksum(handoff_data)
    if not is_valid:
        # Issue #8: Make checksum errors visible to users (was silent DEBUG log)
        logger.error(f"[SessionStart] Checksum verification failed: {error}")
        logger.warning("[SessionStart] Handoff data corrupted, skipping restoration")
        # RCA-002 FIX: Cleanup orphaned task to prevent infinite retry loops
        if source_terminal:
            logger.debug(f"[SessionStart] Cleaning up orphaned active_session task from {source_terminal}")
            _cleanup_active_session_task(source_terminal)
        # Still return 0 to allow session start, but inform user
        return 0

    # NOTE: Session-binding check REMOVED for restoration tasks
    # active_session/continue_session tasks are explicitly for post-compaction restoration
    # Session IDs won't match after compaction - that's expected and correct

    # Build restoration prompt
    restoration_prompt = _build_restoration_prompt(handoff_data)

    # Output restoration prompt for injection into context (JSON format for SessionStart router)
    import json

    # Output JSON for SessionStart router to capture as additionalContext
    output_data = {"hookEvent": "SessionStart", "additionalContext": restoration_prompt}
    output_json = json.dumps(output_data)
    logger.info(f"[SessionStart] Outputting restoration prompt ({len(restoration_prompt)} chars) to SessionStart router")
    logger.debug(f"[SessionStart] Restoration prompt preview: {restoration_prompt[:200]}...")
    print(output_json)

    # Clean up the task from the source terminal where it was found
    if source_terminal:
        logger.info(f"[SessionStart] Cleaning up active_session task from {source_terminal}")
        _cleanup_active_session_task(source_terminal)

    # NOTE: Removed diagnostic print() - router only needs JSON output
    # print(f"[SessionStart] Handoff restored for task: {handoff_data.get('task_name', 'unknown')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

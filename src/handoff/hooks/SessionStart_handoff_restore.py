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

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Hook directory resolution
HOOKS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = HOOKS_DIR.parent

# Add handoff package to path
HANDOFF_PACKAGE = Path("P:/packages/handoff/src")
if str(HANDOFF_PACKAGE) not in sys.path:
    sys.path.insert(0, str(HANDOFF_PACKAGE))

from handoff.migrate import compute_metadata_checksum

# Add hooks dir for terminal detection (use existing comprehensive implementation)
# Path: P:/packages/handoff/src/handoff/hooks/SessionStart_handoff_restore.py
# Need to reach: P:/.claude/hooks/terminal_detection.py
claude_hooks_dir = Path("P:/.claude/hooks")
if str(claude_hooks_dir) not in sys.path:
    sys.path.insert(0, str(claude_hooks_dir))

try:
    from terminal_detection import detect_terminal_id
except ImportError:
    def detect_terminal_id() -> str:
        return f"term_{os.getpid()}"

try:
    from __lib.hook_base import hook_main
except ImportError:
    def hook_main(func):
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
            return False, f"Missing required field: {field}"

    # Validate timestamp
    try:
        datetime.fromisoformat(handoff_data["saved_at"])
    except (ValueError, TypeError):
        return False, f"Invalid saved_at timestamp: {handoff_data.get('saved_at')}"

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

    if not stored_checksum.startswith(computed):
        return False, f"Checksum mismatch: stored={stored_checksum[:16]}... computed={computed[:16]}..."

    return True, None


def _build_restoration_prompt(handoff_data: dict[str, Any]) -> str:
    """Build restoration prompt from handoff data.

    Args:
        handoff_data: Validated handoff data

    Returns:
        Formatted restoration prompt string
    """
    # ⚠️ CRITICAL: The full original_user_request MUST be displayed without truncation.
    # This is the AUTHENTIC source of what the user was working on. Truncation causes
    # the LLM to lose context and hallucinate commands after compaction.

    # ═══════════════════════════════════════════════════════════════
    # ⚠️  MOST IMPORTANT SECTION: THE USER'S ACTUAL LAST COMMAND
    # ═══════════════════════════════════════════════════════════════
    # This MUST come FIRST to prevent LLM from forming wrong mental model
    # from the core conversation summary that appears before this handoff.
    # ═══════════════════════════════════════════════════════════════

    original_request = handoff_data.get("original_user_request")
    last_command_section = []

    if original_request:
        last_command_section = [
            "## ⚠️  THE USER'S LAST COMMAND (AUTHENTIC - READ THIS FIRST)",
            "",
            original_request,  # FULL content, no truncation
            "",
            "",
            "───",
            "**CRITICAL:** This IS the user's last command. Start from here.",
            "Do NOT guess, do NOT search memory, do NOT hallucinate.",
            "",
            "",
        ]

    lines = [
        "# ═══════════════════════════════════════════════════════════════",
        "# ⚠️  SESSION RESTORED FROM COMPACTION - READ CAREFULLY",
        "# ═══════════════════════════════════════════════════════════════",
        "#",
        "# The user's session was compacted. This is the AUTHENTIC handoff data.",
        "# DO NOT search memory or guess - use this as your source of truth.",
        "#",
        "",
    ]

    # Insert last command FIRST (right after header)
    lines.extend(last_command_section)

    # Then continue with context sections
    lines.extend([
        "## 📍 WHERE WE ARE IN THE TASK",
        "",
        f"**Task:** {handoff_data.get('task_name', 'unknown')}",
        f"**Progress:** {handoff_data.get('progress_percent', 0)}%",
        "",
    ])

    # Add blocker if present - this is what we're stuck on
    blocker = handoff_data.get("blocker")
    if blocker:
        if isinstance(blocker, dict):
            blocker_desc = blocker.get("description", str(blocker))
        else:
            blocker_desc = str(blocker)
        lines.extend([
            f"**Current Blocker:** {blocker_desc}",
            "",
        ])

    # Add pending operations if present - interrupted work
    pending_operations = handoff_data.get("pending_operations", [])
    if pending_operations:
        lines.extend([
            "⚠️ **Pending Operations:** (work in progress when compacted)",
        ])
        for op in pending_operations[:5]:  # Limit to 5
            op_type = op.get("type", "unknown")
            op_target = op.get("target", "unknown")
            op_state = op.get("state", "unknown")
            lines.append(f"  - [{op_type.upper()}] {op_target} ({op_state})")
        lines.append("")

    # Add next steps
    next_steps = handoff_data.get("next_steps", "")
    if next_steps:
        lines.extend([
            "**Next Steps:**",
            next_steps,
            "",
        ])

    lines.extend([
        "## 📋 TASK CONTEXT",
        "",
    ])

    # Add active files
    active_files = handoff_data.get("active_files", [])
    if active_files:
        lines.extend([
            "**Active Files:**",
        ])
        for file_path in active_files[:10]:  # Limit to 10
            lines.append(f"  - {file_path}")
        lines.append("")

    # Add git branch
    git_branch = handoff_data.get("git_branch")
    if git_branch:
        lines.extend([
            f"**Git Branch:** {git_branch}",
            "",
        ])

    # Add handover summary
    handover = handoff_data.get("handover")
    if handover and isinstance(handover, dict):
        lines.extend([
            "**Handover:**",
        ])

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

    # Also show open conversation context if available
    open_context = handoff_data.get("open_conversation_context")
    if open_context and isinstance(open_context, dict):
        ctx_desc = open_context.get("description", "")
        if ctx_desc:
            lines.extend([
                "## 💬 LAST CONVERSATION CONTEXT",
                "",
                ctx_desc,
                "",
            ])

    # ═══════════════════════════════════════════════════════════════
    # ⚠️  VISUAL CONTEXT - Screenshots and image analysis
    # ═══════════════════════════════════════════════════════════════
    # This section preserves visual evidence (screenshots, image analysis)
    # that would otherwise be lost during compaction.
    # ═══════════════════════════════════════════════════════════════

    visual_context = handoff_data.get("visual_context")
    if visual_context and isinstance(visual_context, dict):
        v_type = visual_context.get("type", "unknown")
        v_desc = visual_context.get("description", "")
        v_user_response = visual_context.get("user_response", "")

        lines.extend([
            "## 🖼️  VISUAL CONTEXT (Screenshots / Images)",
            "",
            f"**Type:** {v_type}",
        ])

        if v_desc:
            lines.extend([
                f"**Description:** {v_desc}",
            ])

        if v_user_response:
            lines.extend([
                "",
                "**User's response to visual:**",
                v_user_response,
            ])

        lines.extend([
            "",
            "**IMPORTANT:** The user provided visual evidence (screenshot/image) related to this task. ",
            "The visual context above shows what the user was referring to.",
            "",
        ])

    lines.extend([
        "# ═══════════════════════════════════════════════════════════════",
        f"# Restored from handoff saved at {handoff_data.get('saved_at', 'unknown')}",
        "# ═══════════════════════════════════════════════════════════════",
        "",
    ])

    return "\n".join(lines)


def _fallback_find_by_session() -> dict[str, Any] | None:
    """Fallback: Find most recent task file with matching session_id.

    Safety net for edge cases where terminal_id doesn't match
    (test mode, environment variables, missing module).

    Validates session_id to prevent cross-terminal contamination.

    Returns:
        Task dict with handoff in metadata, or None if not found
    """
    try:
        session_id = os.environ.get("CLAUDE_SESSION_ID")
        if not session_id:
            return None  # Can't validate without session_id

        task_tracker_dir = Path("P:/.claude/state/task_tracker")
        if not task_tracker_dir.exists():
            return None

        # Find all task files, sort by modification time (most recent first)
        task_files = list(task_tracker_dir.glob("*_tasks.json"))
        if not task_files:
            return None

        task_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        # Check 5 most recent files for matching session_id
        for task_file in task_files[:5]:
            try:
                with open(task_file, encoding="utf-8") as f:
                    task_data = json.load(f)

                # Try active_session first
                active_session = task_data.get("tasks", {}).get("active_session")
                if active_session:
                    handoff = active_session.get("metadata", {}).get("handoff", {})
                    if handoff.get("session_id") == session_id:
                        # Validate checksum before accepting
                        is_valid, _ = _verify_handoff_checksum(handoff)
                        if is_valid:
                            return active_session
                        # Checksum failed - corrupted data, skip

                # Try continue_session as fallback
                continue_session = task_data.get("tasks", {}).get("continue_session")
                if continue_session:
                    handoff = continue_session.get("metadata", {}).get("handoff", {})
                    if handoff.get("session_id") == session_id:
                        is_valid, _ = _verify_handoff_checksum(handoff)
                        if is_valid:
                            return continue_session

            except (json.JSONDecodeError, OSError, KeyError):
                continue  # Skip corrupted files

    except Exception:
        pass  # Fallback failure - not critical

    return None


def _load_active_session_task(
    terminal_id: str
) -> dict[str, Any] | None:
    """Load active_session task from task tracker.

    Uses terminal-scoped task file to prevent cross-terminal contamination.
    The global current_session.json is NOT used because it causes terminals
    to load each other's handoff data.

    Priority:
        1. Exact terminal_id match (fastest, most reliable)
        2. Most recent file with matching session_id (fallback)

    Args:
        terminal_id: Terminal identifier for isolation

    Returns:
        Task dict with handoff in metadata, or None if not found
    """
    # Priority 1: Try exact terminal_id match
    task_tracker_dir = Path("P:/.claude/state/task_tracker")
    task_file_path = task_tracker_dir / f"{terminal_id}_tasks.json"

    if task_file_path.exists():
        try:
            with open(task_file_path, encoding="utf-8") as f:
                task_data = json.load(f)

            # Look for active_session task
            active_session = task_data.get("tasks", {}).get("active_session")
            if active_session:
                return active_session

            # Fallback to continue_session task
            continue_session = task_data.get("tasks", {}).get("continue_session")
            if continue_session:
                return continue_session

        except (json.JSONDecodeError, OSError):
            pass  # Fall through to session-based fallback

    # Priority 2: Fallback to session-based search
    # This handles edge cases (test mode, env variables) while preserving isolation
    return _fallback_find_by_session()


def _cleanup_active_session_task(terminal_id: str) -> None:
    """Remove active_session task after successful restoration.

    Uses terminal-scoped task file to prevent cross-terminal contamination.

    Args:
        terminal_id: Terminal identifier for task file
    """
    # Use terminal-scoped task file directly
    task_tracker_dir = Path("P:/.claude/state/task_tracker")
    task_file_path = task_tracker_dir / f"{terminal_id}_tasks.json"

    if not task_file_path.exists():
        return

    try:
        with open(task_file_path, encoding="utf-8") as f:
            task_data = json.load(f)

        # Remove active_session task
        if "active_session" in task_data.get("tasks", {}):
            del task_data["tasks"]["active_session"]

            # Write back
            import tempfile
            fd, temp_path = tempfile.mkstemp(
                suffix=".tmp", dir=str(task_file_path.parent)
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(task_data, f, indent=2)
                os.replace(temp_path, str(task_file_path))
            except OSError:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
    except (json.JSONDecodeError, OSError):
        pass


def _safe_id(value: str) -> str:
    """Make a value safe for use in file paths.

    Args:
        value: String to sanitize

    Returns:
        Sanitized string safe for file paths
    """
    return re.sub(r'[\/*?:"<>|]', '_', value)


def _cleanup_active_command_file(terminal_id: str) -> None:
    """Remove active_command file after successful restoration.

    Args:
        terminal_id: Terminal identifier (unused, filename has embedded IDs)
    """
    try:
        current_session_file = Path("P:/.claude/current_session.json")
        if not current_session_file.exists():
            return

        session_data = json.loads(current_session_file.read_text())
        session_id = session_data.get("session_id")
        if not session_id:
            return

        safe_session = _safe_id(session_id)
        pid = os.getpid()
        pattern = f"{safe_session}_*_{pid}.json"

        active_commands_dir = Path("P:/.claude/state/active_commands")
        if not active_commands_dir.exists():
            return

        matching_files = list(active_commands_dir.glob(pattern))
        for file_path in matching_files:
            try:
                file_path.unlink()
            except OSError:
                pass

    except (OSError, json.JSONDecodeError):
        pass




@hook_main
def main() -> int:
    """Execute SessionStart handoff restoration.

    Returns:
        0 for success (always allow session start)
    """
    terminal_id = detect_terminal_id()

    # NOTE: Removed diagnostic print() - any non-JSON output breaks router parsing
    # print(f"[SessionStart] Checking for handoff restoration (terminal: {terminal_id})...")

    # Load active_session task
    active_task = _load_active_session_task(terminal_id)

    if not active_task:
        # NOTE: Silently return - no active handoff is normal, not an error
        # print("[SessionStart] No active handoff found.")
        return 0

    # Extract handoff from metadata
    metadata = active_task.get("metadata", {})
    handoff_data = metadata.get("handoff")

    if not handoff_data:
        # NOTE: No handoff data is normal, not an error
        # print("[SessionStart] Active task found but no handoff data.")
        return 0

    # Validate schema
    is_valid, error = _validate_handoff_schema(handoff_data)
    if not is_valid:
        # NOTE: Schema validation failures are silent - don't spam on every session
        # print(f"[SessionStart] Warning: Invalid handoff schema: {error}")
        return 0

    # Verify checksum
    is_valid, error = _verify_handoff_checksum(handoff_data)
    if not is_valid:
        # NOTE: Checksum failures are silent - don't spam on every session
        # print(f"[SessionStart] Warning: Checksum verification failed: {error}")
        return 0

    # SESSION-BINDING: Only restore handoff if it's from the current session
    # This makes the system: multi-terminal friendly, no TTL, immune to stale data

    # Extract session ID from handoff's transcript_path
    handoff_transcript = handoff_data.get("transcript_path", "")
    handoff_session = Path(handoff_transcript).stem if handoff_transcript else ""

    # Extract session ID from CURRENT session (not from stale active_task metadata)
    # CRITICAL: Must use current_session.json to get ACTUAL current session, not old task data
    current_session_file = Path("P:/.claude/current_session.json")
    if current_session_file.exists():
        try:
            with open(current_session_file, encoding="utf-8") as f:
                current_session_data = json.load(f)
            current_session = current_session_data.get("session_id", "")
        except (json.JSONDecodeError, OSError):
            current_session = ""
    else:
        current_session = ""

    # Only restore if handoff belongs to CURRENT session
    if current_session and handoff_session != current_session:
        # Silent skip - handoff is from a different session, don't restore it
        return 0

    # Build restoration prompt
    restoration_prompt = _build_restoration_prompt(handoff_data)

    # Output restoration prompt for injection into context (JSON format for SessionStart router)
    import json
    # Output JSON for SessionStart router to capture as additionalContext
    print(json.dumps({
        "hookEvent": "SessionStart",
        "additionalContext": restoration_prompt
    }))

    # Clean up active_session task after successful restoration
    _cleanup_active_session_task(terminal_id)

    # NOTE: Removed diagnostic print() - router only needs JSON output
    # print(f"[SessionStart] Handoff restored for task: {handoff_data.get('task_name', 'unknown')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

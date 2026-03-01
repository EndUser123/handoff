#!/usr/bin/env python3
"""
PreCompact Hook - Handoff Version

Captures handoff before transcript compaction.

Flow:
  1. Determine task identity (using TaskIdentityManager)
  2. Capture handoff data (progress, blocker, next steps)
  3. Store handoff in task metadata
  4. Signal: Ready for /compact

Renamed from checkpoint package to handoff package.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Modern path resolution
HOOKS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = HOOKS_DIR.parent

# Add session management module path
SESSION_MODULE_PATH = PROJECT_ROOT / "__csf" / "src"
sys.path.insert(0, str(SESSION_MODULE_PATH))

# Add hooks dir for terminal detection (use existing comprehensive implementation)
# Path: {hooks_dir}/PreCompact_handoff_capture.py
# Need to reach: {project_root}/.claude/hooks/terminal_detection.py
claude_hooks_dir = PROJECT_ROOT / ".claude" / "hooks"
if str(claude_hooks_dir) not in sys.path:
    sys.path.insert(0, str(claude_hooks_dir))

# Import auto-logging decorator
from __lib.hook_base import hook_main

# Import from handoff package
from handoff.config import ensure_directories
from handoff.migrate import compute_metadata_checksum, validate_handoff_size

# Import handoff hooks library
# Add handoff package to path
HANDOFF_PACKAGE = HOOKS_DIR.parent / "src"
if str(HANDOFF_PACKAGE) not in sys.path:
    sys.path.insert(0, str(HANDOFF_PACKAGE))

from handoff.hooks.__lib import (
    handoff_store,
    handover,
    task_identity_manager,
    transcript,
)

HandoffStoreClass = handoff_store.HandoffStore
HandoverBuilder = handover.HandoverBuilder
TaskIdentityManager = task_identity_manager.TaskIdentityManager
TranscriptParser = transcript.TranscriptParser

try:
    from modules.session_management.session_activity_tracker import (
        _get_session_id_from_env,
        get_session_files,
    )

    _SESSION_ACTIVITY_AVAILABLE = True
except ImportError:
    logger.debug("[PreCompact] session_activity module not available")
    _SESSION_ACTIVITY_AVAILABLE = False

try:
    from terminal_detection import detect_terminal_id
except ImportError:
    logger.debug("[PreCompact] terminal_detection module not available")

    def detect_terminal_id() -> str:
        return f"term_{os.getpid()}"


try:
    from tool_sequence_manager import load_tool_sequence

    _TOOL_SEQUENCE_AVAILABLE = True
except ImportError:
    logger.debug("[PreCompact] tool_sequence module not available")
    _TOOL_SEQUENCE_AVAILABLE = False


def _safe_id(value: str) -> str:
    """Sanitize a string for use in filenames.

    Args:
        value: Raw identifier string

    Returns:
        Sanitized identifier safe for filesystem use
    """
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(value))


class PreCompactHandoffCapture:
    """Capture and store session state before compaction using handoff package.

    This orchestrator coordinates:
    - TranscriptParser: For transcript data extraction
    - HandoverBuilder: For handover data generation
    - HandoffStore: For handoff storage operations
    - TaskIdentityManager: For task identity tracking
    """

    @staticmethod
    def _find_terminal_transcript() -> str | None:
        """Find terminal-specific transcript using session_id.

        Returns:
            Path to transcript file or None if not found
        """
        project_conversations_dir = os.path.expanduser("~/.claude/projects/P--/")
        if not (os.path.exists(project_conversations_dir) and _SESSION_ACTIVITY_AVAILABLE):
            logger.info(
                "[PreCompact] Project conversations directory not found or session activity unavailable"
            )
            return None

        session_id = _get_session_id_from_env()
        if not session_id:
            logger.info(
                "[PreCompact] No session_id available - cannot find terminal-specific transcript"
            )
            return None

        # Build transcript path directly from session_id (terminal-isolated)
        candidate_path = os.path.join(project_conversations_dir, f"{session_id}.jsonl")
        if not os.path.exists(candidate_path):
            logger.info(f"[PreCompact] Session transcript not found: {session_id}.jsonl")
            return None

        size_mb = os.path.getsize(candidate_path) / (1024 * 1024)
        # Sanity check: skip if obviously wrong (too large or subagent file)
        if size_mb <= 50 and "subagent" not in candidate_path.lower():
            logger.info(
                f"[PreCompact] Found terminal transcript: {session_id} ({size_mb:.1f}MB)"
            )
            return candidate_path
        else:
            logger.info(
                f"[PreCompact] Transcript exists but fails sanity check: {size_mb:.1f}MB"
            )
            return None

    def __init__(self, hook_input: dict[str, Any] | None = None):
        """Initialize PreCompact handoff orchestrator.

        Args:
            hook_input: Optional hook input dict
        """
        self.project_root = PROJECT_ROOT
        self.terminal_id = detect_terminal_id()
        self.hook_input = hook_input or {}

        # Get transcript_path from hook input, or find it automatically
        _UNSET = object()
        transcript_path_value = self.hook_input.get("transcript_path", _UNSET)
        if transcript_path_value is _UNSET:
            self.transcript_path = self._find_terminal_transcript()
            if not self.transcript_path:
                logger.info(
                    "[PreCompact] No suitable session transcript found - skipping transcript parsing"
                )
        else:
            self.transcript_path = transcript_path_value

        # Ensure handoff directories exist
        ensure_directories()

        # Initialize components
        self.parser = TranscriptParser(transcript_path=self.transcript_path)
        self.handover_builder = HandoverBuilder(
            project_root=self.project_root, transcript_parser=self.parser
        )
        self.handoff_store = HandoffStoreClass(
            project_root=self.project_root, terminal_id=self.terminal_id
        )
        self.task_manager = TaskIdentityManager(
            project_root=self.project_root, terminal_id=self.terminal_id
        )

    def extract_progress_percentage(self, task_name: str) -> int:
        """Extract progress % from progress file.

        Args:
            task_name: Name of task (unused, kept for API compatibility)

        Returns:
            Progress percentage (0-100)
        """
        progress_file = self.project_root / ".claude" / "progress.txt"
        if progress_file.exists():
            try:
                return int(progress_file.read_text().strip().rstrip("%"))
            except ValueError as e:
                logger.debug(f"[PreCompact] Could not parse progress value: {e}")
        return 0

    def extract_modified_files(self) -> list[str]:
        """Extract files tracked in this session via session activity tracker.

        Returns:
            List of modified file paths (limited to 10)
        """
        if not _SESSION_ACTIVITY_AVAILABLE:
            return []

        try:
            session_id = _get_session_id_from_env()
            if not session_id:
                logger.info("[PreCompact] Warning: No session ID available")
                return []

            files = get_session_files(
                session_id=session_id, operation_filter=["read", "edit", "write"]
            )
            return files[:10]  # type: ignore[no-any-return]  # Limit to 10
        except Exception as e:
            logger.warning(f"[PreCompact] Could not get session files: {e}")
            return []

    def _load_active_command_file(self) -> str | None:
        """Load the active command from state/active_commands directory.

        Checks feature flag HANDOFF_ACTIVE_COMMAND_ENABLED.
        Gets session_id, terminal_id, and reads the appropriate file.

        Returns:
            The command string or None if unavailable
        """
        # Check feature flag
        if not os.environ.get("HANDOFF_ACTIVE_COMMAND_ENABLED", "false").lower() == "true":
            return None

        try:
            # Get session_id (try env var first, then fall back to current_session.json)
            session_id = None
            if _SESSION_ACTIVITY_AVAILABLE:
                session_id = _get_session_id_from_env()

            if not session_id:
                # Read from current_session.json
                from handoff.config import load_json_file

                current_session_file = self.project_root / ".claude" / "current_session.json"
                session_data = load_json_file(current_session_file)
                if session_data:
                    session_id = session_data.get("session_id")

            if not session_id:
                return None

            # Get terminal_id and PID
            terminal_id = self.terminal_id
            pid = os.getpid()

            # Sanitize identifiers
            safe_session = _safe_id(session_id)
            safe_terminal = _safe_id(terminal_id)
            safe_pid = _safe_id(str(pid))

            # Build file path: .claude/state/active_commands/{safe_session}_{safe_terminal}_{safe_pid}.json
            active_cmd_file = (
                self.project_root
                / ".claude"
                / "state"
                / "active_commands"
                / f"{safe_session}_{safe_terminal}_{safe_pid}.json"
            )

            if active_cmd_file.exists():
                from handoff.config import load_json_file

                cmd_data = load_json_file(active_cmd_file)
                if cmd_data:
                    command = cmd_data.get("command", "")
                    if command:
                        return command  # type: ignore[no-any-return]

        except Exception as e:
            logger.debug(f"[PreCompact] Could not extract implementation status: {e}")
            # Graceful failure - return None if any error occurs
            pass

        return None

    def extract_next_steps(self, task_name: str) -> list[str]:
        """Extract next steps from next-steps file.

        Args:
            task_name: Name of task (unused, kept for API compatibility)

        Returns:
            List of next step descriptions (limited to 5)
        """
        next_steps_file = self.project_root / ".claude" / "next-steps.txt"
        if next_steps_file.exists():
            return [
                line.strip()
                for line in next_steps_file.read_text().split("\n")
                if line.strip() and not line.startswith("#")
            ][:5]
        return []

    def _load_tool_sequence(self) -> list[dict]:
        """Load current tool sequence for evidence carry-forward across compaction.

        Returns full tool sequence (up to 30 entries) so that
        evidence can be restored on session start and validated by
        existing invalidation logic.
        """
        if not _TOOL_SEQUENCE_AVAILABLE:
            return []
        try:
            tools = load_tool_sequence()
            # Only carry forward observation-relevant entries
            return tools[-30:]  # Last 30 entries max
        except Exception as e:
            logger.debug(f"[PreCompact] Could not extract recent errors: {e}")
            return []

    def _extract_file_modifications(self) -> list[str]:
        """Extract list of modified files using the parser.

        Returns:
            List of file paths modified in this session
        """
        modifications = self.parser.extract_modifications()
        if modifications:
            return [m.get("file") for m in modifications if m.get("file")]
        return []

    def _scan_transcript_for_test_results(self, recent_lines: list[str]) -> dict[str, Any]:
        """Scan transcript lines for test results and verification activity.

        Args:
            recent_lines: List of transcript JSONL lines to scan

        Returns:
            Dict with passed, failed counts and verification_found flag
        """
        test_pattern = re.compile(
            r"(?P<result>passed|failed|PASSED|FAILED|✓|✗|❌|✅)\s*(?P<count>\d*)", re.IGNORECASE
        )
        verification_pattern = re.compile(
            r"(verified|verification|tests? run|assert|pytest)", re.IGNORECASE
        )

        passed = 0
        failed = 0
        verification_found = False

        for line in recent_lines:
            try:
                entry = json.loads(line)
                content = ""

                # Extract content from various message formats
                if entry.get("type") == "assistant":
                    msg = entry.get("message", {})
                    if isinstance(msg, dict):
                        content = msg.get("content", "")
                    elif isinstance(msg, str):
                        content = msg

                    # Check for test results
                    if content:
                        # Count passed/failed indicators
                        for match in test_pattern.finditer(content):
                            result = match.group("result").upper()
                            if result in ("PASSED", "✓", "✅"):
                                passed += 1
                            elif result in ("FAILED", "✗", "❌"):
                                failed += 1

                        # Check for verification activity
                        if verification_pattern.search(content):
                            verification_found = True

            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.debug(f"[PreCompact] Skipping invalid checkpoint entry: {e}")
                continue

        return {"passed": passed, "failed": failed, "verification_found": verification_found}

    def _build_test_results_dict(self, passed: int, failed: int) -> dict[str, Any] | None:
        """Build test results dict with status based on passed/failed counts.

        Args:
            passed: Number of passed tests
            failed: Number of failed tests

        Returns:
            Test results dict or None if no tests found
        """
        if passed > 0 or failed > 0:
            result = {
                "passed": passed,
                "failed": failed,
                "total": passed + failed,
            }
            if failed == 0 and passed > 0:
                result["status"] = "all_passed"
            elif failed > 0:
                result["status"] = "has_failures"
            return result
        return None

    def _determine_completion_state(
        self, files_modified: list[str], passed: int, failed: int, verification_found: bool
    ) -> str:
        """Determine completion state based on test results and modifications.

        Args:
            files_modified: List of files modified in session
            passed: Number of passed tests
            failed: Number of failed tests
            verification_found: Whether verification activity was found

        Returns:
            Completion state: verified, implemented, or in_progress
        """
        if files_modified and passed > 0 and failed == 0:
            return "verified"
        elif files_modified:
            return "implemented"
        elif verification_found:
            return "verified"
        else:
            return "in_progress"

    def _extract_implementation_status(self) -> dict[str, Any]:
        """Extract implementation status from recent transcript activity.

        Detects:
        - Test results (passed/failed)
        - Files modified in this session
        - Completion state (implemented, verified, in-progress)

        Returns:
            Dict with implementation status details
        """
        status = {
            "test_results": None,
            "files_modified": [],
            "completion_state": "unknown",  # implemented, verified, in_progress, unknown
            "last_verification": None,
        }

        if not self.transcript_path:
            return status

        try:
            # Extract file modifications
            status["files_modified"] = self._extract_file_modifications()

            # Scan recent transcript for test results and verification
            with open(self.transcript_path, encoding="utf-8") as f:
                lines = f.readlines()

            # Check last 100 lines for test results
            recent_lines = lines[-100:] if len(lines) > 100 else lines

            # Scan for test results
            test_scan = self._scan_transcript_for_test_results(recent_lines)
            passed = test_scan["passed"]
            failed = test_scan["failed"]
            verification_found = test_scan["verification_found"]

            # Build test results dict
            status["test_results"] = self._build_test_results_dict(passed, failed)

            # Determine completion state
            status["completion_state"] = self._determine_completion_state(
                status["files_modified"], passed, failed, verification_found
            )

            if verification_found:
                status["last_verification"] = "tests_or_verification_found"

        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
            logger.debug(f"[PreCompact] Could not read transcript for recent work: {e}")

        return status

    def _extract_todo_list(self) -> list[dict]:
        """Extract the last TodoWrite state from the transcript.

        Scans the transcript JSONL for the most recent TodoWrite tool_use call
        and returns its todos array. Terminal-scoped via transcript_path.

        Returns:
            List of todo dicts (content, status, activeForm) or [] if none found.
        """
        if not self.transcript_path:
            return []
        last_todos: list[dict] = []
        with open(self.transcript_path, encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get("type") != "assistant":
                        continue
                    msg = entry.get("message", {})
                    content = msg.get("content", []) if isinstance(msg, dict) else []
                    if not isinstance(content, list):
                        continue
                    for block in content:
                        if (
                            isinstance(block, dict)
                            and block.get("type") == "tool_use"
                            and block.get("name") == "TodoWrite"
                        ):
                            todos = block.get("input", {}).get("todos", [])
                            if isinstance(todos, list) and todos:
                                last_todos = todos  # keep updating to get the LAST one
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue
        return last_todos

    def _build_tool_name_map(self, recent_lines: list[str]) -> dict[str, str]:
        """Build tool_use id→name map from transcript entries.

        Args:
            recent_lines: List of transcript JSONL lines to scan

        Returns:
            Dict mapping tool_use IDs to tool names
        """
        tool_name_map: dict[str, str] = {}
        for line in recent_lines:
            try:
                entry = json.loads(line)
                if entry.get("type") != "assistant":
                    continue
                msg = entry.get("message", {})
                content = msg.get("content", []) if isinstance(msg, dict) else []
                if not isinstance(content, list):
                    continue
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_name_map[block.get("id", "")] = block.get("name", "unknown")
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.debug(f"[PreCompact] Skipping invalid checkpoint entry: {e}")
                continue
        return tool_name_map

    def _extract_error_from_tool_result(
        self, block: dict[str, Any], tool_name_map: dict[str, str]
    ) -> dict[str, Any] | None:
        """Extract error from a tool_result block.

        Args:
            block: tool_result block from transcript
            tool_name_map: Mapping of tool_use IDs to tool names

        Returns:
            Error dict with 'tool' and 'error' keys, or None if not an error
        """
        if not block.get("is_error", False):
            return None

        tool_id = block.get("tool_use_id", "")
        tool_name = tool_name_map.get(tool_id, "unknown")
        raw = block.get("content", "")

        # Handle list content format
        if isinstance(raw, list):
            raw = " ".join(r.get("text", "") for r in raw if isinstance(r, dict))

        return {
            "tool": tool_name,
            "error": str(raw)[:500],  # cap at 500 chars
        }

    def _extract_recent_errors(self, max_errors: int = 5) -> list[dict]:
        """Extract recent tool errors from the transcript.

        Scans for tool_result entries with is_error=True or Bash results
        with non-zero exit codes. Returns the last max_errors occurrences.

        Returns:
            List of dicts with 'tool', 'error', 'truncated_output' keys.
        """
        if not self.transcript_path:
            return []

        with open(self.transcript_path, encoding="utf-8") as f:
            lines = f.readlines()

        # Only scan the last 200 lines for performance
        recent = lines[-200:] if len(lines) > 200 else lines

        # Build tool_use id→name map
        tool_name_map = self._build_tool_name_map(recent)

        # Collect errors from tool_result entries
        errors: list[dict] = []
        for line in recent:
            try:
                entry = json.loads(line)
                if entry.get("type") != "tool":
                    continue

                msg = entry.get("message", {})
                if not isinstance(msg, dict):
                    continue

                content_list = msg.get("content", [])
                if not isinstance(content_list, list):
                    continue

                for block in content_list:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "tool_result":
                        continue

                    error = self._extract_error_from_tool_result(block, tool_name_map)
                    if error:
                        errors.append(error)

            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.debug(f"[PreCompact] Skipping invalid checkpoint entry: {e}")
                continue

        return errors[-max_errors:]

    def _extract_recent_exchanges(self, max_pairs: int = 6) -> list[dict]:
        """Extract the last N user↔assistant conversation pairs from the transcript.

        Provides inline context so the LLM doesn't need to read the full
        transcript file just to understand what was happening at compaction.

        Returns:
            List of dicts with 'role' ('user'|'assistant') and 'text' keys,
            in chronological order, capped at max_pairs*2 messages.
        """
        if not self.transcript_path:
            return []
        messages: list[dict] = []
        with open(self.transcript_path, encoding="utf-8") as f:
            lines = f.readlines()
        recent = lines[-300:] if len(lines) > 300 else lines
        for line in recent:
            try:
                entry = json.loads(line)
                role = entry.get("type")
                if role == "user":
                    msg = entry.get("message", {})
                    content = msg.get("content", "") if isinstance(msg, dict) else ""
                    if isinstance(content, list):
                        text = " ".join(
                            c.get("text", "")
                            for c in content
                            if isinstance(c, dict) and c.get("type") == "text"
                        )
                    else:
                        text = str(content)
                    text = text.strip()
                    if text and len(text) > 5:
                        messages.append({"role": "user", "text": text[:800]})
                elif role == "assistant":
                    msg = entry.get("message", {})
                    content = msg.get("content", []) if isinstance(msg, dict) else []
                    text_parts = []
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text_parts.append(block.get("text", ""))
                    elif isinstance(content, str):
                        text_parts = [content]
                    text = " ".join(text_parts).strip()
                    if text and len(text) > 5:
                        messages.append({"role": "assistant", "text": text[:800]})
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.debug(f"[PreCompact] Skipping invalid checkpoint entry: {e}")
                continue
        # Return only the last max_pairs*2 messages (pairs = user+assistant)
        return messages[-(max_pairs * 2) :]

    def _extract_recent_edits(self, max_edits: int = 10) -> list[dict]:
        """Extract recent Edit/Write tool calls from the transcript.

        Captures file path and a brief snippet of what changed, providing
        more context than just the file list in active_files.

        Returns:
            List of dicts with 'tool', 'file', 'snippet' keys.
        """
        if not self.transcript_path:
            return []
        edits: list[dict] = []
        with open(self.transcript_path, encoding="utf-8") as f:
            lines = f.readlines()
        recent = lines[-200:] if len(lines) > 200 else lines
        for line in recent:
            try:
                entry = json.loads(line)
                if entry.get("type") != "assistant":
                    continue
                msg = entry.get("message", {})
                content = msg.get("content", []) if isinstance(msg, dict) else []
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    tool = block.get("name", "")
                    inp = block.get("input", {})
                    if tool == "Edit":
                        file_path = inp.get("file_path", "")
                        new_str = inp.get("new_string", "")
                        snippet = new_str[:200].replace("\n", " ") if new_str else ""
                        if file_path:
                            edits.append({"tool": "Edit", "file": file_path, "snippet": snippet})
                    elif tool == "Write":
                        file_path = inp.get("file_path", "")
                        content_str = inp.get("content", "")
                        snippet = content_str[:200].replace("\n", " ") if content_str else ""
                        if file_path:
                            edits.append({"tool": "Write", "file": file_path, "snippet": snippet})
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.debug(f"[PreCompact] Skipping invalid checkpoint entry: {e}")
                continue
        return edits[-max_edits:]

    def _build_handoff_metadata(
        self,
        task_name: str,
        task_id: str,
        handoff_data: dict[str, Any],
        handoff_payload: dict[str, Any] | None = None,
        original_user_request: str = "",
        first_user_request: str = "",
    ) -> dict[str, Any]:
        """Build complete handoff metadata structure for task storage.

        Consolidates all handoff data into a single metadata dict.

        Args:
            task_name: Name of task
            task_id: Unique task identifier
            handoff_data: Basic handoff data (progress, blocker, next_steps)
            handoff_payload: Optional full handoff payload with handover/context
            original_user_request: The last user message from transcript
            first_user_request: The first user message from transcript

        Returns:
            Complete handoff metadata dict ready for task storage
        """
        # Import utility for DRY compliance
        from handoff.config import utcnow_iso

        # Extract implementation status
        impl_status = self._extract_implementation_status()

        # Extract new enrichment data from transcript
        todo_list = self._extract_todo_list()
        recent_errors = self._extract_recent_errors()
        recent_exchanges = self._extract_recent_exchanges()
        recent_edits = self._extract_recent_edits()

        # Extract first_user_request from transcript if not provided
        # Issue #7: Use TranscriptParser instead of raw line scanning (fixes 20-line limit bug)
        if not first_user_request and self.transcript_path:
            try:
                # Use the same logic as extract_last_user_message, but forward direction
                # This finds the FIRST user message, not the last
                entries = self.parser._get_parsed_entries()
                for entry in entries:
                    if entry.get("type") == "user":
                        msg_obj = entry.get("message", {})
                        content = msg_obj.get("content", "")
                        if isinstance(content, list):
                            for item in content:
                                if isinstance(item, str) and len(item.strip()) > 10:
                                    first_user_request = item.strip()
                                    break
                        elif isinstance(content, str) and len(content.strip()) > 10:
                            first_user_request = content.strip()

                        if first_user_request:
                            logger.debug(
                                f"[PreCompact] Extracted first_user_request from transcript: "
                                f"{first_user_request[:50]}..."
                            )
                            break
            except (OSError, UnicodeDecodeError) as e:
                logger.debug(f"[PreCompact] Could not extract first_user_request: {e}")

        # Build base handoff structure
        handoff_metadata = {
            "task_name": task_name,
            "task_type": "informal",
            "progress_percent": handoff_data.get("progress_pct", 0),
            "blocker": handoff_data.get("blocker"),
            "next_steps": "\n".join(handoff_data.get("next_steps", [])),
            "git_branch": self._get_git_branch(),
            "active_files": handoff_data.get("files_modified", []),
            "recent_tools": self._load_tool_sequence(),
            "transcript_path": str(self.transcript_path) if self.transcript_path else None,
            # NEW: Exact resume tracking for checkpoint recovery
            "transcript_offset": self.parser.get_transcript_offset(),
            "transcript_entry_count": self.parser.get_transcript_entry_count(),
            "handover": handoff_data.get("handover"),
            "open_conversation_context": handoff_payload.get("open_conversation_context")
            if handoff_payload
            else None,
            "visual_context": handoff_payload.get("visual_context") if handoff_payload else None,
            "resolved_issues": handoff_data.get("resolved_issues", []),
            "modifications": handoff_data.get("modifications", []),
            "pending_operations": handoff_data.get("pending_operations", []),
            "original_user_request": original_user_request,
            "first_user_request": first_user_request,
            "saved_at": utcnow_iso(),
            "version": 1,
            # Implementation status tracking
            "implementation_status": impl_status,
            # Enrichment: captured from transcript at compaction time
            "todo_list": todo_list,
            "recent_errors": recent_errors,
            "recent_exchanges": recent_exchanges,
            "recent_edits": recent_edits,
        }

        # Apply size limits (truncate if necessary)
        handoff_metadata = validate_handoff_size(handoff_metadata)

        # Compute checksum for data integrity
        checksum = compute_metadata_checksum(handoff_metadata)
        handoff_metadata["checksum"] = checksum

        return handoff_metadata

    def _get_git_branch(self) -> str | None:
        """Get current git branch name.

        Returns:
            Branch name or None if not in a git repository

        Security:
            - Validates project_root is a valid directory
            - Isolates git config to prevent malicious config injection
            - Uses timeout protection against hanging processes
        """
        try:
            project_root_resolved = Path(self.project_root).resolve()

            # Validate project_root exists and is a directory
            if not project_root_resolved.is_dir():
                return None

            # Isolate git config to prevent loading from untrusted directories
            isolated_env = {
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
            }

            result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True,
                cwd=str(project_root_resolved),
                timeout=5,
                env=isolated_env,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
        return None

    def _cleanup_old_handoffs(self) -> None:
        """Automatically clean up old handoff files based on retention policy.

        Implements COMP-001: Automatic cleanup during compaction.
        Deletes task files older than CLEANUP_DAYS (default 90 days).
        This runs on EVERY compaction, not just when --cleanup flag is used.
        """
        from handoff.config import cleanup_old_handoffs

        deleted_count = cleanup_old_handoffs(self.project_root)

        if deleted_count > 0:
            logger.info(f"[PreCompact] Auto-cleanup: Deleted {deleted_count} old handoff file(s)")

    def run(self) -> bool:
        """Execute full PreCompact handoff process.

        Returns:
            True if handoff process succeeded, False otherwise
        """
        # Import utility for DRY compliance
        from handoff.config import utcnow_iso

        logger.info("[PreCompact] Starting handoff capture...")

        # Step 1: Get task identity
        task_name = self.task_manager.get_current_task()
        if not task_name:
            # Generate checkpoint name using timestamp
            task_name = f"session_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
            task_id = f"task_{task_name}"
            logger.info(f"[PreCompact] Generated handoff task name: {task_name}")
        else:
            task_id = f"task_{task_name.lower()}"
            logger.info(f"[PreCompact] Using task name: {task_name}")

        # Validate session ownership before creating handoff
        # This prevents wasted I/O creating handoffs that will be rejected
        # by SessionStart due to session mismatch
        current_session_file = self.project_root / ".claude" / "current_session.json"
        current_session = ""

        if current_session_file.exists():
            try:
                with open(current_session_file, encoding="utf-8") as f:
                    current_session_data = json.load(f)
                current_session = current_session_data.get("session_id", "")
            except (json.JSONDecodeError, OSError):
                current_session = ""

        # Extract handoff session from transcript path
        handoff_session = Path(self.transcript_path).stem if self.transcript_path else ""

        # Edge case: No current session (allow handoff creation)
        if not current_session:
            logger.info("[PreCompact] ⚠️  No current session - creating handoff without validation")
        else:
            # Validate session ownership
            if handoff_session != current_session:
                logger.info(f"[PreCompact] ⊘ Skipping handoff: '{task_name}' from stale session")
                logger.info(f"  Handoff session: {handoff_session}")
                logger.info(f"  Current session: {current_session}")
                logger.info("  Action: Preventing wasted I/O on cross-session handoff")
                # Skip handoff creation - return early with success
                return True

            logger.info(f"[PreCompact] ✓ Session validated: '{task_name}' belongs to current session")

        # Step 2: Extract handoff data using focused components
        progress_pct = self.extract_progress_percentage(task_name)
        blocker = self.parser.extract_current_blocker()
        files_modified = self.extract_modified_files()
        next_steps = self.extract_next_steps(task_name)
        handover = self.handover_builder.build(task_name)
        modifications = self.parser.extract_modifications()
        open_conversation_context = self.parser.extract_open_conversation_context()
        visual_context = self.parser.extract_visual_context()

        logger.info(f"[PreCompact] Progress: {progress_pct}%")

        # Extract and log implementation status
        impl_status = self._extract_implementation_status()
        if impl_status.get("completion_state") != "unknown":
            logger.info(f"[PreCompact] Completion state: {impl_status['completion_state']}")
        if impl_status.get("test_results"):
            test_res = impl_status["test_results"]
            logger.info(
                f"[PreCompact] Test results: {test_res.get('passed', 0)} passed, "
                f"{test_res.get('failed', 0)} failed"
            )

        if blocker:
            logger.info(f"[PreCompact] Blocker: {blocker.get('description', 'Unknown')}")

        if visual_context:
            logger.info(
                f"[PreCompact] Visual context: {visual_context.get('description', 'Unknown')[:80]}..."
            )

        # Extract pending operations for fault tolerance
        pending_operations = self.parser.extract_pending_operations()
        if pending_operations:
            logger.info(f"[PreCompact] Pending operations: {len(pending_operations)} found")

        # Step 3: Build handoff data
        handoff_data = self.handoff_store.build_handoff_data(
            task_name=task_name,
            progress_pct=progress_pct,
            blocker=blocker,
            files_modified=files_modified,
            next_steps=next_steps,
            handover=handover,
            modifications=modifications,
            pending_operations=pending_operations,
        )

        # Step 4: Save handoff
        handoff_saved = False
        try:
            # Build handoff payload for file storage
            blocker_raw = handoff_data.get("blocker")
            blocker_description = None  # String version for payload, NOT for extraction
            if blocker_raw:
                if isinstance(blocker_raw, dict):
                    blocker_description = blocker_raw.get("description", str(blocker_raw))
                else:
                    blocker_description = str(blocker_raw)
            else:
                blocker_description = None

            # Build command context from active_command.json if exists
            command_context_data = None
            active_cmd_file = self.project_root / ".claude" / "active_command.json"
            if active_cmd_file.exists():
                from handoff.config import load_json_file

                cmd_data = load_json_file(active_cmd_file)
                if cmd_data:
                    command_context_data = {
                        "command": cmd_data.get("command"),
                        "phase": cmd_data.get("phase"),
                        "started_at": cmd_data.get("started_at"),
                        "metadata": cmd_data.get("metadata", {}),
                    }

            # Build handoff data payload for file storage
            handoff_payload = {
                "task_name": task_name,
                "task_type": "formal" if os.getenv("CLAUDE_CODE_TASK_NAME") else "adhoc_session",
                "terminal_id": self.terminal_id,
                "progress_percent": handoff_data["progress_pct"],
                "blocker": blocker_description,
                "next_steps": "\n".join(handoff_data.get("next_steps", [])),
                "command_context": command_context_data,
                "git_branch": handoff_data.get("git_branch"),
                "active_files": handoff_data.get("files_modified", []),
                "recent_tools": self._load_tool_sequence(),
                "dependencies": [],
                "transcript_path": self.transcript_path,
                "handover": handoff_data.get("handover"),
                "open_conversation_context": open_conversation_context,
                "visual_context": visual_context,
                "saved_at": utcnow_iso(),
            }
            # Compute checksum over the payload itself (excluding checksum key)
            import hashlib as _hashlib
            import json as _json

            _payload_bytes = _json.dumps(handoff_payload, sort_keys=True, default=str).encode(
                "utf-8"
            )
            handoff_payload["checksum"] = f"sha256:{_hashlib.sha256(_payload_bytes).hexdigest()}"

            # Store handoff in task metadata
            handoff_saved = True
            logger.info(f"[PreCompact] Handoff stored (terminal: {self.terminal_id})")

        except Exception as e:
            logger.info(f"[PreCompact] Warning: Handoff storage failed: {e}")
            handoff_saved = False

        # Step 5: Create continue_session task with full handoff in metadata
        if handoff_saved:
            try:
                # Get last user message for handoff metadata
                # Priority: 1) TranscriptParser (source of truth), 2) hook_input,
                # 3) active_command file, 4) blocker.description
                last_user_message = ""

                # Option 1: TranscriptParser - scans the ACTUAL transcript (PRIORITY 1 - most reliable)
                transcript_unavailable = False
                if self.transcript_path:
                    # Use the TranscriptParser's extract_last_user_message() which scans
                    # the ENTIRE parsed transcript, not just last 20 raw lines
                    last_user_message = self.parser.extract_last_user_message()
                    if last_user_message:
                        logger.info(
                            f"[PreCompact] Using last_user_message from TranscriptParser: "
                            f"{last_user_message[:50]}..."
                        )
                    else:
                        # Check if transcript is missing or empty (Issue #2, #3)
                        transcript_path = Path(self.transcript_path)
                        if not transcript_path.exists():
                            logger.warning("[PreCompact] WARNING: Transcript file missing - cannot capture authentic context")
                            transcript_unavailable = True
                        else:
                            # File exists but no user messages found (empty transcript or system-only)
                            try:
                                file_size = transcript_path.stat().st_size
                                if file_size == 0:
                                    logger.warning("[PreCompact] WARNING: Transcript file is empty - skipping handoff capture")
                                    transcript_unavailable = True
                                else:
                                    # File has content but no user messages - system-only transcript
                                    logger.warning("[PreCompact] WARNING: Transcript has no user messages - skipping handoff capture to avoid stale data")
                                    transcript_unavailable = True
                            except OSError:
                                logger.warning("[PreCompact] WARNING: Could not read transcript - skipping handoff capture")
                                transcript_unavailable = True
                else:
                    logger.warning("[PreCompact] WARNING: No transcript path available - skipping handoff capture")
                    transcript_unavailable = True

                # Issue #2 & #3: If transcript is unavailable, skip handoff capture
                # Don't fall back to potentially stale hook_input/active_command/blocker
                if transcript_unavailable:
                    logger.info("[PreCompact] Handoff capture skipped - transcript required for authentic context")
                    return True  # Continue with compaction, but don't create handoff

                # Option 2: Read from hook_input if available (fallback, less reliable)
                if not last_user_message:
                    handoff_input_data = self.hook_input.get("handoff_data") or self.hook_input
                    if isinstance(handoff_input_data, dict):
                        input_message = handoff_input_data.get(
                            "last_user_message", ""
                        ) or handoff_input_data.get("prompt", "")
                        if input_message:
                            last_user_message = input_message
                            logger.info(
                                f"[PreCompact] Using last_user_message from hook_input: "
                                f"{last_user_message[:50]}..."
                            )

                # Option 3: Load from active_command file (can be stale)
                if not last_user_message:
                    last_user_message = self._load_active_command_file()
                    if last_user_message:
                        logger.info(
                            f"[PreCompact] Using last_user_message from active_command file: "
                            f"{last_user_message[:50]}..."
                        )

                # Option 4: Use blocker.description (can be from earlier, fallback only)
                if not last_user_message:
                    last_user_message = transcript.extract_user_message_from_blocker(blocker)
                    if last_user_message:
                        logger.info(
                            f"[PreCompact] Using last_user_message from blocker: "
                            f"{last_user_message[:50]}..."
                        )

                # Build full handoff metadata for task storage
                handoff_metadata = self._build_handoff_metadata(
                    task_name, task_id, handoff_data, handoff_payload, last_user_message
                )
                self.handoff_store.create_continue_session_task(
                    task_name, task_id, handoff_metadata
                )
            except Exception as e:
                logger.info(f"[PreCompact] Warning: Failed to create continue_session task: {e}")

        logger.info("[PreCompact] Handoff complete. Ready for compaction.")

        # Step 6: Automatic cleanup of old handoffs (COMP-001)
        # This runs on every compaction, not just with --cleanup flag
        self._cleanup_old_handoffs()

        return True


@hook_main
def main() -> int:
    """Execute PreCompact handoff capture."""
    try:
        # Read hook input from stdin or HANDOFF_INPUT env var
        # Env var is used by subprocess mode to avoid stdin timeout issues
        input_text = sys.stdin.read().strip()
        if not input_text:
            # Fallback to environment variable (used by router subprocess mode)
            input_text = os.environ.get("HANDOFF_INPUT", "").strip()

        hook_input = {}
        if input_text:
            try:
                hook_input = json.loads(input_text)
            except json.JSONDecodeError:
                pass  # Empty or invalid input, continue with empty dict

        handoff_process = PreCompactHandoffCapture(hook_input=hook_input)
        success = handoff_process.run()
        return 0 if success else 1
    except Exception as e:
        logger.info(f"[PreCompact] ERROR: {e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

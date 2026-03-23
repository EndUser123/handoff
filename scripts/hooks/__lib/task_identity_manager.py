"""Task Identity Manager - terminal-scoped task recovery after compaction.

State authority is terminal-local only:
1. Terminal-scoped active command file
2. Terminal-scoped environment variable
3. Terminal-scoped session file
4. Terminal-scoped compact metadata

Global env vars, worktree mappings, and shared command files are intentionally
ignored so one terminal cannot inherit another terminal's task identity.
"""

from __future__ import annotations

import hashlib
import logging
import os

import sys
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeAlias

_hooks_project_root = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
claude_root = _hooks_project_root.parent
hooks_dir = claude_root / ".claude" / "hooks"
if str(hooks_dir) not in sys.path:
    sys.path.insert(0, str(hooks_dir))

# Type aliases
TaskMetadataDict: TypeAlias = dict[str, str]

# Import terminal detection for multi-terminal isolation
from scripts.hooks.__lib.terminal_detection import (
    detect_terminal_id,  # type: ignore[import-untyped]
)

# Import utility functions

logger = logging.getLogger(__name__)

# Constants
COMPACT_METADATA_FRESHNESS_SECONDS = 300  # 5 minutes
DEFAULT_CLEANUP_MAX_AGE_HOURS = 24
SECONDS_PER_HOUR = 3600


@dataclass(slots=True)
class TaskMetadata:
    """Task identity metadata."""

    task_name: str
    task_id: str
    started: str
    checksum: str
    source: str  # Where this came from (env_var, session_file, etc.)


class TaskIdentityManager:
    """Manage task identity across compaction events with terminal-aware isolation."""

    def __init__(
        self, project_root: Path | None = None, terminal_id: str | None = None
    ) -> None:
        """
        Initialize task identity manager.

        Args:
            project_root: Root directory of project (defaults to CWD)
            terminal_id: Terminal identifier for isolation (auto-detected if None)
        """
        self.project_root = Path(project_root) if project_root else Path.cwd()
        detected_terminal_id = (
            terminal_id if terminal_id is not None else detect_terminal_id()
        )
        self.terminal_id = (
            detected_terminal_id.strip()
            if isinstance(detected_terminal_id, str)
            else ""
        )
        self.stateful_enabled = bool(self.terminal_id)

        # Terminal-scoped file paths to prevent task bleeding between terminals
        # Use absolute path to claude_root/.claude to ensure consistency across package locations
        self.state_base = self.project_root / ".claude" / "state" / "task-identity"
        self.session_file = (
            self.state_base / f"session-task-{self.terminal_id}.json"
            if self.stateful_enabled
            else None
        )
        self.metadata_file = (
            self.state_base / f"last-compact-metadata-{self.terminal_id}.json"
            if self.stateful_enabled
            else None
        )
        self.active_command_file = (
            self.state_base / f"active-command-{self.terminal_id}.json"
            if self.stateful_enabled
            else None
        )
        if not self.stateful_enabled:
            logger.warning(
                "[TaskID] Terminal ID unavailable; terminal-scoped task recovery disabled"
            )

    def _require_stateful_terminal(self) -> bool:
        """Return True when terminal-scoped state is safe to use."""
        if self.stateful_enabled:
            return True
        logger.warning(
            "[TaskID] Skipping stateful task recovery because terminal ID is unavailable"
        )
        return False

    @staticmethod
    def _is_metadata_fresh(
        timestamp_str: str, max_age_seconds: int = COMPACT_METADATA_FRESHNESS_SECONDS
    ) -> bool:
        """Check if compact metadata timestamp is fresh enough to use.

        Args:
            timestamp_str: ISO format timestamp string
            max_age_seconds: Maximum age in seconds (default: COMPACT_METADATA_FRESHNESS_SECONDS)

        Returns:
            True if timestamp is fresh enough, False otherwise
        """
        if not timestamp_str:
            return False

        try:
            timestamp = datetime.fromisoformat(timestamp_str)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=UTC)
            age = (datetime.now(UTC) - timestamp).total_seconds()
            return age < max_age_seconds
        except (ValueError, OSError):
            return False

    def get_current_task(self) -> str | None:
        """
        Get current task using terminal-scoped recovery only.

        Priority order:
        1. Ad-hoc command (active-command-{terminal_id}.json)
        2. Environment variable (TASK_NAME_{terminal_id})
        3. Session file (session-task-{terminal_id}.json)
        4. Compact metadata (last-compact-metadata-{terminal_id}.json)

        Returns:
            Task name (e.g., "CWO12") or None if not determinable
        """
        if not self._require_stateful_terminal():
            return None

        # Priority 0: Check for ad-hoc command first
        transient_task = self._get_transient_task_id()
        if transient_task:
            logger.info(f"[TaskID] Recovered: {transient_task} (source: adhoc_command)")
            return transient_task

        sources = [
            ("env_var", self._from_env_var),
            ("session_file", self._from_session_file),
            ("compact_metadata", self._from_compact_metadata),
        ]

        for source_name, method in sources:
            try:
                task = method()
                if task:
                    logger.info(f"[TaskID] Recovered: {task} (source: {source_name})")
                    return task
            except Exception as e:
                logger.warning(f"[TaskID] Warning from {source_name}: {e}")

        # Last resort: ask user
        return self._ask_user()

    def _is_valid_task_name(self, task_name: str | None) -> bool:
        """
        Validate task name format.

        Returns False for None, empty strings, whitespace-only, or dangerous characters.
        """
        if not task_name or not isinstance(task_name, str):
            return False

        # Reject whitespace-only task names
        if not task_name.strip():
            return False

        # Reject dangerous characters (path separators, control characters)
        dangerous_chars = ["/", "\\", "\n", "\r", "\t", "\0"]
        if any(char in task_name for char in dangerous_chars):
            return False

        return True

    def _from_env_var(self) -> str | None:
        """Get task from the terminal-scoped environment variable only."""
        if not self.stateful_enabled:
            return None
        env_var_name = f"TASK_NAME_{self.terminal_id}"
        task = os.getenv(env_var_name)
        if task:
            return task
        return None

    def _from_session_file(self) -> str | None:
        """Read task from terminal-scoped session file with terminal_id verification."""
        if not self.session_file:
            return None
        from scripts.config import load_json_file

        data = load_json_file(self.session_file)
        if data:
            # VERIFY: Terminal ID matches before accepting (prevents cross-terminal bleeding)
            file_terminal = data.get("terminal_id")
            if file_terminal and file_terminal != self.terminal_id:
                logger.warning(
                    f"[TaskID] Terminal mismatch in session file: {file_terminal} != {self.terminal_id}"
                )
                return None

            return data.get("task_name")
        return None

    def _from_compact_metadata(self) -> str | None:
        """Read task from terminal-scoped compact metadata (last-compact-metadata-{terminal_id}.json)."""
        if not self.metadata_file:
            return None
        from scripts.config import load_json_file

        data = load_json_file(self.metadata_file)
        if data:
            task: str | None = data.get("task_name")
            if task:
                # Verify metadata is recent (within 5 minutes)
                timestamp_str = data.get("timestamp", "")
                if self._is_metadata_fresh(timestamp_str):
                    return task
        return None

    def _ask_user(self) -> str | None:
        """Ask user to select task (last resort).

        CKS integration removed - returns None to force manual task setting.
        User can set task via: export TASK_NAME_{terminal_id}=your_task
        """
        # CKS adapter no longer available after handoff system simplification
        # Return None to force explicit task setting
        logger.debug("[TaskID] Last resort fallback: No task determinable")
        return None

    def set_current_task(self, task_name: str) -> bool:
        """
        Set current task and persist to session file.

        Args:
            task_name: Task identifier (e.g., "CWO12")

        Returns:
            True if successful
        """
        if not self._require_stateful_terminal():
            return False

        # Input validation
        if not self._is_valid_task_name(task_name):
            return False

        try:
            from scripts.config import save_json_file, utcnow_iso

            # Set terminal-scoped environment variable (prevents cross-terminal bleeding)
            env_var_name = f"TASK_NAME_{self.terminal_id}"
            os.environ[env_var_name] = task_name

            # Write session file with terminal_id for verification
            session_data = {
                "task_name": task_name,
                "task_id": f"task_{task_name.lower()}",
                "terminal_id": self.terminal_id,
                "started": utcnow_iso(),
                "checksum": hashlib.md5(task_name.encode()).hexdigest(),
            }

            save_json_file(self.session_file, session_data)

            logger.info(f"[TaskID] Set current task: {task_name}")
            return True

        except Exception as e:
            logger.error(f"[TaskID] Error setting task: {e}")
            return False

    def store_compact_metadata(self, task_name: str, handoff_id: str) -> bool:
        """
        Store task identity in compact metadata (for PostCompact recovery).

        Called by PreCompact hook before compaction.

        Args:
            task_name: Task being compacted
            handoff_id: Handoff ID just captured

        Returns:
            True if successful
        """
        if not self._require_stateful_terminal():
            return False

        # Input validation
        if not self._is_valid_task_name(task_name):
            return False
        if not handoff_id or not isinstance(handoff_id, str):
            return False

        try:
            from scripts.config import save_json_file, utcnow_iso

            metadata = {
                "task_name": task_name,
                "task_id": f"task_{task_name.lower()}",
                "handoff_id": handoff_id,
                "timestamp": utcnow_iso(),
                "version": "v1",
            }

            save_json_file(self.metadata_file, metadata)

            logger.info(f"[TaskID] Stored compact metadata: {task_name}")
            return True

        except Exception as e:
            logger.error(f"[TaskID] Error storing metadata: {e}")
            return False

    def register_task_worktree_mapping(self, task_name: str, branch: str) -> bool:
        """Legacy no-op: worktree mappings are disabled to prevent cross-terminal bleed."""
        del task_name, branch
        logger.info(
            "[TaskID] Ignoring worktree mapping registration; shared mappings are disabled"
        )
        return True

    def record_active_command(
        self, command: str, phase: str, metadata: dict[str, object] | None = None
    ) -> bool:
        """
        Record active ad-hoc command for handoff recovery.

        Writes to .claude/state/task-identity/active-command-{terminal_id}.json
        for tracking commands like /duf, /v, /search.

        Args:
            command: Command name (e.g., "duf", "v", "search")
            phase: Current phase (e.g., "pre_mortem", "execution")
            metadata: Optional additional context

        Returns:
            True if successful
        """
        if not self._require_stateful_terminal() or not self.active_command_file:
            return False

        # Input validation
        if not command or not isinstance(command, str):
            return False
        if not phase or not isinstance(phase, str):
            return False

        try:
            from scripts.config import save_json_file, utcnow_iso

            command_data = {
                "command": command,
                "phase": phase,
                "started_at": utcnow_iso(),
                "metadata": metadata or {},
                "terminal_id": self.terminal_id,
            }

            save_json_file(self.active_command_file, command_data)
            logger.info(f"[TaskID] Recorded active command: {command} (phase: {phase})")
            return True

        except Exception as e:
            logger.error(f"[TaskID] Error recording active command: {e}")
            return False

    def clear_active_command(self) -> bool:
        """
        Clear active command record after completion.

        Returns:
            True if file was deleted, False if didn't exist or error
        """
        if not self._require_stateful_terminal() or not self.active_command_file:
            return False

        try:
            if self.active_command_file.exists():
                self.active_command_file.unlink()
                logger.info("[TaskID] Cleared active command")
                return True
            return False

        except Exception as e:
            logger.error(f"[TaskID] Error clearing active command: {e}")
            return False

    def _get_transient_task_id(self) -> str | None:
        """
        Get transient task ID for ad-hoc commands.

        Returns 'adhoc_{command}' if an active command is recorded.

        Returns:
            Transient task ID or None
        """
        if not self.active_command_file:
            return None
        try:
            from scripts.config import load_json_file

            data = load_json_file(self.active_command_file)
            if data:
                file_terminal = data.get("terminal_id")
                if file_terminal and file_terminal != self.terminal_id:
                    logger.warning(
                        f"[TaskID] Terminal mismatch in active command file: {file_terminal} != {self.terminal_id}"
                    )
                    return None
                command = data.get("command")
                if command:
                    return f"adhoc_{command}"
        except Exception as e:
            logger.debug(f"[TaskID] Failed to get transient task ID: {e}")

        return None

    def cleanup_stale_terminal_files(
        self, max_age_hours: int = DEFAULT_CLEANUP_MAX_AGE_HOURS
    ) -> int:
        """
        Delete orphaned session files older than max_age_hours.

        Called on startup to prevent accumulation of stale terminal state.

        Args:
            max_age_hours: Maximum age in hours (default: DEFAULT_CLEANUP_MAX_AGE_HOURS)

        Returns:
            Number of files deleted
        """
        deleted = 0
        cutoff = datetime.now().timestamp() - (max_age_hours * SECONDS_PER_HOUR)

        try:
            if not self.state_base.exists():
                return 0

            for session_file in self.state_base.glob("session-task-*.json"):
                with suppress(OSError):
                    # Check file age
                    mtime = session_file.stat().st_mtime
                    if mtime < cutoff:
                        session_file.unlink()
                        deleted += 1
                        logger.debug(
                            f"[TaskID] Deleted stale session file: {session_file.name}"
                        )

            # Also clean up old compact metadata files
            for metadata_file in self.state_base.glob("last-compact-metadata-*.json"):
                with suppress(OSError):
                    mtime = metadata_file.stat().st_mtime
                    if mtime < cutoff:
                        metadata_file.unlink()
                        deleted += 1
                        logger.debug(
                            f"[TaskID] Deleted stale metadata file: {metadata_file.name}"
                        )

            for active_command_file in self.state_base.glob("active-command-*.json"):
                with suppress(OSError):
                    mtime = active_command_file.stat().st_mtime
                    if mtime < cutoff:
                        active_command_file.unlink()
                        deleted += 1
                        logger.debug(
                            f"[TaskID] Deleted stale active command file: {active_command_file.name}"
                        )

        except OSError as e:
            logger.error(f"[TaskID] Error during cleanup: {e}")

        if deleted > 0:
            logger.info(f"[TaskID] Cleanup: {deleted} stale file(s) deleted")

        return deleted


if __name__ == "__main__":
    # Test the manager
    manager = TaskIdentityManager()

    logger.info("Testing Task Identity Manager")
    logger.info("=" * 50)

    # Test: Get current task
    task = manager.get_current_task()
    logger.info(f"Current task: {task}")

    # Test: Set task
    if task:
        logger.info(f"\nTask '{task}' recovered from source")
    else:
        logger.info("\nNo task found - would prompt user")

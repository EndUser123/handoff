"""Task Identity Manager - Recover task identity after compaction.

Implements 5-source resilience chain for task identification:
1. Environment variable (TASK_NAME)
2. Session file (.claude/session-task-{terminal_id}.json)
3. Compact metadata (.claude/.last-compact-metadata-{terminal_id}.json)
4. Git worktree mapping (.claude/task-worktree-mapping.json)
5. User confirmation (CKS query + user input)

This ensures task identity is ALWAYS recoverable, even after
environment variables are cleared on compaction.

Terminal-aware: Each terminal maintains its own task state to prevent
task bleeding between concurrent terminal sessions.

Constitutional Requirements:
- Solo developer optimization (automatic recovery, no manual setup)
- Evidence-based implementation (proven multi-source fallback pattern)
- Force multiplier (never lose task identity)
- No enterprise bloat (direct file I/O, no complex infrastructure)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess

# For package-based hooks, add P:/.claude/hooks to path for terminal_detection import
# Path: P:/packages/handoff/src/handoff/hooks/__lib/task_identity_manager.py
# Need to reach: P:/.claude/hooks/terminal_detection.py
import sys
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeAlias

_hooks_project_root = (
    Path(__file__).resolve().parent.parent.parent.parent.parent.parent
)  # Up to packages/handoff
claude_root = _hooks_project_root.parent  # Up to P:/
hooks_dir = claude_root / ".claude" / "hooks"
if str(hooks_dir) not in sys.path:
    sys.path.insert(0, str(hooks_dir))

# Type aliases
TaskMetadataDict: TypeAlias = dict[str, str]

# Import terminal detection for multi-terminal isolation
from terminal_detection import detect_terminal_id

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

    def __init__(self, project_root: Path | None = None, terminal_id: str | None = None) -> None:
        """
        Initialize task identity manager.

        Args:
            project_root: Root directory of project (defaults to CWD)
            terminal_id: Terminal identifier for isolation (auto-detected if None)
        """
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.terminal_id = terminal_id if terminal_id else detect_terminal_id()

        # Terminal-scoped file paths to prevent task bleeding between terminals
        # Use absolute path to P:/.claude to ensure consistency across package locations
        state_base = Path("P:/.claude/state/task-identity")
        self.session_file = state_base / f"session-task-{self.terminal_id}.json"
        self.metadata_file = state_base / f"last-compact-metadata-{self.terminal_id}.json"
        self.mapping_file = state_base / "task-worktree-mapping.json"  # Global, not terminal-scoped

    def get_current_task(self) -> str | None:
        """
        Get current task using 6-source resilience chain.

        Priority order:
        1. Ad-hoc command (active_command.json)
        2. Environment variable (TASK_NAME)
        3. Session file (session-task-{terminal_id}.json)
        4. Compact metadata (last-compact-metadata-{terminal_id}.json)
        5. Git worktree mapping
        6. User prompt

        Returns:
            Task name (e.g., "CWO12") or None if not determinable
        """
        # Priority 0: Check for ad-hoc command first
        transient_task = self._get_transient_task_id()
        if transient_task:
            logger.info(f"[TaskID] Recovered: {transient_task} (source: adhoc_command)")
            return transient_task

        sources = [
            ("env_var", self._from_env_var),
            ("session_file", self._from_session_file),
            ("compact_metadata", self._from_compact_metadata),
            ("git_worktree", self._from_git_worktree),
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
        """Get task from environment variable.

        Priority:
        1. Terminal-scoped: TASK_NAME_{terminal_id} (prevents cross-terminal bleeding)
        2. Legacy global: TASK_NAME (backward compatibility)
        """
        # First try terminal-scoped env var (prevents cross-terminal bleeding)
        env_var_name = f"TASK_NAME_{self.terminal_id}"
        task = os.getenv(env_var_name)
        if task:
            return task

        # Fall back to legacy global env var (backward compatibility)
        return os.getenv("TASK_NAME")

    def _from_session_file(self) -> str | None:
        """Read task from terminal-scoped session file with terminal_id verification."""
        from handoff.config import load_json_file

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
        from handoff.config import load_json_file

        data = load_json_file(self.metadata_file)
        if data:
            task = data.get("task_name")
            if task:
                # Verify metadata is recent (within 5 minutes)
                timestamp_str = data.get("timestamp", "")
                if timestamp_str:
                    timestamp = datetime.fromisoformat(timestamp_str)
                    if timestamp.tzinfo is None:
                        timestamp = timestamp.replace(tzinfo=UTC)
                    age = (datetime.now(UTC) - timestamp).total_seconds()
                    if age < COMPACT_METADATA_FRESHNESS_SECONDS:  # 5 minutes
                        return task
        return None

    def _from_git_worktree(self) -> str | None:
        """Infer task from current git branch using mapping."""
        try:
            # Get current branch (use getattr for CREATE_NO_WINDOW in case it doesn't exist)
            import sys

            creation_flags = (
                getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
            )
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=5,
                creationflags=creation_flags,
            )

            branch = result.stdout.strip()
            if not branch:
                return None

            # Load task-worktree mapping
            from handoff.config import load_json_file

            mapping_data = load_json_file(self.mapping_file)
            if mapping_data:
                return mapping_data.get(branch)

        except subprocess.TimeoutExpired:
            logger.warning("[TaskID] Git command timed out")
        except subprocess.CalledProcessError:
            logger.warning("[TaskID] Git command failed")
        except FileNotFoundError:
            logger.warning("[TaskID] Git not found")
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"[TaskID] Error inferring from features.git: {e}")

        return None

    def _ask_user(self) -> str | None:
        """Ask user to select task (last resort).

        CKS integration removed - returns None to force manual task setting.
        User can set task via: export TASK_NAME=your_task
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
        # Input validation
        if not self._is_valid_task_name(task_name):
            return False

        try:
            from handoff.config import save_json_file, utcnow_iso

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
        # Input validation
        if not self._is_valid_task_name(task_name):
            return False
        if not handoff_id or not isinstance(handoff_id, str):
            return False

        try:
            from handoff.config import save_json_file, utcnow_iso

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
        """
        Register mapping from features.git branch to task.

        Called when task starts or when git branch changes.

        Args:
            task_name: Task identifier
            branch: Git branch name

        Returns:
            True if successful
        """
        # Input validation
        if not self._is_valid_task_name(task_name):
            return False
        if not branch or not isinstance(branch, str):
            return False

        try:
            # Load existing mapping
            from handoff.config import load_json_file

            mapping = load_json_file(self.mapping_file)
            if not mapping:
                mapping = {}

            # Add new mapping
            mapping[branch] = task_name

            # Save
            from handoff.config import save_json_file

            save_json_file(self.mapping_file, mapping)

            logger.info(f"[TaskID] Registered: {branch} -> {task_name}")
            return True

        except Exception as e:
            logger.error(f"[TaskID] Error registering mapping: {e}")
            return False

    def record_active_command(self, command: str, phase: str, metadata: dict | None = None) -> bool:
        """
        Record active ad-hoc command for handoff recovery.

        Writes to .claude/active_command.json for tracking commands like /duf, /v, /search.

        Args:
            command: Command name (e.g., "duf", "v", "search")
            phase: Current phase (e.g., "pre_mortem", "execution")
            metadata: Optional additional context

        Returns:
            True if successful
        """
        # Input validation
        if not command or not isinstance(command, str):
            return False
        if not phase or not isinstance(phase, str):
            return False

        try:
            from handoff.config import save_json_file, utcnow_iso

            active_cmd_file = self.project_root / ".claude" / "active_command.json"

            command_data = {
                "command": command,
                "phase": phase,
                "started_at": utcnow_iso(),
                "metadata": metadata or {},
                "terminal_id": self.terminal_id,
            }

            save_json_file(active_cmd_file, command_data)
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
        try:
            active_cmd_file = self.project_root / ".claude" / "active_command.json"
            if active_cmd_file.exists():
                active_cmd_file.unlink()
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
        try:
            from handoff.config import load_json_file

            active_cmd_file = self.project_root / ".claude" / "active_command.json"
            data = load_json_file(active_cmd_file)
            if data:
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
            state_base = Path("P:/.claude/state/task-identity")
            if not state_base.exists():
                return 0

            for session_file in state_base.glob("session-task-*.json"):
                with suppress(OSError):
                    # Check file age
                    mtime = session_file.stat().st_mtime
                    if mtime < cutoff:
                        session_file.unlink()
                        deleted += 1
                        logger.debug(f"[TaskID] Deleted stale session file: {session_file.name}")

            # Also clean up old compact metadata files
            for metadata_file in state_base.glob("last-compact-metadata-*.json"):
                with suppress(OSError):
                    mtime = metadata_file.stat().st_mtime
                    if mtime < cutoff:
                        metadata_file.unlink()
                        deleted += 1
                        logger.debug(f"[TaskID] Deleted stale metadata file: {metadata_file.name}")

        except OSError as e:
            logger.error(f"[TaskID] Error during cleanup: {e}")

        if deleted > 0:
            logger.info(f"[TaskID] Cleanup: {deleted} stale file(s) deleted")

        return deleted


if __name__ == "__main__":
    # Test the manager
    manager = TaskIdentityManager()

    print("Testing Task Identity Manager")
    print("=" * 50)

    # Test: Get current task
    task = manager.get_current_task()
    print(f"Current task: {task}")

    # Test: Set task
    if task:
        print(f"\nTask '{task}' recovered from source")
    else:
        print("\nNo task found - would prompt user")

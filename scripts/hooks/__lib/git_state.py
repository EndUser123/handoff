#!/usr/bin/env python3
"""Git repository state capture for handoff system.

This module provides terminal-isolation-safe git state capture,
extracting branch, uncommitted changes, and last commit information.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Timeout for git operations (seconds)
GIT_TIMEOUT = 2


def capture_git_state(project_root: str) -> dict | None:
    """Capture git repository state.

    Extracts:
    - Current branch name
    - Whether there are uncommitted changes
    - Last commit (hash, message, timestamp)

    Args:
        project_root: Path to project directory (must exist and be accessible)

    Returns:
        Dict with git state or None if:
        - Not a git repository
        - Git operations fail or timeout
        - Path is invalid

    Example:
        >>> state = capture_git_state("/path/to/project")
        >>> if state:
        ...     print(f"Branch: {state['branch']}")
        ...     print(f"Has changes: {state['has_uncommitted_changes']}")
    """
    # Validate path before subprocess calls
    if not project_root:
        logger.warning("[GitState] No project root provided")
        return None

    project_path = Path(project_root)

    # Check if path exists and is accessible
    try:
        if not project_path.exists():
            logger.warning(f"[GitState] Path does not exist: {project_root}")
            return None

        if not project_path.is_dir():
            logger.warning(f"[GitState] Path is not a directory: {project_root}")
            return None

    except OSError as e:
        logger.warning(f"[GitState] Error accessing path {project_root}: {e}")
        return None

    # Check if this is a git repository
    git_dir = project_path / ".git"
    try:
        if not git_dir.exists():
            logger.info(f"[GitState] Not a git repository: {project_root}")
            return None
    except OSError:
        logger.warning(f"[GitState] Cannot access .git directory: {project_root}")
        return None

    # Capture git state with timeout
    try:
        branch = _get_current_branch(project_path)
        has_changes = _has_uncommitted_changes(project_path)
        last_commit = _get_last_commit(project_path)

        return {
            "branch": branch,
            "has_uncommitted_changes": has_changes,
            "last_commit": last_commit,
        }

    except subprocess.TimeoutExpired:
        logger.warning(f"[GitState] Git operation timeout in {project_root}")
        return None
    except subprocess.CalledProcessError as e:
        logger.warning(
            f"[GitState] Git command failed: {e.cmd} returned {e.returncode}"
        )
        return None
    except OSError as e:
        logger.warning(f"[GitState] OS error during git operations: {e}")
        return None
    except Exception as e:
        logger.warning(f"[GitState] Unexpected error capturing git state: {e}")
        return None


def _get_current_branch(project_path: Path) -> str:
    """Get current branch name.

    Returns:
        Branch name or "HEAD" if detached
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            check=True,
        )
        branch = result.stdout.strip()
        return branch if branch else "HEAD"
    except subprocess.CalledProcessError:
        # Fallback for older git versions
        try:
            result = subprocess.run(
                ["git", "symbolic-ref", "--short", "HEAD"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=GIT_TIMEOUT,
                check=False,
            )
            branch = result.stdout.strip()
            return branch if branch else "HEAD"
        except Exception:
            return "HEAD"


def _has_uncommitted_changes(project_path: Path) -> bool:
    """Check if repository has uncommitted changes.

    Returns:
        True if there are uncommitted changes, False otherwise
    """
    try:
        # Check for uncommitted changes (including staged and unstaged)
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            check=True,
        )
        # Any output means there are changes
        return bool(result.stdout.strip())
    except subprocess.CalledProcessError:
        return False


def _get_last_commit(project_path: Path) -> dict | None:
    """Get last commit information.

    Returns:
        Dict with 'hash', 'message', 'timestamp' or None
    """
    try:
        # Get commit hash
        hash_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            check=True,
        )
        commit_hash = hash_result.stdout.strip()[:8]  # Short hash

        # Get commit message
        message_result = subprocess.run(
            ["git", "log", "-1", "--pretty=%s"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            check=True,
        )
        message = message_result.stdout.strip()

        # Get commit timestamp
        timestamp_result = subprocess.run(
            ["git", "log", "-1", "--pretty=%ci"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            check=True,
        )
        timestamp = timestamp_result.stdout.strip()

        return {
            "hash": commit_hash,
            "message": message,
            "timestamp": timestamp,
        }

    except subprocess.CalledProcessError:
        return None

#!/usr/bin/env python3
"""Handoff storage module for session state persistence.

This module provides handoff storage functionality including:
- atomic_write_with_retry: Atomic file writes with Windows file locking handling
- atomic_write_with_validation: Atomic write with data size validation (QUAL-009)
- HandoffStore: Main class for handoff data management and storage

Note: Renamed from checkpoint_store.py to avoid Claude Code checkpoint naming conflict.
"""

from __future__ import annotations

import json
import logging
import os

# Platform-specific imports for file locking
import sys

if sys.platform == 'win32':
    import msvcrt
else:
    import fcntl

import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

# Import utility functions and constants
try:
    from handoff.config import (
        LOCK_CHECK_INTERVAL_SECONDS,
        LOCK_CHECKS_PER_SECOND,
        LOCK_TIMEOUT_SECONDS,
        MAX_RETRIES,
        RETRY_BASE_DELAY_SECONDS,
        STALE_LOCK_AGE_SECONDS,
        utcnow_iso,
    )
except ImportError:
    # Fallback for testing - constants must match config.py values
    from datetime import UTC, datetime

    LOCK_TIMEOUT_SECONDS = 5  # File lock acquisition timeout (seconds)
    MAX_RETRIES = 5  # Maximum retry attempts for atomic write operations
    RETRY_BASE_DELAY_SECONDS = 0.005  # Base delay for exponential backoff (5ms in seconds)
    LOCK_CHECK_INTERVAL_SECONDS = 0.1  # Interval between lock acquisition attempts (100ms in seconds)
    LOCK_CHECKS_PER_SECOND = 10  # Number of lock checks per second
    STALE_LOCK_AGE_SECONDS = 10  # Age after which a lock is considered stale (10 seconds)

    def utcnow_iso() -> str:
        return datetime.now(UTC).isoformat()


# Import bridge token utilities
try:
    from handoff.hooks.__lib.bridge_tokens import (
        BRIDGE_TOKEN_PREFIX,
        generate_bridge_token,
    )
except ImportError:
    # Fallback if bridge_tokens module not available
    def generate_bridge_token(topic: str, timestamp: str) -> str:
        """Fallback bridge token generator."""
        timestamp_str = datetime.fromisoformat(timestamp).strftime('%Y%m%d-%H%M%S')
        topic_str = topic[:20].upper().replace(' ', '_')
        return f"BRIDGE_{timestamp_str}_{topic_str}"

    BRIDGE_TOKEN_PREFIX = "BRIDGE_"

# Import utility functions

# Constants for continue_session task creation
CONTINUE_SESSION_TASK_ID = "continue_session"
CONTINUE_SESSION_SUBJECT_PREFIX = "Continue: "
CONTINUE_SESSION_STATUS_PENDING = "pending"
CONTINUE_SESSION_RESTORED_FROM = "compaction"
SUBJECT_MAX_LENGTH = 80

# Constants for size validation (QUAL-009)
MAX_HANDOFF_SIZE_BYTES = 500_000  # 500 KB
MAX_NEXT_STEPS_LENGTH = 10_000
MAX_ACTIVE_FILES = 100
MAX_MODIFICATIONS = 50
MAX_RECENT_TOOLS = 30
MAX_HANDOVER_DECISIONS = 10
MAX_HANDOVER_PATTERNS = 10

# Quality scoring weights (from /hod skill)
QUALITY_WEIGHT_COMPLETION = 0.30  # Completion tracking
QUALITY_WEIGHT_OUTCOMES = 0.25  # Action-outcome correlation
QUALITY_WEIGHT_DECISIONS = 0.20  # Decision documentation
QUALITY_WEIGHT_ISSUES = 0.15  # Issue resolution
QUALITY_WEIGHT_KNOWLEDGE = 0.10  # Knowledge contribution

# Quality score thresholds
QUALITY_SCORE_EXCELLENT = 0.90  # 0.9-1.0: Excellent
QUALITY_SCORE_GOOD = 0.70  # 0.7-0.8: Good
QUALITY_SCORE_ACCEPTABLE = 0.50  # 0.5-0.6: Acceptable


class FileLock:
    """Platform-specific atomic file locking context manager.

    This provides atomic file locking to prevent race conditions in file access.
    Uses platform-specific primitives:
    - Windows: msvcrt.locking() with LK_NBLCK (non-blocking lock)
    - Unix: fcntl.flock() with LOCK_EX | LOCK_NB (exclusive non-blocking lock)

    The lock is automatically released when exiting the context manager.
    """

    def __init__(self, lock_file_path: Path, timeout: float = LOCK_TIMEOUT_SECONDS, stale_age: float = STALE_LOCK_AGE_SECONDS):
        """Initialize file lock.

        Args:
            lock_file_path: Path to lock file
            timeout: Maximum seconds to wait for lock acquisition (from config.LOCK_TIMEOUT_SECONDS)
            stale_age: Seconds after which a lock is considered stale (from config.STALE_LOCK_AGE_SECONDS)
        """
        self.lock_file_path = lock_file_path
        self.timeout = timeout
        self.stale_age = stale_age
        self.lock_fd: int | None = None
        self._acquired = False

    def acquire(self) -> bool:
        """Acquire the file lock with retry logic.

        Returns:
            True if lock was acquired, False if timeout expired

        Raises:
            OSError: If lock file operations fail
        """
        start_time = time.time()
        retry_interval = LOCK_CHECK_INTERVAL_SECONDS

        while time.time() - start_time < self.timeout:
            try:
                # Open lock file (create if doesn't exist)
                flags = os.O_RDWR | os.O_CREAT
                self.lock_fd = os.open(self.lock_file_path, flags)

                # Try to acquire lock atomically
                if sys.platform == 'win32':
                    # Windows: msvcrt.locking() with LK_NBLCK (non-blocking)
                    # Lock mode: write lock (LK_LOCK) with non-blocking (LK_NBLCK)
                    try:
                        msvcrt.locking(self.lock_fd, msvcrt.LK_NBLCK, 1)
                        self._acquired = True
                        return True
                    except OSError:
                        # Lock is held by another process
                        os.close(self.lock_fd)
                        self.lock_fd = None
                else:
                    # Unix: fcntl.flock() with LOCK_EX | LOCK_NB
                    # LOCK_EX: Exclusive lock
                    # LOCK_NB: Non-blocking (don't wait)
                    try:
                        fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        self._acquired = True
                        return True
                    except OSError:
                        # Lock is held by another process
                        os.close(self.lock_fd)
                        self.lock_fd = None

                # Lock acquisition failed, check for stale lock
                self._check_and_remove_stale_lock()

                # Wait before retry
                time.sleep(retry_interval)

            except FileExistsError:
                # Lock file exists but we couldn't open it
                self._check_and_remove_stale_lock()
                time.sleep(retry_interval)
            except OSError:
                # Error during lock acquisition
                if self.lock_fd is not None:
                    try:
                        os.close(self.lock_fd)
                    except OSError:
                        pass
                    self.lock_fd = None
                raise

        # Timeout expired
        logger.warning(
            f"[FileLock] Could not acquire lock {self.lock_file_path.name} "
            f"after {self.timeout:.1f}s"
        )
        return False

    def _check_and_remove_stale_lock(self) -> None:
        """Check if lock file is stale and remove it if so.

        A lock is considered stale if it's older than stale_age seconds.
        This handles cases where a process crashed while holding the lock.
        """
        try:
            if self.lock_file_path.exists():
                lock_stat = os.stat(self.lock_file_path)
                lock_age = time.time() - lock_stat.st_mtime
                if lock_age > self.stale_age:
                    # Stale lock found, remove it
                    os.unlink(self.lock_file_path)
                    logger.warning(
                        f"[FileLock] Removed stale lock file: {self.lock_file_path.name} "
                        f"(age: {lock_age:.1f}s)"
                    )
        except OSError as e:
            # Best effort - don't fail if we can't check/remove stale lock
            logger.debug(f"[FileLock] Could not check stale lock: {e}")

    def release(self) -> None:
        """Release the file lock and clean up lock file.

        This is safe to call even if lock wasn't acquired.
        """
        if self.lock_fd is not None:
            try:
                # Release the platform-specific lock
                if sys.platform == 'win32':
                    # Windows: msvcrt.locking() with LK_UNLCK
                    msvcrt.locking(self.lock_fd, msvcrt.LK_UNLCK, 1)
                else:
                    # Unix: fcntl.flock() with LOCK_UN
                    fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
            except OSError:
                # Ignore errors during lock release
                pass

            # Close file descriptor
            try:
                os.close(self.lock_fd)
            except OSError:
                pass
            self.lock_fd = None

        # Remove lock file (only if we acquired it)
        if self._acquired:
            try:
                self.lock_file_path.unlink(missing_ok=True)
            except OSError:
                pass
            self._acquired = False

    def __enter__(self) -> FileLock:
        """Enter context manager and acquire lock."""
        if not self.acquire():
            # Timeout waiting for lock
            raise TimeoutError(
                f"Could not acquire lock {self.lock_file_path.name} "
                f"after {self.timeout:.1f}s"
            )
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Exit context manager and release lock."""
        self.release()


def atomic_write_with_retry(temp_path: str, target_path: str | Path, max_retries: int = MAX_RETRIES) -> None:
    """Perform atomic file write with retry logic for Windows file locking.

    On Windows, os.replace() can fail with PermissionError (WinError 5) when multiple
    processes/threads try to replace same file concurrently. This function adds
    retry logic with exponential backoff to handle this issue.

    Args:
        temp_path: Path to temporary file to write from
        target_path: Path to target file to write to
        max_retries: Maximum number of retry attempts (from config.MAX_RETRIES)

    Raises:
        PermissionError: If all retry attempts fail
        OSError: For other OS errors during file operations
    """
    target_path_str = str(target_path)
    base_delay = RETRY_BASE_DELAY_SECONDS

    for attempt in range(max_retries):
        try:
            os.replace(temp_path, target_path_str)
            # Success - break out of retry loop
            return
        except PermissionError:
            # Windows-specific file locking error
            logger.warning(
                f"[HandoffStore] Atomic write PermissionError "
                f"(attempt {attempt + 1}/{max_retries}): {target_path_str}"
            )
            if attempt == max_retries - 1:
                # Last attempt failed, clean up and raise
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
                logger.error(
                    f"[HandoffStore] Failed to write {target_path_str} after {max_retries} attempts"
                )
                raise
            # Exponential backoff: 5ms, 10ms, 20ms, 40ms
            delay = base_delay * (2**attempt)
            time.sleep(delay)
        except OSError as e:
            # Other OS errors - don't retry, clean up and raise
            logger.error(f"[HandoffStore] Atomic write OSError for {target_path_str}: {e}")
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise


def atomic_write_with_validation(
    data: dict[str, Any], target_path: str | Path, max_retries: int = MAX_RETRIES
) -> dict[str, Any]:
    """Perform atomic file write with data size validation.

    Validates and truncates handoff data before writing to prevent files
    from exceeding size limit (500KB). This addresses QUAL-009.

    Args:
        data: Dictionary data to write as JSON
        target_path: Path to target file to write to
        max_retries: Maximum number of retry attempts (from config.MAX_RETRIES)

    Returns:
        Dict with size information:
        - original_size: Original data size in bytes
        - final_size: Final data size after validation in bytes
        - truncated: Whether data was truncated

    Raises:
        PermissionError: If all retry attempts fail
        OSError: For other OS errors during file operations
    """
    # Calculate original size
    original_data = json.dumps(data, indent=2)
    original_size = len(original_data.encode("utf-8"))

    # Validate and truncate if necessary (without internal size check)
    # PERF-002: Pass cached_json=None to skip internal serialization
    validated_data = _validate_handoff_data_size(data.copy(), cached_json=None)

    # Calculate final size and cache JSON string (PERF-002)
    final_data = json.dumps(validated_data, indent=2)
    final_size = len(final_data.encode("utf-8"))

    # PERF-002: Perform size check here using cached JSON instead of re-serializing
    if final_size > MAX_HANDOFF_SIZE_BYTES:
        logger.warning(
            f"[HandoffStore] Handoff still exceeds "
            f"{MAX_HANDOFF_SIZE_BYTES} bytes: {final_size} bytes"
        )
        validated_data = _apply_last_resort_truncation(validated_data)
        # Re-serialize after last-resort truncation
        final_data = json.dumps(validated_data, indent=2)
        final_size = len(final_data.encode("utf-8"))

    # Check if truncation occurred
    truncated = original_size != final_size

    # Log warning if data was truncated
    if truncated:
        logger.info(
            f"[HandoffStore] Warning: Handoff data truncated from "
            f"{original_size} to {final_size} bytes"
        )

    # Create temp file and write validated data
    target_path_str = str(target_path)
    target_dir = os.path.dirname(target_path_str)
    fd, temp_path = tempfile.mkstemp(suffix=".tmp", dir=target_dir)

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(final_data)

        # Use atomic_write_with_retry for actual write
        atomic_write_with_retry(temp_path, target_path_str, max_retries)

    except OSError as e:
        # Clean up temp file if write fails
        logger.error(f"[HandoffStore] Failed to write validated data to {target_path_str}: {e}")
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise

    return {
        "original_size": original_size,
        "final_size": final_size,
        "truncated": truncated,
    }


def _truncate_text_field(text: str, max_length: int) -> str:
    """Truncate text field with truncation marker.

    Args:
        text: Text to truncate
        max_length: Maximum length

    Returns:
        Truncated text with marker, or original if under limit
    """
    if len(text) > max_length:
        return text[: max_length - 50] + "\n\n...[truncated]"
    return text


def _truncate_list_with_marker(items: list[Any], max_items: int) -> list[Any]:
    """Truncate list with "and N more" marker.

    Args:
        items: List to truncate
        max_items: Maximum items to keep

    Returns:
        Truncated list with marker, or original if under limit
    """
    if len(items) > max_items:
        truncated = items[:max_items]
        truncated.append(f"...and {len(items) - max_items} more")
        return truncated
    return items


def _truncate_list_keep_recent(items: list[Any], max_items: int) -> list[Any]:
    """Truncate list keeping most recent items.

    Args:
        items: List to truncate
        max_items: Maximum items to keep (from end)

    Returns:
        Truncated list with recent items, or original if under limit
    """
    if len(items) > max_items:
        return items[-max_items:]
    return items


def _truncate_handover_section(handover: dict[str, Any]) -> dict[str, Any]:
    """Truncate handover decisions and patterns.

    Args:
        handover: Handover dict to truncate

    Returns:
        Handover dict with truncated lists
    """
    result = handover.copy()

    if (
        isinstance(result.get("decisions"), list)
        and len(result["decisions"]) > MAX_HANDOVER_DECISIONS
    ):
        result["decisions"] = result["decisions"][:MAX_HANDOVER_DECISIONS]

    if (
        isinstance(result.get("patterns_learned"), list)
        and len(result["patterns_learned"]) > MAX_HANDOVER_PATTERNS
    ):
        result["patterns_learned"] = result["patterns_learned"][:MAX_HANDOVER_PATTERNS]

    return result


def _apply_last_resort_truncation(validated: dict[str, Any]) -> dict[str, Any]:
    """Apply last-resort truncation if size still exceeds limit.

    Args:
        validated: Validated handoff data

    Returns:
        Handoff data with task_aware fields truncated
    """
    task_aware = validated.get("task_aware")
    if isinstance(task_aware, dict):
        # Remove some verbose fields to reduce size
        for field in ["REASONS", "CONTEXT_FILES", "KNOWN_RISKS"]:
            if field in task_aware and task_aware[field]:
                task_aware[field] = []
        validated["task_aware"] = task_aware
        logger.info("[HandoffStore] Truncated task_aware fields to reduce size")

    return validated


def _validate_handoff_data_size(
    handoff_data: dict[str, Any], cached_json: str | None = None
) -> dict[str, Any]:
    """Validate and truncate handoff data to enforce size limits.

    Args:
        handoff_data: Handoff data to validate
        cached_json: Optional cached JSON string to avoid re-serialization (PERF-002)

    Returns:
        Validated handoff data with size limits applied

    Note:
        Limits (QUAL-009):
        - next_steps: Max 10,000 characters
        - active_files: Max 100 files
        - modifications: Max 50 entries
        - recent_tools: Max 30 entries
        - handover decisions/patterns: Max 10 each
        - Total metadata: Max 500 KB
    """
    validated = handoff_data.copy()

    # Truncate next_steps to max length
    next_steps = validated.get("next_steps", "")
    if isinstance(next_steps, str):
        validated["next_steps"] = _truncate_text_field(next_steps, MAX_NEXT_STEPS_LENGTH)

    # Truncate active_files and files_modified lists
    for field in ["active_files", "files_modified"]:
        items = validated.get(field, [])
        if isinstance(items, list):
            validated[field] = _truncate_list_with_marker(items, MAX_ACTIVE_FILES)

    # Truncate modifications and recent_tools (keep most recent)
    for field, limit in [("modifications", MAX_MODIFICATIONS), ("recent_tools", MAX_RECENT_TOOLS)]:
        items = validated.get(field, [])
        if isinstance(items, list):
            validated[field] = _truncate_list_keep_recent(items, limit)

    # Truncate handover patterns/decisions
    handover = validated.get("handover")
    if isinstance(handover, dict):
        validated["handover"] = _truncate_handover_section(handover)

    # PERF-002: Skip size check if cached_json is None (caller will handle it)
    # This avoids duplicate serialization during atomic_write_with_validation
    if cached_json is not None:
        # Use cached JSON if available to avoid re-serialization
        estimated_size = len(cached_json.encode("utf-8"))
        if estimated_size > MAX_HANDOFF_SIZE_BYTES:
            logger.info(
                f"[HandoffStore] Warning: Handoff still exceeds "
                f"{MAX_HANDOFF_SIZE_BYTES} bytes: {estimated_size} bytes"
            )
            validated = _apply_last_resort_truncation(validated)

    return validated


def calculate_quality_score(handoff_data: dict[str, Any]) -> float:
    """Calculate session quality score (0-1) based on /hod algorithm.

    Scoring weights:
    - 30% Completion Tracking: resolved issues vs total modifications
    - 25% Action-Outcome Correlation: blocker presence indicates incomplete work
    - 20% Decision Documentation: number of decisions captured
    - 15% Issue Resolution: absence of blocker indicates resolution
    - 10% Knowledge Contribution: patterns learned captured

    Args:
        handoff_data: Handoff metadata dict

    Returns:
        Quality score between 0.0 and 1.0
    """
    scores = {
        "completion": 0.0,
        "outcomes": 0.0,
        "decisions": 0.0,
        "issues": 0.0,
        "knowledge": 0.0,
    }

    # 30% Completion: whether modifications exist (resolved_issues is never populated)
    modifications = handoff_data.get("modifications", [])
    if modifications:
        scores["completion"] = 1.0 * QUALITY_WEIGHT_COMPLETION
    else:
        # No modifications means no work done - neutral score
        scores["completion"] = 0.5 * QUALITY_WEIGHT_COMPLETION

    # 25% Outcomes: blocker presence indicates incomplete work
    blocker = handoff_data.get("blocker")
    if blocker:
        scores["outcomes"] = (
            0.5 * QUALITY_WEIGHT_OUTCOMES
        )  # Half credit for having blocker documented
    else:
        scores["outcomes"] = 1.0 * QUALITY_WEIGHT_OUTCOMES  # Full credit for no blocker

    # 20% Decisions: number of decisions captured (target: 3+)
    handover = handoff_data.get("handover", {})
    decisions = handover.get("decisions", [])
    if isinstance(decisions, list):
        scores["decisions"] = min(1.0, len(decisions) / 3) * QUALITY_WEIGHT_DECISIONS

    # 15% Issues: absence of blocker indicates resolution progress
    if blocker:
        scores["issues"] = 0.5 * QUALITY_WEIGHT_ISSUES  # Half credit with blocker
    else:
        scores["issues"] = 1.0 * QUALITY_WEIGHT_ISSUES  # Full credit without blocker

    # 10% Knowledge: patterns learned captured (target: 2+)
    patterns = handover.get("patterns_learned", [])
    if isinstance(patterns, list):
        scores["knowledge"] = min(1.0, len(patterns) / 2) * QUALITY_WEIGHT_KNOWLEDGE

    total_score = sum(scores.values())

    # Clamp to [0, 1]
    return max(0.0, min(1.0, total_score))


def get_quality_rating(score: float) -> str:
    """Get quality rating label from score.

    Args:
        score: Quality score between 0 and 1

    Returns:
        Rating label: "Excellent", "Good", "Acceptable", or "Needs Improvement"
    """
    if score >= QUALITY_SCORE_EXCELLENT:
        return "Excellent"
    elif score >= QUALITY_SCORE_GOOD:
        return "Good"
    elif score >= QUALITY_SCORE_ACCEPTABLE:
        return "Acceptable"
    else:
        return "Needs Improvement"


def enrich_handoff_with_bridge_tokens(handoff_data: dict[str, Any]) -> dict[str, Any]:
    """Add bridge tokens to handoff decisions for cross-session continuity.

    Bridge tokens allow tracking specific decisions across compacts.
    Format: BRIDGE_YYYYMMDD-HHMMSS_TOPIC_KEYWORD

    Args:
        handoff_data: Handoff metadata dict

    Returns:
        Enriched handoff data with bridge tokens added to decisions
    """

    enriched = handoff_data.copy()
    handover = enriched.get("handover", {}).copy()
    decisions = handover.get("decisions", []).copy()

    # Add bridge token to each decision
    for i, decision in enumerate(decisions):
        if isinstance(decision, dict):
            decision_copy = decision.copy()
            # Generate bridge token from topic and timestamp
            topic = decision_copy.get("topic", "unknown")
            timestamp = decision_copy.get("timestamp", utcnow_iso())
            bridge_token = generate_bridge_token(topic, timestamp)
            decision_copy["bridge_token"] = bridge_token
            decisions[i] = decision_copy

    handover["decisions"] = decisions
    enriched["handover"] = handover

    return enriched


class HandoffStore:
    """Store handoffs to JSON and Tasks list.

    Handles handoff storage operations including:
    - Building handoff data structure
    - Creating continue_session tasks

    Note: Renamed from CheckpointStore to avoid Claude Code naming conflicts.
    """

    def __init__(self, project_root: Path, terminal_id: str):
        """Initialize handoff store.

        Args:
            project_root: Path to project root directory
            terminal_id: Terminal identifier for task tracking

        Raises:
            ValueError: If terminal_id fails validation (SEC-002)
        """
        # SEC-002: Validate terminal_id format to prevent path traversal and injection attacks
        self._validate_terminal_id(terminal_id)

        self.project_root = project_root
        self.terminal_id = terminal_id
        self._parsed_entries_cache: list[dict[str, Any]] | None = None
        self._cache_transcript_mtime: float | None = None
        self._cache_lines_key: tuple[str, ...] | None = None
        # Track current checkpoint for parent linking
        self._current_checkpoint_id: str | None = None
        self._current_chain_id: str | None = None

    def _validate_terminal_id(self, terminal_id: str) -> None:
        """Validate terminal_id to prevent security issues (SEC-002).

        Security validation checks:
        - Reject empty or whitespace-only strings
        - Reject null bytes (null byte injection)
        - Reject path traversal patterns (../, ./, etc.)
        - Reject absolute paths
        - Allow alphanumeric, underscore, hyphen, and UUID-like formats

        Args:
            terminal_id: Terminal identifier to validate

        Raises:
            ValueError: If terminal_id fails any validation check with descriptive message
        """
        # Check for empty or whitespace-only
        if not terminal_id or not terminal_id.strip():
            raise ValueError(
                "terminal_id cannot be empty or whitespace-only"
            )

        # Check for null bytes (null byte injection prevention)
        if '\x00' in terminal_id:
            raise ValueError(
                f"terminal_id cannot contain null bytes (got: '{terminal_id}')"
            )

        # Check for path traversal patterns
        if '..' in terminal_id or terminal_id.startswith('./'):
            raise ValueError(
                f"terminal_id cannot contain path traversal sequences (got: '{terminal_id}')"
            )

        # Check for absolute paths
        if terminal_id.startswith('/') or terminal_id.startswith('\\'):
            raise ValueError(
                f"terminal_id cannot be an absolute path (got: '{terminal_id}')"
            )

    def build_handoff_data(
        self,
        task_name: str,
        progress_pct: int,
        blocker: dict[str, Any] | None,
        files_modified: list[str],
        next_steps: list[str],
        handover: dict[str, Any],
        modifications: list[dict[str, Any]],
        add_bridge_tokens: bool = True,
        calculate_quality: bool = True,
        pending_operations: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Assemble complete handoff from extracted data.

        Args:
            task_name: Name of task
            progress_pct: Progress percentage
            blocker: Current blocker dict (if any)
            files_modified: List of modified file paths
            next_steps: List of next step descriptions
            handover: Handover data with decisions and patterns
            modifications: List of modification details
            add_bridge_tokens: Add bridge tokens to decisions (default: True)
            calculate_quality: Calculate and add quality score (default: True)
            pending_operations: List of incomplete operations (default: None)

        Returns:
            Complete handoff data dict with optional quality score and bridge tokens
        """
        # Generate checkpoint chain identifiers
        checkpoint_id = str(uuid4())

        # Determine parent checkpoint_id (null for first in chain)
        parent_checkpoint_id = self._current_checkpoint_id

        # Generate or reuse chain_id (groups all checkpoints in same session)
        if self._current_chain_id is None:
            self._current_chain_id = str(uuid4())
        chain_id = self._current_chain_id

        # Update current checkpoint for next call
        self._current_checkpoint_id = checkpoint_id

        session_id = f"session_{int(datetime.now(UTC).timestamp())}_{task_name.lower()}"

        handoff_data: dict[str, Any] = {
            # Checkpoint chain fields (NEW)
            "checkpoint_id": checkpoint_id,
            "parent_checkpoint_id": parent_checkpoint_id,
            "chain_id": chain_id,
            # Existing fields
            "task_name": task_name,
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "progress_pct": progress_pct,
            "blocker": blocker,
            "files_modified": files_modified,
            "next_steps": next_steps,
            "session_summary": f"Handoff captured before compaction at {datetime.now().isoformat()}",
            "handover": handover,
            "modifications": modifications,
            # NEW: Pending operations for fault tolerance
            "pending_operations": pending_operations or [],
        }

        # Add bridge tokens to decisions for cross-session continuity
        if add_bridge_tokens:
            handoff_data = enrich_handoff_with_bridge_tokens(handoff_data)

        # Calculate and add quality score
        if calculate_quality:
            quality_score = calculate_quality_score(handoff_data)
            handoff_data["quality_score"] = quality_score
            handoff_data["quality_rating"] = get_quality_rating(quality_score)

        return handoff_data

    def create_continue_session_task(
        self,
        task_name: str,
        task_id: str,
        handoff_metadata: dict[str, Any],
    ) -> None:
        """Create a continue_session task in task tracker with handoff in metadata.

        This task captures current work in progress, allowing users to
        continue their session after compaction. The handoff data is stored
        directly in task metadata, eliminating need for separate JSON files.

        Args:
            task_name: The name of current task.
            task_id: The unique task identifier.
            handoff_metadata: Complete handoff metadata dict with all data
                needed for session restoration (progress, blocker, next_steps, etc.)

        Side effects:
            - Creates/updates task tracker JSON file
            - Adds active_session and continue_session tasks with handoff in metadata
            - Prints status messages to stdout
        """

        # CRITICAL: Always use terminal_id for task file naming to prevent cross-terminal contamination
        # Session ID is global across terminals and would cause context leakage between concurrent sessions
        task_tracker_dir = self.project_root / ".claude" / "state" / "task_tracker"
        task_file_path = task_tracker_dir / f"{self.terminal_id}_tasks.json"

        # QUAL-009: Validate and truncate handoff metadata before use
        validated_metadata = _validate_handoff_data_size(handoff_metadata)

        # Derive subject from next_steps or task_name
        next_steps = validated_metadata.get("next_steps", "")
        if next_steps:
            lines = next_steps.split("\n")
            subject_source = lines[0][:SUBJECT_MAX_LENGTH]
        else:
            subject_source = task_name
        subject = f"{CONTINUE_SESSION_SUBJECT_PREFIX}{subject_source}"

        # Build active_session task with full handoff in metadata
        active_session_task = {
            "id": "active_session",
            "subject": "Session Restore",
            "status": "pending",
            "created_at": utcnow_iso(),
            "terminal": self.terminal_id,
            "metadata": {
                "handoff": validated_metadata,
                "task_id": task_id,
                "task_name": task_name,
                "pid": os.getpid(),
                "restore_pending": True,
            },
        }

        # Build continue_session task (legacy user-visible task)
        continue_task = {
            "id": CONTINUE_SESSION_TASK_ID,
            "subject": subject,
            "status": CONTINUE_SESSION_STATUS_PENDING,
            "created_at": utcnow_iso(),
            "terminal": self.terminal_id,
            "metadata": {
                "handoff": validated_metadata,
                "original_task_id": task_id,
                "restored_from": CONTINUE_SESSION_RESTORED_FROM,
            },
        }

        # Load existing task data or create new structure
        task_tracker_dir.mkdir(parents=True, exist_ok=True)

        def _create_empty_task_data() -> dict[str, Any]:
            """Create empty task data structure."""
            return {
                "terminal_id": self.terminal_id,
                "tasks": {},
                "last_update": utcnow_iso(),
            }

        if task_file_path.exists():
            try:
                with open(task_file_path, encoding="utf-8") as f:
                    task_data = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(
                    f"[HandoffStore] Failed to load task file {task_file_path}, creating new: {e}"
                )
                task_data = _create_empty_task_data()
        else:
            task_data = _create_empty_task_data()

        # Add metadata field to existing tasks that don't have it
        for task_id_key, task in task_data["tasks"].items():
            if "metadata" not in task:
                task["metadata"] = {}

        # Add active_session task for SessionStart restore detection
        task_data["tasks"]["active_session"] = active_session_task

        # Add continue_session task to tasks dict (user-visible)
        task_data["tasks"][CONTINUE_SESSION_TASK_ID] = continue_task
        task_data["last_update"] = utcnow_iso()

        # PERF-001: Create manifest file for O(1) lookup
        manifest_path = task_tracker_dir / "active_session_manifest.json"
        manifest_data = {
            "terminal_id": self.terminal_id,
            "timestamp": utcnow_iso(),
            "handoff_path": validated_metadata.get("transcript_path", ""),
        }

        # SEC-003: Use atomic file locking to prevent concurrent compaction race condition
        # Platform-specific locking (Windows: msvcrt.locking, Unix: fcntl.flock)
        # This replaces the vulnerable os.open(O_CREAT|O_EXCL) approach which had TOCTOU vulnerability
        lock_file_path = task_file_path.with_suffix(".lock")

        try:
            # Acquire lock with timeout and stale lock handling
            # FileLock context manager ensures lock is released even on error
            with FileLock(lock_file_path, timeout=LOCK_TIMEOUT_SECONDS, stale_age=STALE_LOCK_AGE_SECONDS):
                # Atomic write: temp file + rename
                fd, temp_path = tempfile.mkstemp(
                    suffix=".tmp", dir=str(task_tracker_dir), prefix=f"{self.terminal_id}_tasks_"
                )
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        json.dump(task_data, f, indent=2)

                    # Atomic rename with retry for Windows PermissionError (WinError 5)
                    atomic_write_with_retry(temp_path, task_file_path)

                    logger.info(
                        f"[HandoffStore] active_session task added to {task_file_path.name} (PID {os.getpid()})"
                    )
                    logger.info(
                        f"[HandoffStore] continue_session task added to {task_file_path.name}"
                    )

                    # Write manifest file atomically
                    fd_manifest, temp_manifest_path = tempfile.mkstemp(
                        suffix=".tmp", dir=str(task_tracker_dir), prefix="active_session_manifest_"
                    )
                    try:
                        with os.fdopen(fd_manifest, "w", encoding="utf-8") as f:
                            json.dump(manifest_data, f, indent=2)
                        atomic_write_with_retry(temp_manifest_path, manifest_path)
                        logger.debug(f"[HandoffStore] Created manifest file: {manifest_path.name}")
                    except OSError as manifest_error:
                        logger.error(f"[HandoffStore] Failed to write manifest file: {manifest_error}")
                        try:
                            os.unlink(temp_manifest_path)
                        except OSError:
                            pass
                        # Manifest is optional, don't fail the entire operation
                except OSError as write_error:
                    logger.error(
                        f"[HandoffStore] Failed to write task file {task_file_path}: {write_error}"
                    )
                    try:
                        os.unlink(temp_path)
                    except OSError:
                        pass
                    raise write_error

        except TimeoutError:
            # Lock acquisition timeout - log warning but proceed with write
            # This maintains backward compatibility with original behavior
            logger.warning(
                f"[HandoffStore] Could not acquire lock for {task_file_path.name} after "
                f"{LOCK_TIMEOUT_SECONDS}s timeout - proceeding with write anyway (risk of concurrent writes)"
            )
            # Proceed with write anyway (risky but maintains compatibility)
            fd, temp_path = tempfile.mkstemp(
                suffix=".tmp", dir=str(task_tracker_dir), prefix=f"{self.terminal_id}_tasks_"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(task_data, f, indent=2)
                atomic_write_with_retry(temp_path, task_file_path)
                logger.info(
                    f"[HandoffStore] active_session task added to {task_file_path.name} (PID {os.getpid()}) [no lock]"
                )
                logger.info(
                    f"[HandoffStore] continue_session task added to {task_file_path.name} [no lock]"
                )

                # Write manifest file atomically (even without lock)
                fd_manifest, temp_manifest_path = tempfile.mkstemp(
                    suffix=".tmp", dir=str(task_tracker_dir), prefix="active_session_manifest_"
                )
                try:
                    with os.fdopen(fd_manifest, "w", encoding="utf-8") as f:
                        json.dump(manifest_data, f, indent=2)
                    atomic_write_with_retry(temp_manifest_path, manifest_path)
                    logger.debug(f"[HandoffStore] Created manifest file: {manifest_path.name} [no lock]")
                except OSError as manifest_error:
                    logger.error(f"[HandoffStore] Failed to write manifest file: {manifest_error}")
                    try:
                        os.unlink(temp_manifest_path)
                    except OSError:
                        pass
            except OSError as write_error:
                logger.error(
                    f"[HandoffStore] Failed to write task file {task_file_path}: {write_error}"
                )
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
                raise write_error

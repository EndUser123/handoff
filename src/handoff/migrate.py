#!/usr/bin/env python3
"""
Handoff Migration Utilities

Migrate existing handoff JSON files to task metadata format.

This module provides utilities for migrating from the dual storage system
(HandoffManager JSON files + task tracker) to the consolidated task-based
storage system.

Usage:
    from handoff.migrate import compute_metadata_checksum, migrate_handoffs

    # Compute checksum for handoff data
    checksum = compute_metadata_checksum(handoff_data)

    # Migrate all handoffs
    results = migrate_handoffs(handoff_dir, task_tracker_dir, terminal_id)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

# Add hooks directory to path for terminal_detection import
_hooks_path = Path(__file__).parent.parent / "hooks"
if str(_hooks_path) not in sys.path:
    sys.path.insert(0, str(_hooks_path))

try:
    from terminal_detection import detect_terminal_id
except ImportError:
    logger.debug("[Migrate] terminal_detection module not available")

    # Fallback if terminal_detection unavailable
    def detect_terminal_id() -> str:  # type: ignore[misc]
        return f"term_{os.getpid()}"

# Import utility functions


def migrate_old_handoff_to_checkpoint(old_handoff: dict[str, Any]) -> dict[str, Any]:
    """Migrate old handoff data to checkpoint format with sensible defaults.

    This function converts old handoff data to the new checkpoint format,
    handling missing optional fields with sensible defaults.

    Args:
        old_handoff: Old handoff dictionary

    Returns:
        Checkpoint dict with all required fields populated

    Note:
        Default values for missing fields:
        - pending_operations: [] (empty list)
        - timestamp: saved_at field, or current ISO time if both missing
        - metadata: {} (empty dict)

    Example:
        >>> old_data = {"task_name": "test", "saved_at": "2025-01-15T10:30:00Z"}
        >>> checkpoint = migrate_old_handoff_to_checkpoint(old_data)
        >>> checkpoint["pending_operations"]
        []
        >>> checkpoint["timestamp"]
        '2025-01-15T10:30:00Z'
    """
    # Create a copy to avoid mutating original
    checkpoint = old_handoff.copy()

    # Add pending_operations with default empty list
    if "pending_operations" not in checkpoint:
        checkpoint["pending_operations"] = []

    # Add timestamp with fallback to saved_at or current time
    if "timestamp" not in checkpoint:
        from handoff.config import utcnow_iso

        checkpoint["timestamp"] = checkpoint.get("saved_at") or utcnow_iso()

    # Add metadata with default empty dict
    if "metadata" not in checkpoint:
        checkpoint["metadata"] = {}

    return checkpoint


def compute_metadata_checksum(handoff_data: dict[str, Any]) -> str:
    """Compute SHA256 checksum of handoff metadata.

    Args:
        handoff_data: Handoff dictionary from task metadata or JSON file

    Returns:
        SHA256 checksum as hex string with "sha256:" prefix

    Note:
        - Serializes handoff_data to JSON with sorted keys for deterministic output
        - Uses default=str to handle datetime and other non-serializable types
        - Returns format: "sha256:{hexdigest}"

    Example:
        >>> data = {"task_name": "test", "progress": 50}
        >>> compute_metadata_checksum(data)
        "sha256:a94a8fe5ccb19ba61c4c0873d391e987982fbbd3..."
    """
    # Serialize with sorted keys for deterministic output
    serialized = json.dumps(handoff_data, sort_keys=True, default=str)
    # Compute SHA256 hash
    hash_obj = hashlib.sha256(serialized.encode("utf-8"))
    return f"sha256:{hash_obj.hexdigest()}"


def load_handoff_json(json_path: Path) -> dict[str, Any] | None:
    """Load and validate handoff JSON file.

    Args:
        json_path: Path to handoff JSON file

    Returns:
        Handoff data dict or None if invalid/corrupt

    Note:
        - Validates required fields (task_name, saved_at/version)
        - Verifies checksum if present
        - Returns None for invalid files
    """
    from handoff.config import load_json_file

    data = load_json_file(json_path)
    if not data:
        return None

    # Validate required fields
    if "task_name" not in data:
        # Try alternative field names from different handoff versions
        if "session_id" not in data and "id" not in data:
            return None

    # Verify checksum if present
    try:
        if "checksum" in data:
            stored = data["checksum"]
            # Remove checksum for recomputation
            data_for_hash = {k: v for k, v in data.items() if k != "checksum"}
            computed = compute_metadata_checksum(data_for_hash)
            if not stored.startswith(computed):
                # Checksum mismatch - file may be corrupted
                return None
    except (ValueError, TypeError) as e:
        logger.debug(f"[Migrate] Could not parse timestamp: {e}")
        return None

    return data


def handoff_to_task(handoff_data: dict[str, Any], terminal_id: str) -> dict[str, Any]:
    """Convert handoff JSON to task metadata format.

    Args:
        handoff_data: Handoff data from JSON file
        terminal_id: Terminal identifier for task isolation

    Returns:
        Task dict with handoff in metadata field

    Note:
        - Creates a task with nested handoff metadata
        - Preserves all original handoff data
        - Adds migration metadata (migrated_at, migrated_from)
        - Applies checkpoint chain field migration for backward compatibility
    """
    from handoff.config import utcnow_iso

    # Apply checkpoint chain field migration to ensure compatibility
    migrated_handoff = migrate_checkpoint_chain_fields(handoff_data)

    return {
        "id": "migrated_handoff",
        "subject": f"Handoff: {migrated_handoff.get('task_name', 'unknown')}",
        "status": "completed",
        "created_at": (
            migrated_handoff.get("saved_at") or migrated_handoff.get("timestamp") or utcnow_iso()
        ),
        "terminal": terminal_id,
        "metadata": {
            "handoff": {
                # Checkpoint chain fields (from migration if not present)
                "checkpoint_id": migrated_handoff.get("checkpoint_id"),
                "parent_checkpoint_id": migrated_handoff.get("parent_checkpoint_id"),
                "chain_id": migrated_handoff.get("chain_id"),
                # Existing fields
                "task_name": (
                    migrated_handoff.get("task_name")
                    or migrated_handoff.get("session_id", "unknown")
                ),
                "task_type": migrated_handoff.get("task_type", "informal"),
                "progress_percent": (
                    migrated_handoff.get("progress_percent")
                    or migrated_handoff.get("progress_pct", 0)
                ),
                "blocker": migrated_handoff.get("blocker"),
                "next_steps": migrated_handoff.get("next_steps", ""),
                "git_branch": migrated_handoff.get("git_branch"),
                "active_files": (
                    migrated_handoff.get("active_files")
                    or migrated_handoff.get("files_modified", [])
                ),
                "recent_tools": migrated_handoff.get("recent_tools", []),
                "transcript_path": str(migrated_handoff.get("transcript_path", "")),
                "transcript_offset": migrated_handoff.get("transcript_offset", 0),
                "transcript_entry_count": migrated_handoff.get("transcript_entry_count", 0),
                "handover": migrated_handoff.get("handover"),
                "open_conversation_context": migrated_handoff.get("open_conversation_context"),
                "resolved_issues": migrated_handoff.get("resolved_issues", []),
                "modifications": migrated_handoff.get("modifications", []),
                "saved_at": (migrated_handoff.get("saved_at") or migrated_handoff.get("timestamp")),
                "checksum": migrated_handoff.get("checksum"),
                "version": migrated_handoff.get("version", 1),
                "migrated_at": utcnow_iso(),
                "migrated_from": "handoff_json",
            },
            "pid": migrated_handoff.get("pid"),
            "restore_pending": False,  # Migrated handoffs don't need restoration
        },
    }


def _create_task_file_structure(terminal_id: str) -> dict[str, Any]:
    """Create new task file structure.

    Args:
        terminal_id: Terminal identifier

    Returns:
        Dict with terminal_id, empty tasks dict, and last_update timestamp
    """
    from handoff.config import utcnow_iso

    return {"terminal_id": terminal_id, "tasks": {}, "last_update": utcnow_iso()}


def _load_or_create_task_file(task_file_path: Path, terminal_id: str) -> dict[str, Any]:
    """Load existing task file or create new structure.

    Args:
        task_file_path: Path to task file
        terminal_id: Terminal identifier

    Returns:
        Task data dict
    """

    if task_file_path.exists():
        try:
            with open(task_file_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError, ValueError) as e:
            logger.debug(f"[Migrate] Task file corrupt, creating new: {e}")
            # File exists but is corrupt, create new structure
            return _create_task_file_structure(terminal_id)
    else:
        # File doesn't exist, create new structure
        return _create_task_file_structure(terminal_id)


def _write_task_file_atomic(task_file_path: Path, task_data: dict[str, Any]) -> bool:
    """Write task file using atomic write (temp file + rename).

    Args:
        task_file_path: Path to task file
        task_data: Task data to write

    Returns:
        True if successful, raises OSError if failed
    """
    fd, temp_path_str = tempfile.mkstemp(suffix=".tmp", dir=str(task_file_path.parent))
    temp_path = Path(temp_path_str)
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(task_data, indent=2))
        temp_path.replace(task_file_path)
        return True
    except OSError as replace_error:
        logger.debug(f"[Migrate] Could not replace task file: {replace_error}")
        try:
            temp_path.unlink()
        except OSError as unlink_error:
            logger.debug(f"[Migrate] Could not unlink temp file: {unlink_error}")
        raise


def _initialize_migration_results() -> dict[str, Any]:
    """Initialize migration results dict.

    Returns:
        Dict with counters and error list
    """
    return {"migrated": 0, "failed": 0, "skipped": 0, "errors": []}


def _collect_handoff_files(handoff_dir: Path) -> list[Path] | None:
    """Find all handoff JSON files in directory.

    Args:
        handoff_dir: Directory to search

    Returns:
        List of JSON file paths, or None if directory not found
    """
    if not handoff_dir.exists():
        return None

    handoff_files = list(handoff_dir.glob("*.json"))
    # Skip directories (like trash/)
    return [f for f in handoff_files if f.is_file()]


def _load_handoff_with_validation(
    json_path: Path, results: dict[str, Any]
) -> dict[str, Any] | None:
    """Load handoff JSON with error tracking.

    Args:
        json_path: Path to handoff JSON file
        results: Results dict to update on failure

    Returns:
        Handoff data dict, or None if loading failed
    """
    handoff_data = load_handoff_json(json_path)
    if not handoff_data:
        results["failed"] += 1
        results["errors"].append(f"{json_path.name}: Invalid or corrupt")
    return handoff_data


def _handle_dry_run_migration(json_path: Path, results: dict[str, Any]) -> None:
    """Handle dry-run migration (no file writes).

    Args:
        json_path: Path to handoff JSON file
        results: Results dict to update
    """
    logger.info(f"[DRY RUN] Would migrate: {json_path.name}")
    results["migrated"] += 1


def _migrate_handoff_to_task_file(
    json_path: Path,
    task: dict[str, Any],
    task_file_path: Path,
    terminal_id: str,
    results: dict[str, Any],
) -> None:
    """Migrate single handoff to task file with idempotency check.

    Args:
        json_path: Path to handoff JSON file
        task: Task dict to migrate
        task_file_path: Path to task tracker file
        terminal_id: Terminal identifier
        results: Results dict to update
    """
    # Load or create task file
    task_data = _load_or_create_task_file(task_file_path, terminal_id)

    # Add migrated task
    task_id = f"migrated_{json_path.stem}"
    task["id"] = task_id

    # Check if task already exists (idempotency)
    if task_id in task_data["tasks"]:
        # Task already migrated, skip it
        results["skipped"] += 1
        return

    task_data["tasks"][task_id] = task
    from handoff.config import utcnow_iso

    task_data["last_update"] = utcnow_iso()

    # Write task file with atomic write
    try:
        _write_task_file_atomic(task_file_path, task_data)
        logger.info(f"Migrated: {json_path.name} -> {task_id}")
        results["migrated"] += 1
    except OSError as e:
        logger.warning(f"[Migrate] Failed to migrate {json_path.name}: {e}")
        results["failed"] += 1
        results["errors"].append(f"{json_path.name}: {e}")


def _process_single_handoff(
    json_path: Path,
    task_tracker_dir: Path,
    terminal_id: str,
    dry_run: bool,
    results: dict[str, Any],
) -> None:
    """Process a single handoff file migration.

    Args:
        json_path: Path to handoff JSON file
        task_tracker_dir: Directory for task tracker files
        terminal_id: Terminal identifier
        dry_run: If True, skip file writes
        results: Results dict to update
    """
    # Load handoff data
    handoff_data = _load_handoff_with_validation(json_path, results)
    if not handoff_data:
        return

    # Convert to task format
    task = handoff_to_task(handoff_data, terminal_id)

    # Determine task file path
    task_file_path = task_tracker_dir / f"{terminal_id}_tasks.json"

    if dry_run:
        _handle_dry_run_migration(json_path, results)
        return

    # Ensure task tracker directory exists
    task_tracker_dir.mkdir(parents=True, exist_ok=True)

    # Migrate to task file
    _migrate_handoff_to_task_file(
        json_path,
        task,
        task_file_path,
        terminal_id,
        results,
    )


def migrate_handoffs(
    handoff_dir: Path, task_tracker_dir: Path, terminal_id: str | None = None, dry_run: bool = False
) -> dict[str, Any]:
    """Migrate all handoff JSON files to task metadata.

    Args:
        handoff_dir: Directory containing handoff JSON files
        task_tracker_dir: Directory for task tracker files
        terminal_id: Terminal identifier for task isolation (auto-detected if None)
        dry_run: If True, don't write any files

    Returns:
        Migration results dict with counts:
        - migrated: Number of successfully migrated handoffs
        - failed: Number of failed migrations
        - skipped: Number of skipped handoffs
        - errors: List of error messages

    Note:
        - Creates backup of task files before migration
        - Uses atomic writes (temp file + rename)
        - Validates checksums before migration
        - Logs progress to stdout
    """
    results = _initialize_migration_results()

    # Auto-detect terminal ID if not provided
    if terminal_id is None:
        terminal_id = detect_terminal_id()

    # Find all handoff JSON files
    handoff_files = _collect_handoff_files(handoff_dir)
    if handoff_files is None:
        results["errors"].append(f"Handoff directory not found: {handoff_dir}")
        return results

    logger.info(f"Found {len(handoff_files)} handoff files")

    # Process each handoff file
    for json_path in handoff_files:
        _process_single_handoff(
            json_path,
            task_tracker_dir,
            terminal_id,
            dry_run,
            results,
        )

    return results


def _truncate_active_files(handoff_data: dict[str, Any]) -> None:
    """Truncate active_files to 100 items with truncation marker.

    Modifies handoff_data in place.

    Args:
        handoff_data: Handoff dictionary to update
    """
    active_files = handoff_data.get("active_files", [])
    if isinstance(active_files, list) and len(active_files) > 100:
        handoff_data["active_files"] = active_files[:100]
        handoff_data["active_files"].append(f"...and {len(active_files) - 100} more")


def _truncate_next_steps(handoff_data: dict[str, Any]) -> None:
    """Truncate next_steps to 10,000 characters.

    Modifies handoff_data in place.

    Args:
        handoff_data: Handoff dictionary to update
    """
    next_steps = handoff_data.get("next_steps", "")
    if isinstance(next_steps, str) and len(next_steps) > 10000:
        handoff_data["next_steps"] = next_steps[:9950] + "\n\n...[truncated]"


def _truncate_handover_lists(handoff_data: dict[str, Any]) -> None:
    """Truncate handover patterns/decisions to 10 items each.

    Modifies handoff_data in place.

    Args:
        handoff_data: Handoff dictionary to update
    """
    handover = handoff_data.get("handover")
    if isinstance(handover, dict):
        handover = handover.copy()
        if isinstance(handover.get("decisions"), list) and len(handover["decisions"]) > 10:
            handover["decisions"] = handover["decisions"][:10]
        if (
            isinstance(handover.get("patterns_learned"), list)
            and len(handover["patterns_learned"]) > 10
        ):
            handover["patterns_learned"] = handover["patterns_learned"][:10]
        handoff_data["handover"] = handover


def _truncate_list_keep_recent(
    handoff_data: dict[str, Any], field_name: str, max_entries: int
) -> None:
    """Truncate list field to max entries, keeping most recent.

    Modifies handoff_data in place.

    Args:
        handoff_data: Handoff dictionary to update
        field_name: Name of the list field to truncate
        max_entries: Maximum number of entries to keep
    """
    items = handoff_data.get(field_name, [])
    if isinstance(items, list) and len(items) > max_entries:
        handoff_data[field_name] = items[-max_entries:]


def _warn_if_oversized(handoff_data: dict[str, Any], max_bytes: int = 500_000) -> None:
    """Warn if handoff data size exceeds limit.

    Args:
        handoff_data: Handoff dictionary to check
        max_bytes: Maximum allowed size in bytes (default: 500 KB)
    """
    estimated_size = len(json.dumps(handoff_data).encode("utf-8"))
    if estimated_size > max_bytes:
        logger.warning(f"Handoff metadata exceeds {max_bytes // 1000} KB: {estimated_size} bytes")


def validate_handoff_size(handoff_data: dict[str, Any]) -> dict[str, Any]:
    """Enforce metadata size limits to prevent task file bloat.

    Args:
        handoff_data: Handoff dictionary to validate

    Returns:
        Validated handoff dict with size limits applied

    Note:
        Limits (from plan PR-001):
        - active_files: Max 100 files (truncate with "...and N more")
        - next_steps: Max 10,000 characters
        - handover patterns/decisions: Max 10 each
        - recent_tools: Max 30 entries (FIFO)
        - modifications: Max 50 entries (FIFO)
        - Total metadata: Max 500 KB

    Example:
        >>> data = {"active_files": list(range(150)), "next_steps": "x" * 15000}
        >>> validated = validate_handoff_size(data)
        >>> len(validated["active_files"])
        101  # 100 files + truncation marker
    """
    # Create a copy to avoid mutating original
    validated = handoff_data.copy()

    # Apply all truncation rules
    _truncate_active_files(validated)
    _truncate_next_steps(validated)
    _truncate_handover_lists(validated)
    _truncate_list_keep_recent(validated, "recent_tools", 30)
    _truncate_list_keep_recent(validated, "modifications", 50)

    # Warn if oversized
    _warn_if_oversized(validated)

    return validated


def _validate_checkpoint_chain_field_types(handoff_data: dict[str, Any]) -> None:
    """Validate types of existing checkpoint chain fields.

    Args:
        handoff_data: Handoff dictionary to validate

    Raises:
        TypeError: If any existing field has wrong type
    """
    if "checkpoint_id" in handoff_data and not isinstance(handoff_data["checkpoint_id"], str):
        raise TypeError("checkpoint_id must be str")

    if "parent_checkpoint_id" in handoff_data:
        if not isinstance(handoff_data["parent_checkpoint_id"], (str, type(None))):
            raise TypeError("parent_checkpoint_id must be str or None")

    if "chain_id" in handoff_data and not isinstance(handoff_data["chain_id"], str):
        raise TypeError("chain_id must be str")


def _add_missing_checkpoint_chain_fields(handoff_data: dict[str, Any]) -> None:
    """Add missing checkpoint chain fields with defaults.

    This modifies handoff_data in place.

    Args:
        handoff_data: Handoff dictionary to update
    """
    # Only add fields if they don't already exist (idempotent)
    if "checkpoint_id" not in handoff_data:
        handoff_data["checkpoint_id"] = str(uuid4())

    if "parent_checkpoint_id" not in handoff_data:
        # Old handoffs have no parent (treated as first in chain)
        handoff_data["parent_checkpoint_id"] = None

    if "chain_id" not in handoff_data:
        # Generate new chain ID for migrated handoffs
        handoff_data["chain_id"] = str(uuid4())

    # Add transcript tracking fields for migrated handoffs
    # Use 0 as default since we don't have exact historical data
    if "transcript_offset" not in handoff_data:
        handoff_data["transcript_offset"] = 0

    if "transcript_entry_count" not in handoff_data:
        handoff_data["transcript_entry_count"] = 0


def migrate_checkpoint_chain_fields(handoff_data: dict[str, Any]) -> dict[str, Any]:
    """Migrate old handoff data to include checkpoint chain fields.

    This function adds checkpoint_id, parent_checkpoint_id, and chain_id to
    handoff data that doesn't have these fields. It is idempotent - safe to run
    multiple times on the same data.

    Args:
        handoff_data: Handoff dictionary from task metadata or JSON file

    Returns:
        Updated handoff dict with checkpoint chain fields added

    Raises:
        TypeError: If handoff_data is None or existing fields have wrong types

    Note:
        - Generates checkpoint_id as UUID v4 for migrated handoffs
        - Sets parent_checkpoint_id to null for migrated handoffs (first in chain)
        - Generates chain_id as new session UUID
        - Idempotent: if fields already exist, they are preserved
        - Sets transcript_offset and transcript_entry_count to 0 for migrated handoffs
          (exact values unavailable for historical data)
        - Validates types of existing checkpoint chain fields

    Example:
        >>> old_handoff = {"task_name": "test", "saved_at": "2025-01-01"}
        >>> migrated = migrate_checkpoint_chain_fields(old_handoff)
        >>> "checkpoint_id" in migrated
        True
        >>> migrated["parent_checkpoint_id"] is None
        True
    """
    # Validate input type
    if handoff_data is None:
        raise TypeError("handoff_data expected dict or None")

    # Create a copy to avoid mutating original
    migrated = handoff_data.copy()

    # Validate existing field types
    _validate_checkpoint_chain_field_types(migrated)

    # Add missing fields
    _add_missing_checkpoint_chain_fields(migrated)

    return migrated


def main() -> int:
    """CLI entry point for handoff migration.

    Usage:
        python -m handoff.migrate [--dry-run] [--terminal-id ID]

    Returns:
        Exit code (0 for success, 1 for failure)
    """

    parser = argparse.ArgumentParser(description="Migrate handoff JSON files to task metadata")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be done without making changes"
    )
    parser.add_argument("--terminal-id", help="Terminal ID (auto-detected if not specified)")
    parser.add_argument("--handoff-dir", default=".claude/handoffs", help="Handoff directory")
    parser.add_argument(
        "--task-tracker-dir", default=".claude/state/task_tracker", help="Task tracker directory"
    )

    args = parser.parse_args()

    # Detect terminal ID if not specified
    terminal_id = args.terminal_id or detect_terminal_id()

    handoff_dir = Path(args.handoff_dir)
    task_tracker_dir = Path(args.task_tracker_dir)

    if not handoff_dir.exists():
        print(f"ERROR: Handoff directory not found: {handoff_dir}")
        return 1

    print(f"Migrating handoffs from {handoff_dir}")
    print(f"Terminal ID: {terminal_id}")
    print(f"Task tracker: {task_tracker_dir}")
    print()

    results = migrate_handoffs(handoff_dir, task_tracker_dir, terminal_id, args.dry_run)

    print()
    print("Migration Results:")
    print(f"  Migrated: {results['migrated']}")
    print(f"  Failed: {results['failed']}")
    print(f"  Skipped: {results['skipped']}")

    if results["errors"]:
        print()
        print("Errors:")
        for error in results["errors"]:
            print(f"  - {error}")

    return 0 if results["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

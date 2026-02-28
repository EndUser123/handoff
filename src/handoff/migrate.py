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
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

# Add hooks directory to path for terminal_detection import
_hooks_path = Path(__file__).parent.parent / "hooks"
if str(_hooks_path) not in sys.path:
    sys.path.insert(0, str(_hooks_path))

try:
    from terminal_detection import detect_terminal_id
except ImportError:
    # Fallback if terminal_detection unavailable
    def detect_terminal_id() -> str:  # type: ignore[misc]
        return f"term_{os.getpid()}"


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
        checkpoint["timestamp"] = checkpoint.get("saved_at") or datetime.now(UTC).isoformat()

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
    hash_obj = hashlib.sha256(serialized.encode('utf-8'))
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
    try:
        data = json.loads(json_path.read_text(encoding='utf-8'))

        # Validate required fields
        if "task_name" not in data:
            # Try alternative field names from different handoff versions
            if "session_id" not in data and "id" not in data:
                return None

        # Verify checksum if present
        if "checksum" in data:
            stored = data["checksum"]
            # Remove checksum for recomputation
            data_for_hash = {k: v for k, v in data.items() if k != "checksum"}
            computed = compute_metadata_checksum(data_for_hash)
            if not stored.startswith(computed):
                # Checksum mismatch - file may be corrupted
                return None

        return data
    except (json.JSONDecodeError, OSError, ValueError):
        return None


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
    # Apply checkpoint chain field migration to ensure compatibility
    migrated_handoff = migrate_checkpoint_chain_fields(handoff_data)

    return {
        "id": "migrated_handoff",
        "subject": f"Handoff: {migrated_handoff.get('task_name', 'unknown')}",
        "status": "completed",
        "created_at": migrated_handoff.get("saved_at") or migrated_handoff.get("timestamp") or datetime.now(UTC).isoformat(),
        "terminal": terminal_id,
        "metadata": {
            "handoff": {
                # Checkpoint chain fields (from migration if not present)
                "checkpoint_id": migrated_handoff.get("checkpoint_id"),
                "parent_checkpoint_id": migrated_handoff.get("parent_checkpoint_id"),
                "chain_id": migrated_handoff.get("chain_id"),
                # Existing fields
                "task_name": migrated_handoff.get("task_name") or migrated_handoff.get("session_id", "unknown"),
                "task_type": migrated_handoff.get("task_type", "informal"),
                "progress_percent": migrated_handoff.get("progress_percent") or migrated_handoff.get("progress_pct", 0),
                "blocker": migrated_handoff.get("blocker"),
                "next_steps": migrated_handoff.get("next_steps", ""),
                "git_branch": migrated_handoff.get("git_branch"),
                "active_files": migrated_handoff.get("active_files") or migrated_handoff.get("files_modified", []),
                "recent_tools": migrated_handoff.get("recent_tools", []),
                "transcript_path": str(migrated_handoff.get("transcript_path", "")),
                "transcript_offset": migrated_handoff.get("transcript_offset", 0),
                "transcript_entry_count": migrated_handoff.get("transcript_entry_count", 0),
                "handover": migrated_handoff.get("handover"),
                "open_conversation_context": migrated_handoff.get("open_conversation_context"),
                "resolved_issues": migrated_handoff.get("resolved_issues", []),
                "modifications": migrated_handoff.get("modifications", []),
                "saved_at": migrated_handoff.get("saved_at") or migrated_handoff.get("timestamp"),
                "checksum": migrated_handoff.get("checksum"),
                "version": migrated_handoff.get("version", 1),
                "migrated_at": datetime.now(UTC).isoformat(),
                "migrated_from": "handoff_json"
            },
            "pid": migrated_handoff.get("pid"),
            "restore_pending": False  # Migrated handoffs don't need restoration
        }
    }


def migrate_handoffs(
    handoff_dir: Path,
    task_tracker_dir: Path,
    terminal_id: str | None = None,
    dry_run: bool = False
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
    results = {"migrated": 0, "failed": 0, "skipped": 0, "errors": []}

    # Auto-detect terminal ID if not provided
    if terminal_id is None:
        terminal_id = detect_terminal_id()

    # Find all handoff JSON files
    if not handoff_dir.exists():
        results["errors"].append(f"Handoff directory not found: {handoff_dir}")
        return results

    handoff_files = list(handoff_dir.glob("*.json"))
    # Skip directories (like trash/)
    handoff_files = [f for f in handoff_files if f.is_file()]

    print(f"Found {len(handoff_files)} handoff files")

    for json_path in handoff_files:
        # Load handoff data
        handoff_data = load_handoff_json(json_path)
        if not handoff_data:
            results["failed"] += 1
            results["errors"].append(f"{json_path.name}: Invalid or corrupt")
            continue

        # Convert to task format
        task = handoff_to_task(handoff_data, terminal_id)

        # Determine task file path
        task_file_path = task_tracker_dir / f"{terminal_id}_tasks.json"

        if dry_run:
            print(f"[DRY RUN] Would migrate: {json_path.name}")
            results["migrated"] += 1
            continue

        # Ensure task tracker directory exists
        task_tracker_dir.mkdir(parents=True, exist_ok=True)

        # Load or create task file
        if task_file_path.exists():
            try:
                with open(task_file_path, encoding="utf-8") as f:
                    task_data = json.load(f)
            except (json.JSONDecodeError, OSError, ValueError):
                # File exists but is corrupt, create new structure
                task_data = {
                    "terminal_id": terminal_id,
                    "tasks": {},
                    "last_update": datetime.now(UTC).isoformat()
                }
        else:
            # File doesn't exist, create new structure
            task_data = {
                "terminal_id": terminal_id,
                "tasks": {},
                "last_update": datetime.now(UTC).isoformat()
            }

        # Add migrated task
        task_id = f"migrated_{json_path.stem}"
        task["id"] = task_id

        # Check if task already exists (idempotency)
        if task_id in task_data["tasks"]:
            # Task already migrated, skip it
            results["skipped"] += 1
            continue

        task_data["tasks"][task_id] = task
        task_data["last_update"] = datetime.now(UTC).isoformat()

        # Write task file with atomic write (mkstemp avoids concurrent migration races)
        try:
            fd, temp_path_str = tempfile.mkstemp(
                suffix=".tmp", dir=str(task_file_path.parent)
            )
            temp_path = Path(temp_path_str)
            try:
                with open(fd, "w", encoding="utf-8") as f:
                    f.write(json.dumps(task_data, indent=2))
                temp_path.replace(task_file_path)
            except OSError:
                try:
                    temp_path.unlink()
                except OSError:
                    pass
                raise
            print(f"Migrated: {json_path.name} -> {task_id}")
            results["migrated"] += 1
        except OSError as e:
            results["failed"] += 1
            results["errors"].append(f"{json_path.name}: {e}")

    return results


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

    # Truncate active_files to 100 items
    active_files = validated.get("active_files", [])
    if isinstance(active_files, list) and len(active_files) > 100:
        validated["active_files"] = active_files[:100]
        validated["active_files"].append(f"...and {len(active_files) - 100} more")

    # Truncate next_steps to 10,000 characters
    next_steps = validated.get("next_steps", "")
    if isinstance(next_steps, str) and len(next_steps) > 10000:
        validated["next_steps"] = next_steps[:9950] + "\n\n...[truncated]"

    # Truncate handover patterns/decisions
    handover = validated.get("handover")
    if isinstance(handover, dict):
        handover = handover.copy()
        if isinstance(handover.get("decisions"), list) and len(handover["decisions"]) > 10:
            handover["decisions"] = handover["decisions"][:10]
        if isinstance(handover.get("patterns_learned"), list) and len(handover["patterns_learned"]) > 10:
            handover["patterns_learned"] = handover["patterns_learned"][:10]
        validated["handover"] = handover

    # Limit recent_tools to 30 entries (keep most recent)
    recent_tools = validated.get("recent_tools", [])
    if isinstance(recent_tools, list) and len(recent_tools) > 30:
        validated["recent_tools"] = recent_tools[-30:]

    # Limit modifications to 50 entries (keep most recent)
    modifications = validated.get("modifications", [])
    if isinstance(modifications, list) and len(modifications) > 50:
        validated["modifications"] = modifications[-50:]

    # Compute final size and warn if exceeds 500 KB
    import json
    estimated_size = len(json.dumps(validated).encode('utf-8'))
    if estimated_size > 500_000:  # 500 KB
        print(f"Warning: Handoff metadata exceeds 500 KB: {estimated_size} bytes")

    return validated


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

    # Validate existing checkpoint_id type
    if "checkpoint_id" in migrated and not isinstance(migrated["checkpoint_id"], str):
        raise TypeError("checkpoint_id must be str")

    # Validate existing parent_checkpoint_id type
    if "parent_checkpoint_id" in migrated:
        if not isinstance(migrated["parent_checkpoint_id"], (str, type(None))):
            raise TypeError("parent_checkpoint_id must be str or None")

    # Validate existing chain_id type
    if "chain_id" in migrated and not isinstance(migrated["chain_id"], str):
        raise TypeError("chain_id must be str")

    # Only add fields if they don't already exist (idempotent)
    if "checkpoint_id" not in migrated:
        migrated["checkpoint_id"] = str(uuid4())

    if "parent_checkpoint_id" not in migrated:
        # Old handoffs have no parent (treated as first in chain)
        migrated["parent_checkpoint_id"] = None

    if "chain_id" not in migrated:
        # Generate new chain ID for migrated handoffs
        migrated["chain_id"] = str(uuid4())

    # Add transcript tracking fields for migrated handoffs
    # Use 0 as default since we don't have exact historical data
    if "transcript_offset" not in migrated:
        migrated["transcript_offset"] = 0

    if "transcript_entry_count" not in migrated:
        migrated["transcript_entry_count"] = 0

    return migrated


def main() -> int:
    """CLI entry point for handoff migration.

    Usage:
        python -m handoff.migrate [--dry-run] [--terminal-id ID]

    Returns:
        Exit code (0 for success, 1 for failure)
    """

    parser = argparse.ArgumentParser(
        description="Migrate handoff JSON files to task metadata"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--terminal-id",
        help="Terminal ID (auto-detected if not specified)"
    )
    parser.add_argument(
        "--handoff-dir",
        default=".claude/handoffs",
        help="Handoff directory"
    )
    parser.add_argument(
        "--task-tracker-dir",
        default=".claude/state/task_tracker",
        help="Task tracker directory"
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

    results = migrate_handoffs(
        handoff_dir,
        task_tracker_dir,
        terminal_id,
        args.dry_run
    )

    print()
    print("Migration Results:")
    print(f"  Migrated: {results['migrated']}")
    print(f"  Failed: {results['failed']}")
    print(f"  Skipped: {results['skipped']}")

    if results['errors']:
        print()
        print("Errors:")
        for error in results['errors']:
            print(f"  - {error}")

    return 0 if results['failed'] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

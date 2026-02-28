"""Checkpoint chain traversal utilities.

This module provides the CheckpointChain class for traversing
chains of related handoff checkpoints linked by parent/child relationships.

Usage:
    from handoff.checkpoint_chain import CheckpointChain

    chain = CheckpointChain(task_tracker_dir, terminal_id)
    checkpoints = chain.get_chain(chain_id)
    latest = chain.get_latest(chain_id)
    length = chain.get_chain_length(chain_id)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from handoff.migrate import migrate_checkpoint_chain_fields


@dataclass(slots=True)
class HandoffCheckpointRef:
    """Reference to a handoff checkpoint.

    A lightweight reference for chain traversal without loading full handoff data.

    Attributes:
        checkpoint_id: Unique checkpoint identifier
        parent_checkpoint_id: Parent checkpoint ID (null for first)
        chain_id: Chain identifier grouping related checkpoints
        task_id: Task ID where checkpoint is stored
        created_at: ISO timestamp when checkpoint was created
        transcript_offset: Character position in transcript (if available)
        transcript_entry_count: Number of entries in transcript (if available)
    """
    checkpoint_id: str
    parent_checkpoint_id: str | None
    chain_id: str
    task_id: str
    created_at: str
    transcript_offset: int = 0
    transcript_entry_count: int = 0

    @classmethod
    def from_task_metadata(cls, task_id: str, metadata: dict[str, Any]) -> HandoffCheckpointRef:
        """Create checkpoint reference from task metadata.

        Args:
            task_id: Task identifier
            metadata: Task metadata dict containing handoff

        Returns:
            HandoffCheckpointRef instance
        """
        handoff = metadata.get("handoff", {})
        return cls(
            checkpoint_id=handoff.get("checkpoint_id", ""),
            parent_checkpoint_id=handoff.get("parent_checkpoint_id"),
            chain_id=handoff.get("chain_id", ""),
            task_id=task_id,
            created_at=handoff.get("saved_at", metadata.get("created_at", "")),
            transcript_offset=handoff.get("transcript_offset", 0),
            transcript_entry_count=handoff.get("transcript_entry_count", 0),
        )


class CheckpointChain:
    """Utilities for traversing checkpoint chains.

    Provides methods to retrieve and navigate through chains of related
    handoff checkpoints linked by parent/child relationships.
    """

    def __init__(self, task_tracker_dir: Path, terminal_id: str):
        """Initialize checkpoint chain utilities.

        Args:
            task_tracker_dir: Directory containing task tracker JSON files
            terminal_id: Terminal identifier for task isolation
        """
        self.task_tracker_dir = task_tracker_dir
        self.terminal_id = terminal_id
        self._cache: dict[str, list[HandoffCheckpointRef]] = {}
        self._cache_mtime: float = 0.0
        self._migration_cache: dict[str, dict[str, Any]] = {}
        self._migration_lock = __import__('threading').Lock()

    def _get_task_file_path(self) -> Path:
        """Get the task file path for this terminal.

        Returns:
            Path to the task tracker JSON file
        """
        return self.task_tracker_dir / f"{self.terminal_id}_tasks.json"

    def _load_all_checkpoints(self) -> list[HandoffCheckpointRef]:
        """Load all checkpoint references from task tracker.

        Returns:
            List of checkpoint references sorted by created_at

        Note:
            Applies migration to old format handoffs that don't have checkpoint_id.
            Uses migration cache to ensure consistent chain_ids across calls.
            Invalidates cache when task file is modified.
        """
        task_file = self._get_task_file_path()
        if not task_file.exists():
            return []

        # Check if cache is valid (file hasn't been modified)
        current_mtime = task_file.stat().st_mtime
        if current_mtime != self._cache_mtime:
            # File was modified, clear cache
            self._cache.clear()
            self._cache_mtime = current_mtime

        try:
            with open(task_file, encoding="utf-8") as f:
                task_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return []

        checkpoints = []
        for task_id, task in task_data.get("tasks", {}).items():
            metadata = task.get("metadata", {})
            if "handoff" in metadata:
                handoff = metadata["handoff"]

                # Migrate old format handoffs that don't have checkpoint_id
                if "checkpoint_id" not in handoff:
                    # Check migration cache first for consistency
                    if task_id in self._migration_cache:
                        migrated_handoff = self._migration_cache[task_id]
                    else:
                        # Apply migration with lock to prevent race conditions
                        with self._migration_lock:
                            # Double-check after acquiring lock
                            if task_id not in self._migration_cache:
                                migrated_handoff = migrate_checkpoint_chain_fields(handoff)
                                # Cache the migrated handoff for this session
                                self._migration_cache[task_id] = migrated_handoff
                            else:
                                migrated_handoff = self._migration_cache[task_id]

                    # Update metadata with migrated handoff for from_task_metadata
                    metadata = {**metadata, "handoff": migrated_handoff}

                # Get the (possibly migrated) handoff from metadata
                final_handoff = metadata.get("handoff", {})

                # After migration, all handoffs should have checkpoint_id
                if "checkpoint_id" in final_handoff:
                    checkpoints.append(
                        HandoffCheckpointRef.from_task_metadata(task_id, metadata)
                    )

        # Sort by created_at (oldest first)
        checkpoints.sort(key=lambda c: c.created_at)
        return checkpoints

    def get_chain(self, chain_id: str) -> list[HandoffCheckpointRef]:
        """Get all checkpoints in a chain, ordered oldest to newest.

        Args:
            chain_id: Chain identifier

        Returns:
            List of checkpoint references in chronological order
        """
        # Use cache if available
        if chain_id in self._cache:
            return self._cache[chain_id]

        checkpoints = self._load_all_checkpoints()
        chain_checkpoints = [c for c in checkpoints if c.chain_id == chain_id]

        # Cache for future access
        self._cache[chain_id] = chain_checkpoints
        return chain_checkpoints

    def get_latest(self, chain_id: str) -> HandoffCheckpointRef | None:
        """Get the newest checkpoint in a chain.

        Args:
            chain_id: Chain identifier

        Returns:
            Newest checkpoint reference or None if chain not found
        """
        chain = self.get_chain(chain_id)
        return chain[-1] if chain else None

    def get_previous(self, checkpoint_id: str) -> HandoffCheckpointRef | None:
        """Get the previous checkpoint in chain.

        Args:
            checkpoint_id: Current checkpoint identifier

        Returns:
            Previous checkpoint reference or None if not found
        """
        checkpoints = self._load_all_checkpoints()

        # Find the current checkpoint
        current = next((c for c in checkpoints if c.checkpoint_id == checkpoint_id), None)
        if not current:
            return None

        # Find checkpoint with matching parent (the child before current in chain)
        # Since checkpoints are sorted by created_at, the previous one in same chain is the parent
        chain_checkpoints = [c for c in checkpoints if c.chain_id == current.chain_id]
        for i, cp in enumerate(chain_checkpoints):
            if cp.checkpoint_id == checkpoint_id and i > 0:
                return chain_checkpoints[i - 1]

        return None

    def get_chain_length(self, chain_id: str) -> int:
        """Get the number of checkpoints in a chain.

        Args:
            chain_id: Chain identifier

        Returns:
            Number of checkpoints in the chain
        """
        chain = self.get_chain(chain_id)
        return len(chain)

    def invalidate_cache(self, chain_id: str | None = None) -> None:
        """Invalidate cache for a chain or all chains.

        Args:
            chain_id: Specific chain to invalidate, or None to invalidate all

        Example:
            Invalidate all caches after creating a new checkpoint:
                chain_manager.invalidate_cache()
        """
        if chain_id:
            self._cache.pop(chain_id, None)
        else:
            self._cache.clear()

    def get_next(self, checkpoint_id: str) -> HandoffCheckpointRef | None:
        """Get the next checkpoint in chain (if any).

        Args:
            checkpoint_id: Current checkpoint identifier

        Returns:
            Next checkpoint reference or None if not found
        """
        checkpoints = self._load_all_checkpoints()

        # Find the current checkpoint
        current = next((c for c in checkpoints if c.checkpoint_id == checkpoint_id), None)
        if not current:
            return None

        # Find checkpoint that has current as parent
        for cp in checkpoints:
            if cp.parent_checkpoint_id == checkpoint_id:
                return cp

        return None

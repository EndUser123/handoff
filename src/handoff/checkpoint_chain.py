"""Checkpoint chain traversal utilities.

This module provides the CheckpointChain class for traversing
chains of related handoff checkpoints linked by parent/child relationships.

Usage:
    from handoff.checkpoint_chain import CheckpointChain

    chain = CheckpointChain(task_tracker_dir, terminal_id)
    checkpoints = chain.get_chain(chain_id)
    latest = chain.get_latest(chain_id)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
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
        """
        task_file = self._get_task_file_path()
        if not task_file.exists():
            return []

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
                if "checkpoint_id" in handoff:
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

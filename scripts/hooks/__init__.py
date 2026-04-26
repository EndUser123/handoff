"""
Snapshot hooks for Claude Code integration.

This module contains Claude Code hook files that integrate with
the snapshot package.

Hooks:
    PreCompact_snapshot_capture.py: Captures snapshot before transcript compaction
    SessionStart_snapshot_restore.py: Restores snapshot on session start

These hooks are registered in settings.json and called by Claude Code's hook system.

Note: SnapshotManager, SnapshotPayload, TaskType, CommandContext have been removed.
Snapshot data is now stored in task metadata.
"""

from scripts.hooks.__lib.snapshot_store import (
    SnapshotStore,
    atomic_write_with_retry,
    atomic_write_with_validation,
)
from scripts.hooks.__lib.handover import HandoverBuilder
from scripts.hooks.__lib.task_identity_manager import TaskIdentityManager
from scripts.hooks.__lib.transcript import TranscriptLines, TranscriptParser

__all__ = [
    "SnapshotStore",
    "HandoverBuilder",
    "TaskIdentityManager",
    "TranscriptParser",
    "TranscriptLines",
    "atomic_write_with_retry",
    "atomic_write_with_validation",
]

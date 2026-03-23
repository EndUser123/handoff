"""
Handoff hooks for Claude Code integration.

This module contains Claude Code hook files that integrate with
the handoff package.

Hooks:
    PreCompact_handoff_capture.py: Captures handoff before transcript compaction
    SessionStart_handoff_restore.py: Restores handoff on session start

These hooks are registered in settings.json and called by Claude Code's hook system.

Note: HandoffManager, HandoffPayload, TaskType, CommandContext have been removed.
Handoff data is now stored in task metadata.
"""

from handoff.hooks.__lib.handoff_store import (
    HandoffStore,
    atomic_write_with_retry,
    atomic_write_with_validation,
)
from handoff.hooks.__lib.handover import HandoverBuilder
from handoff.hooks.__lib.task_identity_manager import TaskIdentityManager
from handoff.hooks.__lib.transcript import TranscriptLines, TranscriptParser

__all__ = [
    "HandoffStore",
    "HandoverBuilder",
    "TaskIdentityManager",
    "TranscriptParser",
    "TranscriptLines",
    "atomic_write_with_retry",
    "atomic_write_with_validation",
]

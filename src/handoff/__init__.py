"""
Handoff - Session handoff management for AI coding environments.

Provides capture, restore, and management of conversation state with:
- Task-based handoff storage (consolidated with task tracker)
- SHA256-validated handoff metadata
- Terminal-aware task isolation
- Automatic migration from legacy JSON file storage

Note: HandoffManager has been removed. Handoff data is now stored
directly in task tracker metadata, eliminating dual storage redundancy.

The dataclasses previously in manager.py (HandoffPayload, TaskType, CommandContext)
are no longer needed as handoff metadata is stored directly in task metadata.
"""

from __future__ import annotations

from handoff.migrate import compute_metadata_checksum, validate_handoff_size
from handoff.protocol import HandoffStorage

__all__ = [
    "HandoffStorage",
    "compute_metadata_checksum",
    "validate_handoff_size",
]

__version__ = "0.2.0"

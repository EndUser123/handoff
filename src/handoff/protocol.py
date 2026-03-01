#!/usr/bin/env python3
"""
HandoffStorage Protocol - Type-safe interface for handoff storage systems.

This protocol defines the storage contract for handoff persistence,
enabling type safety, mocking, and multiple storage backend implementations.

Purpose:
- Type safety through Protocol interface
- Mocking for tests without real file I/O
- Multiple storage backend implementations (filesystem, S3, database, etc.)

Usage:
    from pathlib import Path
    from typing import runtime_checkable

    @runtime_checkable
    class HandoffStorage(Protocol):
        def save_handoff(self, task_name: str, terminal_id: str, data: dict[str, Any]) -> Path: ...
        def load_handoff(self, task_name: str, terminal_id: str, strict: bool =
            True) -> dict | None: ...        def list_handoffs(self, task_name: str, terminal_id: str) -> list[Path]: ...
        def delete_handoff(self, task_name: str, terminal_id: str, version: int) -> bool: ...

    # Check if an object implements the protocol
    assert isinstance(manager, HandoffStorage)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class HandoffStorage(Protocol):
    """
    Protocol defining handoff storage interface.

    This protocol defines the contract for handoff persistence systems,
    ensuring type safety and enabling multiple storage backends.

    Methods:
        save_handoff: Save handoff data, return file path.
        load_handoff: Load handoff data, returns None if not found.
        list_handoffs: List all handoff versions for task.
        delete_handoff: Delete specific handoff version, returns True if deleted.

    Example:
        # Any class implementing these methods satisfies the protocol
        class TaskTrackerStorage:
            def save_handoff(self, task_name: str, terminal_id: str, data: dict[str, Any]) -> Path: ...
            def load_handoff(self, task_name: str, terminal_id: str, strict: bool =
                True) -> dict | None: ...            # ... other methods

        storage = TaskTrackerStorage()
        assert isinstance(storage, HandoffStorage)  # Runtime check

        # Type checker knows storage has these methods
        path = storage.save_handoff("task", "term", {"data": "value"})
    """

    def save_handoff(self, task_name: str, terminal_id: str, data: dict[str, Any]) -> Path:
        """
        Save handoff data to storage.

        Args:
            task_name: Task identifier for the handoff.
            terminal_id: Terminal identifier for isolation.
            data: Dictionary containing handoff data.

        Returns:
            Path to the saved handoff file.

        Raises:
            ValueError: If data validation fails.
            IOError: If write operation fails.
        """
        ...

    def load_handoff(self, task_name: str, terminal_id: str, strict: bool = True) -> dict[str, Any] | None:
        """
        Load handoff data from storage.

        Args:
            task_name: Task identifier for the handoff.
            terminal_id: Terminal identifier for isolation.
            strict: If True, raise exception on validation error.
                    If False, return None or partial data on error.

        Returns:
            Handoff data dictionary, or None if not found.

        Raises:
            ValueError: If checksum validation fails (when strict=True).
        """
        ...

    def list_handoffs(self, task_name: str, terminal_id: str) -> list[Path]:
        """
        List all handoff versions for a task.

        Args:
            task_name: Task identifier to filter by.
            terminal_id: Terminal identifier to filter by.

        Returns:
            List of Path objects for handoff files, sorted by version descending.
        """
        ...

    def delete_handoff(self, task_name: str, terminal_id: str, version: int) -> bool:
        """
        Delete a specific handoff version.

        Args:
            task_name: Task identifier for the handoff.
            terminal_id: Terminal identifier for isolation.
            version: Handoff version number to delete.

        Returns:
            True if handoff was deleted, False if not found.
        """
        ...

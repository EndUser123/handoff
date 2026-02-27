"""Checkpoint operation tracking for fault tolerance.

This module provides the PendingOperation dataclass for tracking
operations that were in progress at checkpoint time. This enables
recovery of interrupted work after compaction or session restart.

Usage:
    from handoff.checkpoint_ops import PendingOperation

    op = PendingOperation(
        type="edit",
        target="src/main.py",
        state="in_progress",
        details={"line": 42, "change": "fix bug"}
    )
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal


@dataclass
class PendingOperation:
    """An operation that was in progress at checkpoint time.

    This represents a tool call, file operation, or other action that was
    interrupted or in progress when the checkpoint was captured. It enables
    recovery and resumption of incomplete work.

    Attributes:
        type: The type of operation (edit, test, read, command, skill)
        target: The target of the operation (file path, test name, etc.)
        state: The current state (pending, in_progress, failed)
        details: Additional details about the operation
        started_at: ISO timestamp when operation started (optional)

    Example:
        >>> op = PendingOperation(
        ...     type="edit",
        ...     target="src/main.py",
        ...     state="in_progress",
        ...     details={"line": 42}
        ... )
        >>> op.to_dict()
        {'type': 'edit', 'target': 'src/main.py', 'state': 'in_progress',
         'details': {'line': 42}, 'started_at': None}
    """

    type: Literal["edit", "test", "read", "command", "skill"]
    target: str
    state: Literal["pending", "in_progress", "failed"]
    details: dict[str, Any]
    started_at: str | None = None

    def __post_init__(self):
        """Validate target field after initialization."""
        if isinstance(self.target, str):
            self._validate_target(self.target)

    def _validate_target(self, target: str):
        """Validate target field.

        Args:
            target: The target string to validate

        Raises:
            ValueError: If target is invalid
        """
        # Check for empty or whitespace-only strings
        if not target or len(target.strip()) == 0:
            raise ValueError("target cannot be empty or whitespace-only")

        # Check for null bytes (security risk)
        if "\x00" in target:
            raise ValueError("target cannot contain null bytes")

        # Check length (filesystem limit)
        if len(target) > 255:
            raise ValueError("target cannot exceed 255 characters")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization.

        Returns:
            Dictionary representation suitable for JSON encoding
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PendingOperation:
        """Load from dict with validation.

        Args:
            data: Dictionary containing pending operation data

        Returns:
            PendingOperation instance

        Raises:
            ValueError: If required fields are missing or invalid
        """
        # Validate required fields
        if "type" not in data or "target" not in data or "state" not in data:
            raise ValueError("Missing required fields: type, target, state")

        # Validate target field
        target = data["target"]
        if target is None:
            raise ValueError("target cannot be None")
        if not isinstance(target, str):
            raise ValueError("target must be a string")

        # Create instance to trigger validation via __post_init__
        return cls(
            type=data["type"],
            target=target,
            state=data["state"],
            details=data.get("details", {}),
            started_at=data.get("started_at"),
        )

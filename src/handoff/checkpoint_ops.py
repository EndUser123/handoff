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


@dataclass(slots=True)
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

    # Class constants
    MAX_TARGET_LENGTH: int = 255  # Filesystem NAME_MAX limit
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
    state: Literal["pending", "in_progress", "completed", "failed"]
    details: dict[str, Any]
    started_at: str | None = None

    def __post_init__(self):
        """Validate the target field after initialization.

        This validation runs automatically when a PendingOperation is instantiated
        via the constructor. Validation ensures the target meets filesystem and
        security constraints before the object is considered valid.

        Note:
            Validation occurs only for direct constructor instantiation. When loading
            from dict via from_dict(), that method handles validation separately.

        Raises:
            ValueError: If target field violates validation rules (empty, too long,
                        or contains null bytes)
        """
        if isinstance(self.target, str):
            self._validate_target(self.target)

    @staticmethod
    def _validate_target(target: str) -> None:
        """Validate the target field against filesystem and security constraints.

        This method enforces three critical validation rules to ensure targets are
        safe for filesystem operations and free from security vulnerabilities.

        Validation Rules:
            1. **Non-empty**: Targets must contain at least one non-whitespace character.
               Empty or whitespace-only targets indicate missing or invalid data and are
               rejected to prevent ambiguous operations.

            2. **No null bytes**: Null bytes (\\x00) are strictly prohibited. These can be
               used in path traversal attacks (e.g., "safe.txt\\x00malicious.py") to bypass
               file extension checks on some systems. Rejecting them prevents exploitation
               of C string termination semantics in underlying filesystem calls.

            3. **Length limit**: Targets cannot exceed 255 characters. This aligns with the
               MAX_PATH limits on many filesystems (POSIX NAME_MAX, Windows historical
               limits). Paths exceeding this may fail silently or cause truncation,
               leading to data loss or incorrect operation targeting.

        Args:
            target: The target string to validate (typically a file path, test name,
                    or operation identifier)

        Raises:
            ValueError: If target is empty/whitespace-only, contains null bytes, or
                        exceeds 255 characters. Error messages indicate specific failure.

        Examples:
            >>> PendingOperation._validate_target("src/main.py")  # Valid
            >>> PendingOperation._validate_target("")  # Raises ValueError
            >>> PendingOperation._validate_target("test\\x00.py")  # Raises ValueError
            >>> PendingOperation._validate_target("a" * 300)  # Raises ValueError
        """
        # Check for empty or whitespace-only strings
        # Empty targets indicate missing/invalid data and would lead to ambiguous operations
        if not target or len(target.strip()) == 0:
            raise ValueError("target cannot be empty or whitespace-only")

        # Check for null bytes (security risk)
        # Null bytes can be used in path traversal attacks to bypass file extension checks
        # Example: "safe.txt\x00malicious.py" may be treated as "safe.txt" by some APIs
        if "\x00" in target:
            raise ValueError("target cannot contain null bytes")

        # Check length (filesystem limit)
        if len(target) > cls.MAX_TARGET_LENGTH:
            raise ValueError(
                f"target cannot exceed {cls.MAX_TARGET_LENGTH} characters"
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization.

        Returns:
            Dictionary representation suitable for JSON encoding
        """
        return asdict(self)

    def transition_to(self, new_state: str) -> None:
        """Transition to a new state with validation.

        Args:
            new_state: The target state to transition to

        Raises:
            ValueError: If the transition is invalid or state is unknown

        Valid transitions:
            - pending -> in_progress
            - in_progress -> completed
            - in_progress -> failed
        """
        valid_states = {"pending", "in_progress", "completed", "failed"}
        if new_state not in valid_states:
            raise ValueError(f"Invalid state: {new_state}. Must be one of {valid_states}")

        if self.state == new_state:
            raise ValueError(f"Invalid state transition: already in {new_state} state")

        # Define valid transitions
        valid_transitions = {
            "pending": {"in_progress"},
            "in_progress": {"completed", "failed"},
            "completed": set(),  # No transitions out of completed
            "failed": set(),  # No transitions out of failed
        }

        # Validate current state before checking transitions
        if self.state not in valid_transitions:
            raise ValueError(
                f"Invalid current state: {self.state}. Must be one of {list(valid_transitions.keys())}"
            )

        if new_state not in valid_transitions[self.state]:
            raise ValueError(
                f"Invalid state transition: cannot transition from {self.state} to {new_state}"
            )

        self.state = new_state

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
        cls._validate_target(target)

        # Validate type field
        valid_types = {"edit", "test", "read", "command", "skill"}
        if data["type"] not in valid_types:
            raise ValueError(f"Invalid type: {data['type']}. Must be one of {valid_types}")

        # Validate state field
        valid_states = {"pending", "in_progress", "completed", "failed"}
        if data["state"] not in valid_states:
            raise ValueError(f"Invalid state: {data['state']}. Must be one of {valid_states}")

        return cls(
            type=data["type"],
            target=target,
            state=data["state"],
            details=data.get("details", {}),
            started_at=data.get("started_at"),
        )

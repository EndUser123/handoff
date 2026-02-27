"""Typed dataclass models for handoff data validation.

This module provides Pydantic-style dataclass models for handoff data
with type validation and serialization support.

Usage:
    from handoff.models import HandoffCheckpoint, PendingOperation

    checkpoint = HandoffCheckpoint.from_dict(handoff_data)
    print(checkpoint.checkpoint_id)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass
class PendingOperation:
    """An operation that was in progress at checkpoint time.

    This represents a tool call, file operation, or other action that was
    interrupted or in progress when the checkpoint was captured.

    Attributes:
        type: The type of operation (edit, test, read, command, skill)
        target: The target of the operation (file path, test name, etc.)
        state: The current state (pending, in_progress, failed)
        details: Additional details about the operation
        started_at: ISO timestamp when operation started (optional)
    """

    type: Literal["edit", "test", "read", "command", "skill"]
    target: str
    state: Literal["pending", "in_progress", "failed"]
    details: dict[str, Any] = field(default_factory=dict)
    started_at: str | None = None

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

        # Validate type field
        valid_types = {"edit", "test", "read", "command", "skill"}
        if data["type"] not in valid_types:
            raise ValueError(f"Invalid type: {data['type']}. Must be one of {valid_types}")

        # Validate state field
        valid_states = {"pending", "in_progress", "failed"}
        if data["state"] not in valid_states:
            raise ValueError(f"Invalid state: {data['state']}. Must be one of {valid_states}")

        return cls(
            type=data["type"],
            target=data["target"],
            state=data["state"],
            details=data.get("details", {}),
            started_at=data.get("started_at"),
        )


@dataclass
class HandoffCheckpoint:
    """Typed handoff checkpoint with chain links.

    This model provides type-safe access to handoff checkpoint data
    with validation and serialization support.

    Attributes:
        checkpoint_id: Unique checkpoint identifier
        parent_checkpoint_id: Parent checkpoint ID (null for first)
        chain_id: Chain identifier grouping related checkpoints
        created_at: ISO timestamp when checkpoint was created
        transcript_offset: Character position in transcript for exact resume
        transcript_entry_count: Number of entries in transcript at checkpoint time
        task_name: Name of task being worked on
        task_type: Type of task (informal, formal, etc.)
        progress_percent: Progress percentage (0-100)
        blocker: Current blocker dict with description
        next_steps: Next steps as newline-separated string
        git_branch: Git branch name
        active_files: List of active file paths
        recent_tools: List of recent tool invocations
        transcript_path: Path to transcript file
        handover: Handover data dict with decisions and patterns
        open_conversation_context: Open conversation context dict
        visual_context: Visual context dict with description
        resolved_issues: List of resolved issue dicts
        modifications: List of file modification dicts
        original_user_request: The last user message
        first_user_request: The first user message
        saved_at: ISO timestamp when saved
        version: Handoff format version
        implementation_status: Implementation status dict
        pending_operations: List of incomplete operations
        checksum: SHA256 checksum for data integrity
    """

    # Checkpoint chain fields
    checkpoint_id: str
    parent_checkpoint_id: str | None
    chain_id: str

    # Resume capability
    created_at: str
    transcript_offset: int
    transcript_entry_count: int

    # Existing fields (migrated)
    task_name: str
    task_type: str
    progress_percent: int
    blocker: dict[str, Any] | None
    next_steps: str
    git_branch: str | None
    active_files: list[str]
    recent_tools: list[dict[str, Any]]
    transcript_path: str | None
    handover: dict[str, Any] | None
    open_conversation_context: dict[str, Any] | None
    visual_context: dict[str, Any] | None
    resolved_issues: list[dict[str, Any]]
    modifications: list[dict[str, Any]]
    original_user_request: str | None
    first_user_request: str | None
    saved_at: str
    version: int
    implementation_status: dict[str, Any] | None

    # NEW: Fault tolerance
    pending_operations: list[PendingOperation]

    # Validation
    checksum: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for storage.

        Returns:
            Dictionary representation suitable for JSON serialization
        """
        result = asdict(self)
        # Convert PendingOperation objects to dicts
        result["pending_operations"] = [
            op.to_dict() if isinstance(op, PendingOperation) else op
            for op in self.pending_operations
        ]
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HandoffCheckpoint:
        """Load from dict with validation.

        Args:
            data: Dictionary containing handoff checkpoint data

        Returns:
            HandoffCheckpoint instance

        Raises:
            ValueError: If required fields are missing or invalid
        """
        # Validate required fields
        required_fields = [
            "checkpoint_id", "chain_id", "created_at",
            "task_name", "task_type", "progress_percent",
            "next_steps", "active_files", "recent_tools",
            "saved_at", "version", "checksum"
        ]
        missing = [f for f in required_fields if f not in data]
        if missing:
            raise ValueError(f"Missing required fields: {missing}")

        # Validate checksum format
        checksum = data["checksum"]
        if not checksum.startswith("sha256:"):
            raise ValueError("Invalid checksum format: must start with 'sha256:'")
        hex_part = checksum[7:]  # Remove "sha256:" prefix
        if len(hex_part) != 64:
            raise ValueError("Invalid checksum: must be 64 hexadecimal characters after 'sha256:' prefix")
        valid_hex_chars = set("0123456789abcdef")
        if not all(c in valid_hex_chars for c in hex_part):
            raise ValueError("Invalid checksum: must contain only hexadecimal characters (0-9, a-f)")

        # Validate progress_percent range (0-100)
        progress_percent = data["progress_percent"]
        if progress_percent is not None and (progress_percent < 0 or progress_percent > 100):
            raise ValueError(f"progress_percent must be between 0 and 100, got {progress_percent}")

        # Convert pending_operations dicts to PendingOperation objects
        pending_ops = []
        for op_data in data.get("pending_operations", []):
            if isinstance(op_data, dict):
                pending_ops.append(PendingOperation.from_dict(op_data))
            elif isinstance(op_data, PendingOperation):
                pending_ops.append(op_data)

        return cls(
            # Checkpoint chain fields
            checkpoint_id=data["checkpoint_id"],
            parent_checkpoint_id=data.get("parent_checkpoint_id"),
            chain_id=data["chain_id"],
            created_at=data["created_at"],
            transcript_offset=data.get("transcript_offset", 0),
            transcript_entry_count=data.get("transcript_entry_count", 0),
            # Existing fields
            task_name=data["task_name"],
            task_type=data["task_type"],
            progress_percent=data["progress_percent"],
            blocker=data.get("blocker"),
            next_steps=data["next_steps"],
            git_branch=data.get("git_branch"),
            active_files=data.get("active_files", []),
            recent_tools=data.get("recent_tools", []),
            transcript_path=data.get("transcript_path"),
            handover=data.get("handover"),
            open_conversation_context=data.get("open_conversation_context"),
            visual_context=data.get("visual_context"),
            resolved_issues=data.get("resolved_issues", []),
            modifications=data.get("modifications", []),
            original_user_request=data.get("original_user_request"),
            first_user_request=data.get("first_user_request"),
            saved_at=data["saved_at"],
            version=data["version"],
            implementation_status=data.get("implementation_status"),
            # NEW: Fault tolerance
            pending_operations=pending_ops,
            # Validation
            checksum=data["checksum"],
        )

"""Shared validation utilities for handoff components."""

from __future__ import annotations


def validate_terminal_id(terminal_id: str) -> None:
    """Validate terminal_id to prevent security issues.

    Checks:
    - Reject empty or whitespace-only strings
    - Reject null bytes (null byte injection)
    - Reject path traversal patterns (../, ./)
    - Reject absolute paths

    Raises:
        ValueError: If terminal_id fails any validation check.
    """
    if not terminal_id or not terminal_id.strip():
        raise ValueError("terminal_id cannot be empty or whitespace-only")
    if "\x00" in terminal_id:
        raise ValueError("terminal_id cannot contain null bytes")
    if ".." in terminal_id or terminal_id.startswith("./"):
        raise ValueError("terminal_id cannot contain path traversal sequences")
    if terminal_id.startswith("/") or terminal_id.startswith("\\"):
        raise ValueError("terminal_id cannot be an absolute path")

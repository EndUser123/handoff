#!/usr/bin/env python3
"""
Hook Input Validation - Defensive layer for hook input contracts.

Prevents silent failures from field name mismatches or missing fields.
All field names are snake_case (not camelCase) per Claude Code conventions.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


# Hook input schemas based on Claude Code actual format
# All field names are snake_case (not camelCase)
HOOK_INPUT_SCHEMAS = {
    "PreCompact": {
        "required_fields": {
            "session_id": str,
            "transcript_path": str,  # NOT transcriptPath - snake_case only
            "cwd": str,
            "hook_event_name": str,
            "trigger": str,
        },
        "optional_fields": {
            "terminal_id": str,
            "test_mode": bool,  # When True, hook skips expensive operations (git, pip, pytest)
            # Future fields can be added here without breaking validation
        },
    },
    "SessionStart": {
        "required_fields": {
            "session_id": str,
            "cwd": str,
            "hook_event_name": str,
            "trigger": str,
        },
        "optional_fields": {
            "terminal_id": str,
            "source": str,
            "transcript_path": str,
        },
    },
}


class HookInputError(Exception):
    """Raised when hook input validation fails."""

    def __init__(self, message: str, field_name: str | None = None):
        super().__init__(message)
        self.field_name = field_name


def validate_hook_input(input_data: dict[str, Any], hook_type: str) -> None:
    """Validate hook input matches expected schema.

    Args:
        input_data: Raw hook input from Claude Code (via stdin)
        hook_type: Type of hook ("PreCompact" or "SessionStart")

    Raises:
        HookInputError: If validation fails with clear error message

    Side effects:
        Logs validated input for debugging (development mode only)
    """
    if hook_type not in HOOK_INPUT_SCHEMAS:
        raise HookInputError(f"Unknown hook type: {hook_type}")

    schema = HOOK_INPUT_SCHEMAS[hook_type]
    errors = []

    # Validate required fields
    for field_name, expected_type in schema["required_fields"].items():
        if field_name not in input_data:
            errors.append(f"Missing required field: '{field_name}'")
        elif not isinstance(input_data[field_name], expected_type):
            errors.append(
                f"Field '{field_name}' has wrong type: "
                f"expected {expected_type.__name__}, got {type(input_data[field_name]).__name__}"
            )

    # Warn about unknown fields (future-proofing)
    known_fields = set(schema["required_fields"]) | set(
        schema.get("optional_fields", {})
    )
    unknown_fields = set(input_data.keys()) - known_fields
    if unknown_fields:
        logger.info(
            f"[{hook_type}] Unknown fields in input (may be new Claude Code features): "
            f"{', '.join(sorted(unknown_fields))}"
        )

    if errors:
        error_message = f"Hook input validation failed for {hook_type}:\n" + "\n".join(
            f"  - {e}" for e in errors
        )

        # Log the actual input for debugging
        logger.error(f"[{hook_type}] {error_message}")
        logger.error(
            f"[{hook_type}] Actual input received:\n{json.dumps(input_data, indent=2)}"
        )

        raise HookInputError(error_message)

    # Log successful validation in debug mode
    logger.debug(f"[{hook_type}] Hook input validation passed")

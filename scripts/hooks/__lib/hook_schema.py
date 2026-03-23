"""Claude Code Hook JSON Schema Constants and Validators.

This module defines the authoritative schema for hook JSON output.
Values are derived from Claude Code's actual validation requirements.

IMPORTANT: When Claude Code rejects hook output with "Invalid input", it shows
the expected schema. Use that schema to keep these constants synchronized.

Usage:
    from scripts.hooks.__lib.hook_schema import (
        DECISION_APPROVE,
        DECISION_BLOCK,
        validate_hook_output,
    )

    # Correct - use constants
    output = {"decision": DECISION_APPROVE, "reason": "..."}

    # Wrong - magic strings
    output = {"decision": "allow", ...}  # ❌ Schema-invalid!
"""

from __future__ import annotations

from typing import Any

# =============================================================================
# DECISION FIELD VALUES
# =============================================================================

# Valid values for the "decision" field in hook JSON output.
# These are the ONLY valid values - Claude Code will reject anything else.
#
# Historical bug: Hooks used "allow" which is semantically intuitive but
# schema-invalid. The valid values are "approve" and "block" specifically.
DECISION_APPROVE = "approve"  # Hook allows the action to proceed
DECISION_BLOCK = "block"  # Hook blocks the action


# =============================================================================
# SCHEMA VALIDATION
# =============================================================================

# Valid decision values as a set for O(1) lookup
VALID_DECISIONS = {DECISION_APPROVE, DECISION_BLOCK}


def validate_hook_output(
    output: dict[str, Any], hook_type: str = "generic"
) -> list[str]:
    """Validate hook JSON output against Claude Code schema.

    Args:
        output: The hook output dictionary to validate
        hook_type: Type of hook (e.g., "PreCompact", "SessionStart")

    Returns:
        List of validation errors (empty if valid)

    Example:
        errors = validate_hook_output({"decision": "allow"}, "PreCompact")
        # errors = ["Invalid decision 'allow'. Must be one of: approve, block"]
    """
    errors: list[str] = []

    # Validate decision field if present
    if "decision" in output:
        decision = output["decision"]
        if decision not in VALID_DECISIONS:
            errors.append(
                f"Invalid decision '{decision}'. Must be one of: {', '.join(sorted(VALID_DECISIONS))}"
            )

    # Validate required fields based on hook type
    if hook_type in ("PreCompact", "SessionStart"):
        if "reason" not in output:
            errors.append(f"Missing required field 'reason' for {hook_type} hook")

    return errors


def assert_valid_hook_output(
    output: dict[str, Any], hook_type: str = "generic"
) -> None:
    """Assert that hook output is valid. Raises AssertionError if not.

    Use in tests to catch schema violations early.

    Args:
        output: The hook output dictionary to validate
        hook_type: Type of hook

    Raises:
        AssertionError: If output violates schema
    """
    errors = validate_hook_output(output, hook_type)
    if errors:
        raise AssertionError(
            "Hook output schema validation failed:\n  - " + "\n  - ".join(errors)
        )


# =============================================================================
# SCHEMA DOCUMENTATION
# =============================================================================

# The full schema as documented by Claude Code error messages.
# This is for reference - actual validation uses the constants above.
HOOK_OUTPUT_SCHEMA = """
{
  "continue": "boolean (optional)",
  "suppressOutput": "boolean (optional)",
  "stopReason": "string (optional)",
  "decision": "approve | block (optional)",
  "reason": "string (optional)",
  "systemMessage": "string (optional)",
  "permissionDecision": "allow | deny | ask (optional)",
  "hookSpecificOutput": {
    "for PreToolUse": {
      "hookEventName": "PreToolUse",
      "permissionDecision": "allow | deny | ask (optional)",
      "permissionDecisionReason": "string (optional)",
      "updatedInput": "object (optional)"
    },
    "for UserPromptSubmit": {
      "hookEventName": "UserPromptSubmit",
      "additionalContext": "string (required)"
    },
    "for PostToolUse": {
      "hookEventName": "PostToolUse",
      "additionalContext": "string (optional)"
    }
  }
}
"""

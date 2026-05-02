"""Tests for hook JSON schema validation.

This test module validates hook output against Claude Code's actual JSON schema.
It catches the "allow vs approve" class of bugs where implementation uses
semantically intuitive but schema-invalid values.

Run with: pytest scripts/tests/test_hook_schema_validation.py -v
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Add package root to path
package_root = Path(__file__).resolve().parents[2]
if str(package_root) not in sys.path:
    sys.path.insert(0, str(package_root))

# Register meta path finder for core.hooks.* imports
import core.hooks.__lib  # noqa: F401

from core.hooks.__lib.hook_schema import (
    DECISION_APPROVE,
    DECISION_BLOCK,
    VALID_DECISIONS,
    assert_valid_hook_output,
    validate_hook_output,
)


class TestHookSchemaConstants:
    """Test that schema constants are correct."""

    def test_approve_value_is_string(self):
        """Decision constant must be a string."""
        assert isinstance(DECISION_APPROVE, str)

    def test_block_value_is_string(self):
        """Decision constant must be a string."""
        assert isinstance(DECISION_BLOCK, str)

    def test_valid_decisions_set_contains_constants(self):
        """VALID_DECISIONS set must include both constants."""
        assert DECISION_APPROVE in VALID_DECISIONS
        assert DECISION_BLOCK in VALID_DECISIONS

    def test_valid_decisions_only_contains_known_values(self):
        """VALID_DECISIONS must only contain approved values."""
        assert VALID_DECISIONS == {"approve", "block"}


class TestSchemaValidation:
    """Test the validate_hook_output function."""

    def test_approve_decision_is_valid(self):
        """approve is a valid decision value."""
        errors = validate_hook_output({"decision": "approve"})
        assert errors == []

    def test_block_decision_is_valid(self):
        """block is a valid decision value."""
        errors = validate_hook_output({"decision": "block"})
        assert errors == []

    def test_allow_decision_is_invalid(self):
        """allow is NOT a valid decision value.

        This is the bug we're preventing - 'allow' is semantically intuitive
        but schema-invalid. Claude Code rejects it with "Invalid input".
        """
        errors = validate_hook_output({"decision": "allow"})
        assert len(errors) == 1
        assert "Invalid decision 'allow'" in errors[0]
        assert "approve" in errors[0]

    def test_unknown_decision_is_invalid(self):
        """Unknown values are invalid."""
        errors = validate_hook_output({"decision": "yes"})
        assert len(errors) == 1
        assert "Invalid decision 'yes'" in errors[0]

    def test_missing_decision_is_valid(self):
        """decision field is optional - missing is OK."""
        errors = validate_hook_output({"reason": "some reason"})
        assert errors == []

    def test_assert_valid_raises_on_invalid(self):
        """assert_valid_hook_output raises AssertionError for invalid output."""
        with pytest.raises(AssertionError) as exc_info:
            assert_valid_hook_output({"decision": "allow"})
        assert "schema validation failed" in str(exc_info.value).lower()
        assert "allow" in str(exc_info.value)


class TestActualHookOutputSchema:
    """Test that actual hooks produce schema-valid output.

    These tests run the real hooks with mock input and validate output.
    They catch the "allow vs approve" bug at the integration level.
    """

    @pytest.fixture
    def mock_transcript(self, tmp_path: Path) -> Path:
        """Create a minimal valid transcript for testing."""
        transcript = tmp_path / "test.jsonl"
        entries = [
            {"type": "user", "message": {"content": "Test goal for handoff"}},
            {"type": "assistant", "message": {"content": "Working on test"}},
        ]
        with open(transcript, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")
        return transcript

    def test_precompact_hook_output_is_schema_valid(
        self, tmp_path: Path, mock_transcript: Path
    ):
        """PreCompact hook must produce schema-valid JSON output.

        REGRESSION TEST: This test would have caught the "allow" bug.
        If the hook returns {"decision": "allow"}, this test fails.
        """
        payload = {
            "session_id": "test-session",
            "transcript_path": str(mock_transcript),
            "cwd": str(tmp_path),
            "hook_event_name": "PreCompact",
            "trigger": "manual",
        }

        result = subprocess.run(
            [
                sys.executable,
                str(package_root / "scripts/hooks/PreCompact_snapshot_capture.py"),
            ],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
        )

        # Parse and validate output
        output = json.loads(result.stdout)

        # This assertion catches "allow" vs "approve" bugs
        assert_valid_hook_output(output, hook_type="PreCompact")

        # Additional sanity checks
        assert output["decision"] in VALID_DECISIONS
        assert "reason" in output

    def test_session_start_hook_output_is_schema_valid(
        self, tmp_path: Path, mock_transcript: Path
    ):
        """SessionStart hook must produce schema-valid JSON output."""
        payload = {
            "session_id": "test-session",
            "transcript_path": str(mock_transcript),
            "cwd": str(tmp_path),
            "hook_event_name": "SessionStart",
            "trigger": "startup",
        }

        result = subprocess.run(
            [
                sys.executable,
                str(package_root / "scripts/hooks/SessionStart_snapshot_restore.py"),
            ],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
        )

        output = json.loads(result.stdout)

        # This assertion catches "allow" vs "approve" bugs
        assert_valid_hook_output(output, hook_type="SessionStart")


class TestNoMagicStringsInHooks:
    """Ensure hooks use schema constants, not magic strings.

    This catches the root cause: hardcoded strings instead of constants.
    """

    def test_precompact_uses_approve_constant(self):
        """PreCompact hook should import and use DECISION_APPROVE constant."""
        hook_path = package_root / "scripts/hooks/PreCompact_snapshot_capture.py"
        content = hook_path.read_text(encoding="utf-8")

        # Check for constant import
        assert "DECISION_APPROVE" in content or '"approve"' in content, (
            "Hook should either import DECISION_APPROVE constant or use "
            "the literal 'approve' (not 'allow')"
        )

        # Check for the bug pattern
        assert '"decision": "allow"' not in content, (
            "Hook uses schema-invalid 'allow' decision value. Use 'approve' instead."
        )

    def test_session_start_uses_approve_constant(self):
        """SessionStart hook should not use magic 'allow' string."""
        hook_path = package_root / "scripts/hooks/SessionStart_snapshot_restore.py"
        content = hook_path.read_text(encoding="utf-8")

        # Check for the bug pattern
        assert '"decision": "allow"' not in content, (
            "Hook uses schema-invalid 'allow' decision value. Use 'approve' instead."
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

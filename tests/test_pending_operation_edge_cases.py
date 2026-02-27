#!/usr/bin/env python3
"""Edge case tests for PendingOperation validation.

Tests edge cases and boundary conditions for PendingOperation:
- Empty target field handling
- Very long file paths (>255 chars)
- Unicode/special characters in file paths
- Empty details dict
- Unknown operation type (invalid enum)
- Unknown state (invalid enum)
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Add handoff package to path
HANDOFF_PACKAGE = Path(__file__).parent.parent / "src"
if str(HANDOFF_PACKAGE) not in globals():
    import sys
    sys.path.insert(0, str(HANDOFF_PACKAGE))

from handoff.checkpoint_ops import PendingOperation


class TestPendingOperationEmptyTarget:
    """Tests for empty target field handling."""

    def test_empty_string_target_via_constructor(self):
        """Test PendingOperation with empty string target via constructor.

        Given: A PendingOperation is created with empty target
        When: Constructor is called with target=""
        Then: Should raise ValueError (or fail validation)
        """
        with pytest.raises(ValueError, match="target"):
            PendingOperation(
                type="edit",
                target="",
                state="in_progress",
                details={}
            )

    def test_whitespace_only_target(self):
        """Test PendingOperation with whitespace-only target.

        Given: A PendingOperation is created with whitespace target
        When: Constructor is called with target="   "
        Then: Should raise ValueError (or fail validation)
        """
        with pytest.raises(ValueError, match="target"):
            PendingOperation(
                type="edit",
                target="   ",
                state="in_progress",
                details={}
            )

    def test_empty_string_target_via_from_dict(self):
        """Test PendingOperation with empty string target via from_dict.

        Given: A PendingOperation is loaded from dict with empty target
        When: from_dict is called with target=""
        Then: Should raise ValueError
        """
        data = {
            "type": "edit",
            "target": "",
            "state": "in_progress"
        }
        with pytest.raises(ValueError, match="target"):
            PendingOperation.from_dict(data)

    def test_none_target_via_from_dict(self):
        """Test PendingOperation with None target via from_dict.

        Given: A PendingOperation is loaded from dict with None target
        When: from_dict is called with target=None
        Then: Should raise ValueError
        """
        data = {
            "type": "edit",
            "target": None,
            "state": "in_progress"
        }
        with pytest.raises(ValueError, match="target"):
            PendingOperation.from_dict(data)


class TestPendingOperationLongPaths:
    """Tests for very long file path handling."""

    def test_very_long_path_via_constructor(self):
        """Test PendingOperation with path > 255 characters.

        Given: A PendingOperation is created with extremely long path
        When: Constructor is called with 300+ character path
        Then: Should raise ValueError (path too long for most filesystems)
        """
        long_path = "a" * 300 + ".py"
        with pytest.raises(ValueError, match="path|target|length"):
            PendingOperation(
                type="edit",
                target=long_path,
                state="in_progress",
                details={}
            )

    def test_path_exactly_255_chars(self):
        """Test PendingOperation with path exactly 255 characters.

        Given: A PendingOperation is created with 255 character path
        When: Constructor is called with 255 character path
        Then: Should accept or validate (boundary case)
        """
        path_255 = "a" * 252 + ".py"  # Exactly 255 chars
        # This is the MAX length for many filesystems
        op = PendingOperation(
            type="edit",
            target=path_255,
            state="in_progress",
            details={}
        )
        assert len(op.target) == 255

    def test_long_path_via_from_dict(self):
        """Test PendingOperation with long path via from_dict.

        Given: A PendingOperation is loaded from dict with long path
        When: from_dict is called with 300+ character path
        Then: Should raise ValueError
        """
        long_path = "b" * 300 + ".txt"
        data = {
            "type": "read",
            "target": long_path,
            "state": "pending"
        }
        with pytest.raises(ValueError, match="path|target|length"):
            PendingOperation.from_dict(data)


class TestPendingOperationSpecialCharacters:
    """Tests for Unicode and special characters in file paths."""

    def test_unicode_characters_in_target(self):
        """Test PendingOperation with Unicode characters in target.

        Given: A PendingOperation is created with Unicode path
        When: Constructor is called with emojis/special chars
        Then: Should accept valid Unicode or reject invalid
        """
        # Test with various Unicode characters
        unicode_paths = [
            "src/日本語/ファイル.py",  # Japanese
            "src/emoji/test🚀.py",    # Emoji
            "src/arabic/مثال.py",     # Arabic
            "src/russian/пример.py",   # Cyrillic
        ]

        for path in unicode_paths:
            op = PendingOperation(
                type="edit",
                target=path,
                state="in_progress",
                details={}
            )
            assert op.target == path

    def test_null_bytes_in_target(self):
        """Test PendingOperation with null bytes in target.

        Given: A PendingOperation is created with null bytes
        When: Constructor is called with embedded null bytes
        Then: Should raise ValueError (security risk)
        """
        malicious_path = "test\x00.py"
        with pytest.raises(ValueError, match="null|invalid"):
            PendingOperation(
                type="edit",
                target=malicious_path,
                state="in_progress",
                details={}
            )

    def test_absolute_path_traversal(self):
        """Test PendingOperation with path traversal sequences.

        Given: A PendingOperation is created with path traversal
        When: Constructor is called with ../../../etc/passwd
        Then: Should validate or normalize path (security)
        """
        traversal_paths = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32",
            "./../../secret.txt",
            "/etc/passwd",
        ]

        for path in traversal_paths:
            # Either reject or normalize - tests document behavior
            op = PendingOperation(
                type="read",
                target=path,
                state="pending",
                details={}
            )
            # Document what happens - may want validation later
            assert op.target == path


class TestPendingOperationDetails:
    """Tests for details field validation."""

    def test_empty_details_dict(self):
        """Test PendingOperation with empty details dict.

        Given: A PendingOperation is created with empty details
        When: Constructor is called with details={}
        Then: Should accept empty details (valid use case)
        """
        op = PendingOperation(
            type="edit",
            target="src/main.py",
            state="in_progress",
            details={}
        )
        assert op.details == {}

    def test_none_details_defaults_to_empty(self):
        """Test PendingOperation with None details via from_dict.

        Given: A PendingOperation is loaded from dict without details
        When: from_dict is called with missing details key
        Then: Should default to empty dict
        """
        data = {
            "type": "test",
            "target": "tests/test_main.py",
            "state": "pending"
        }
        op = PendingOperation.from_dict(data)
        assert op.details == {}

    def test_complex_nested_details(self):
        """Test PendingOperation with complex nested details.

        Given: A PendingOperation has nested details structure
        When: Details contain nested dicts, lists, primitives
        Then: Should preserve structure
        """
        complex_details = {
            "changes": [
                {"line": 42, "old": "foo", "new": "bar"},
                {"line": 99, "old": "baz", "new": "qux"}
            ],
            "metadata": {
                "author": "test",
                "timestamp": "2025-02-27T12:00:00Z",
                "reviewed": True
            },
            "count": 2
        }

        op = PendingOperation(
            type="edit",
            target="src/main.py",
            state="in_progress",
            details=complex_details
        )

        assert op.details["changes"][0]["line"] == 42
        assert op.details["metadata"]["reviewed"] is True


class TestPendingOperationInvalidEnums:
    """Tests for invalid enum values."""

    def test_invalid_operation_type_uppercase(self):
        """Test PendingOperation with uppercase operation type.

        Given: A PendingOperation is created with uppercase type
        When: from_dict is called with type="EDIT"
        Then: Should raise ValueError (case-sensitive enum)
        """
        data = {
            "type": "EDIT",  # Should be "edit"
            "target": "test.py",
            "state": "pending"
        }
        with pytest.raises(ValueError, match="Invalid type"):
            PendingOperation.from_dict(data)

    def test_unknown_operation_type(self):
        """Test PendingOperation with unknown operation type.

        Given: A PendingOperation is loaded from dict
        When: from_dict is called with type="deploy" (not in enum)
        Then: Should raise ValueError with valid enum values
        """
        data = {
            "type": "deploy",  # Not a valid type
            "target": "app.py",
            "state": "pending"
        }
        with pytest.raises(ValueError, match="Invalid type.*Must be one of"):
            PendingOperation.from_dict(data)

    def test_numeric_type(self):
        """Test PendingOperation with numeric type.

        Given: A PendingOperation is loaded from dict
        When: from_dict is called with type=123 (wrong type)
        Then: Should raise ValueError
        """
        data = {
            "type": 123,
            "target": "test.py",
            "state": "pending"
        }
        with pytest.raises((ValueError, TypeError)):
            PendingOperation.from_dict(data)

    def test_invalid_state_uppercase(self):
        """Test PendingOperation with uppercase state.

        Given: A PendingOperation is loaded from dict
        When: from_dict is called with state="PENDING"
        Then: Should raise ValueError (case-sensitive enum)
        """
        data = {
            "type": "edit",
            "target": "test.py",
            "state": "PENDING"  # Should be "pending"
        }
        with pytest.raises(ValueError, match="Invalid state"):
            PendingOperation.from_dict(data)

    def test_unknown_state(self):
        """Test PendingOperation with unknown state.

        Given: A PendingOperation is loaded from dict
        When: from_dict is called with state="cancelled" (not in enum)
        Then: Should raise ValueError with valid enum values
        """
        data = {
            "type": "edit",
            "target": "test.py",
            "state": "cancelled"  # Not a valid state
        }
        with pytest.raises(ValueError, match="Invalid state.*Must be one of"):
            PendingOperation.from_dict(data)

    def test_all_valid_types(self):
        """Test that all valid operation types are accepted.

        Given: A PendingOperation is created
        When: Each valid type is used
        Then: All should be accepted
        """
        valid_types = ["edit", "test", "read", "command", "skill"]

        for op_type in valid_types:
            op = PendingOperation(
                type=op_type,
                target="test.py",
                state="pending",
                details={}
            )
            assert op.type == op_type

    def test_all_valid_states(self):
        """Test that all valid states are accepted.

        Given: A PendingOperation is created
        When: Each valid state is used
        Then: All should be accepted
        """
        valid_states = ["pending", "in_progress", "failed"]

        for state in valid_states:
            op = PendingOperation(
                type="edit",
                target="test.py",
                state=state,
                details={}
            )
            assert op.state == state


class TestPendingOperationConstructorValidation:
    """Tests for direct constructor validation (vs from_dict).

    Current behavior: Constructor validates target field, but not type/state.
    These tests document the validation behavior.
    """

    def test_constructor_skips_type_validation(self):
        """Test that constructor accepts invalid type (documenting current behavior).

        Given: Direct instantiation via constructor
        When: Invalid type is provided
        Then: Currently succeeds (no validation in constructor)
        """
        # This currently succeeds - type hints only, no runtime validation
        op = PendingOperation(
            type="invalid_type",  # Invalid but accepted by constructor
            target="test.py",
            state="pending",
            details={}
        )
        assert op.type == "invalid_type"  # Documents current behavior

    def test_constructor_skips_state_validation(self):
        """Test that constructor accepts invalid state (documenting current behavior).

        Given: Direct instantiation via constructor
        When: Invalid state is provided
        Then: Currently succeeds (no validation in constructor)
        """
        # This currently succeeds - type hints only, no runtime validation
        op = PendingOperation(
            type="edit",
            target="test.py",
            state="cancelled",  # Invalid but accepted by constructor
            details={}
        )
        assert op.state == "cancelled"  # Documents current behavior

    def test_constructor_accepts_empty_target(self):
        """Test that constructor accepts empty target (documenting current behavior).

        Given: Direct instantiation via constructor
        When: Empty target string is provided
        Then: Currently succeeds (no validation in constructor)
        """
        # This currently succeeds - no validation
        op = PendingOperation(
            type="edit",
            target="",  # Invalid but accepted
            state="pending",
            details={}
        )
        assert op.target == ""  # Documents current behavior

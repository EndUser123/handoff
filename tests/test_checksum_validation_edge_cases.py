#!/usr/bin/env python3
"""
Edge case tests for checksum validation (TEST-003).

These tests CAPTURE CURRENT BEHAVIOR of checksum validation edge cases.
The validation is implemented in handoff.models.HandoffCheckpoint._validate_checksum()

Current implementation (models.py lines 114-139):
- Checks for "sha256:" prefix (case-sensitive)
- Validates hex characters (0-9, a-f, A-F) - case-insensitive
- Validates length: exactly 64 hex characters after prefix

Run with: pytest P:/packages/handoff/tests/test_checksum_validation_edge_cases.py -v
"""

import pytest
import sys
from pathlib import Path

# Add src to path for imports
src_dir = Path("P:/packages/handoff/src").resolve()
sys.path.insert(0, str(src_dir))

from handoff.models import HandoffCheckpoint


class TestChecksumEmpty:
    """Test edge case: empty checksum string."""

    def test_empty_checksum_raises_error(self):
        """
        Test that empty checksum raises ValueError.

        Given: Empty checksum string ""
        When: _validate_checksum is called
        Then: ValueError is raised with message about prefix

        Current behavior: Raises "Invalid checksum format: must start with 'sha256:'"
        """
        with pytest.raises(ValueError) as exc_info:
            HandoffCheckpoint._validate_checksum("")

        assert "must start with 'sha256:'" in str(exc_info.value)
        assert "Invalid checksum format" in str(exc_info.value)


class TestChecksumWrongLength:
    """Test edge case: checksum with wrong length."""

    def test_short_checksum_raises_error(self):
        """
        Test that too-short checksum raises ValueError.

        Given: Checksum with only 3 hex chars: "sha256:abc"
        When: _validate_checksum is called
        Then: ValueError is raised about length requirement

        Current behavior: Raises "Invalid checksum: must be 64 hexadecimal characters"
        """
        with pytest.raises(ValueError) as exc_info:
            HandoffCheckpoint._validate_checksum("sha256:abc")

        assert "64 hexadecimal characters" in str(exc_info.value)
        assert "Invalid checksum" in str(exc_info.value)

    def test_long_checksum_raises_error(self):
        """
        Test that too-long checksum raises ValueError.

        Given: Checksum with 65 hex chars
        When: _validate_checksum is called
        Then: ValueError is raised about length requirement

        Current behavior: Raises "Invalid checksum: must be 64 hexadecimal characters"
        """
        # 65 hex chars (one too many)
        long_checksum = "sha256:" + "a" * 65
        with pytest.raises(ValueError) as exc_info:
            HandoffCheckpoint._validate_checksum(long_checksum)

        assert "64 hexadecimal characters" in str(exc_info.value)
        assert "Invalid checksum" in str(exc_info.value)

    def test_exactly_64_chars_passes(self):
        """
        Test that exactly 64 hex characters passes validation.

        Given: Checksum with exactly 64 hex characters
        When: _validate_checksum is called
        Then: No exception is raised

        This is the POSITIVE test case - valid checksum should pass.
        """
        # Valid: exactly 64 hex chars
        valid_checksum = "sha256:" + "a" * 64
        # Should not raise
        HandoffCheckpoint._validate_checksum(valid_checksum)


class TestChecksumInvalidHex:
    """Test edge case: checksum with invalid hex characters."""

    def test_invalid_hex_characters_raises_error(self):
        """
        Test that non-hex characters raise ValueError.

        Given: Checksum with invalid hex: "sha256:xyz123..."
        When: _validate_checksum is called
        Then: ValueError is raised about hex characters

        Current behavior: Raises "Invalid checksum: must contain only hexadecimal characters"
        """
        # Invalid hex: 'x', 'y', 'z' are not valid hex
        invalid_checksum = "sha256:xyz123000000000000000000000000000000000000000000000000000000000"

        with pytest.raises(ValueError) as exc_info:
            HandoffCheckpoint._validate_checksum(invalid_checksum)

        assert "hexadecimal characters" in str(exc_info.value)
        assert "Invalid checksum" in str(exc_info.value)

    def test_special_characters_raise_error(self):
        """
        Test that special characters raise ValueError.

        Given: Checksum with special chars: "sha256:abc@#$..."
        When: _validate_checksum is called
        Then: ValueError is raised about hex characters

        Current behavior: Raises "Invalid checksum: must contain only hexadecimal characters"
        """
        # Special characters: '@', '#', '$' are not valid hex
        invalid_checksum = "sha256:abc@#$0000000000000000000000000000000000000000000000000000000000000"

        with pytest.raises(ValueError) as exc_info:
            HandoffCheckpoint._validate_checksum(invalid_checksum)

        assert "hexadecimal characters" in str(exc_info.value)
        assert "Invalid checksum" in str(exc_info.value)

    def test_spaces_raise_error(self):
        """
        Test that spaces in checksum raise ValueError.

        Given: Checksum with spaces: "sha256:abc def..."
        When: _validate_checksum is called
        Then: ValueError is raised about hex characters

        Current behavior: Raises "Invalid checksum: must contain only hexadecimal characters"
        """
        # Spaces are not valid hex
        invalid_checksum = "sha256:abc def0000000000000000000000000000000000000000000000000000000000"

        with pytest.raises(ValueError) as exc_info:
            HandoffCheckpoint._validate_checksum(invalid_checksum)

        assert "hexadecimal characters" in str(exc_info.value)
        assert "Invalid checksum" in str(exc_info.value)


class TestChecksumCaseSensitivity:
    """Test edge case: case sensitivity in prefix and hex characters."""

    def test_uppercase_prefix_raises_error(self):
        """
        Test that uppercase prefix "SHA256:" is rejected.

        Given: Checksum with uppercase prefix: "SHA256:abc..."
        When: _validate_checksum is called
        Then: ValueError is raised about prefix

        Current behavior: The prefix check is case-sensitive
        Expected: Raises "Invalid checksum format: must start with 'sha256:'"
        """
        # Uppercase prefix
        uppercase_checksum = "SHA256:" + "a" * 64

        with pytest.raises(ValueError) as exc_info:
            HandoffCheckpoint._validate_checksum(uppercase_checksum)

        assert "must start with 'sha256:'" in str(exc_info.value)
        assert "Invalid checksum format" in str(exc_info.value)

    def test_mixed_case_prefix_raises_error(self):
        """
        Test that mixed-case prefix "Sha256:" is rejected.

        Given: Checksum with mixed-case prefix: "Sha256:abc..."
        When: _validate_checksum is called
        Then: ValueError is raised about prefix

        Current behavior: The prefix check is case-sensitive
        Expected: Raises "Invalid checksum format: must start with 'sha256:'"
        """
        # Mixed case prefix
        mixed_checksum = "Sha256:" + "a" * 64

        with pytest.raises(ValueError) as exc_info:
            HandoffCheckpoint._validate_checksum(mixed_checksum)

        assert "must start with 'sha256:'" in str(exc_info.value)
        assert "Invalid checksum format" in str(exc_info.value)

    def test_lowercase_hex_passes(self):
        """
        Test that lowercase hex characters pass validation.

        Given: Checksum with lowercase hex: "sha256:abc...123"
        When: _validate_checksum is called
        Then: No exception is raised

        Current behavior: Hex validation accepts lowercase a-f
        """
        # Valid: lowercase hex
        valid_checksum = "sha256:" + "abc123" + "0" * 58
        # Should not raise
        HandoffCheckpoint._validate_checksum(valid_checksum)

    def test_uppercase_hex_passes(self):
        """
        Test that uppercase hex characters pass validation.

        Given: Checksum with uppercase hex: "sha256:ABC...123"
        When: _validate_checksum is called
        Then: No exception is raised

        Current behavior: Hex validation accepts uppercase A-F (case-insensitive)
        """
        # Valid: uppercase hex
        valid_checksum = "sha256:" + "ABC123" + "0" * 58
        # Should not raise
        HandoffCheckpoint._validate_checksum(valid_checksum)

    def test_mixed_case_hex_passes(self):
        """
        Test that mixed-case hex characters pass validation.

        Given: Checksum with mixed-case hex: "sha256:AaBbCc..."
        When: _validate_checksum is called
        Then: No exception is raised

        Current behavior: Hex validation is case-insensitive
        """
        # Valid: mixed case hex
        valid_checksum = "sha256:" + "AaBbCc123" + "0" * 56
        # Should not raise
        HandoffCheckpoint._validate_checksum(valid_checksum)


class TestChecksumMissingPrefix:
    """Test edge case: checksum missing required prefix."""

    def test_no_prefix_raises_error(self):
        """
        Test that checksum without "sha256:" prefix raises ValueError.

        Given: Checksum without prefix: "abc...123" (64 hex chars, no prefix)
        When: _validate_checksum is called
        Then: ValueError is raised about missing prefix

        Current behavior: Raises "Invalid checksum format: must start with 'sha256:'"
        """
        # No prefix, just 64 hex chars
        no_prefix = "a" * 64

        with pytest.raises(ValueError) as exc_info:
            HandoffCheckpoint._validate_checksum(no_prefix)

        assert "must start with 'sha256:'" in str(exc_info.value)
        assert "Invalid checksum format" in str(exc_info.value)

    def test_wrong_prefix_raises_error(self):
        """
        Test that checksum with wrong prefix raises ValueError.

        Given: Checksum with "md5:" prefix instead of "sha256:"
        When: _validate_checksum is called
        Then: ValueError is raised about incorrect prefix

        Current behavior: Raises "Invalid checksum format: must start with 'sha256:'"
        """
        # Wrong prefix
        wrong_prefix = "md5:" + "a" * 64

        with pytest.raises(ValueError) as exc_info:
            HandoffCheckpoint._validate_checksum(wrong_prefix)

        assert "must start with 'sha256:'" in str(exc_info.value)
        assert "Invalid checksum format" in str(exc_info.value)

    def test_partial_prefix_raises_error(self):
        """
        Test that checksum with partial prefix raises ValueError.

        Given: Checksum with "sha25:" instead of "sha256:"
        When: _validate_checksum is called
        Then: ValueError is raised about incorrect prefix

        Current behavior: Raises "Invalid checksum format: must start with 'sha256:'"
        """
        # Partial prefix (missing the '6')
        partial_prefix = "sha25:" + "a" * 64

        with pytest.raises(ValueError) as exc_info:
            HandoffCheckpoint._validate_checksum(partial_prefix)

        assert "must start with 'sha256:'" in str(exc_info.value)
        assert "Invalid checksum format" in str(exc_info.value)


class TestChecksumValidFormats:
    """Test valid checksum formats (positive test cases)."""

    def test_valid_all_zeros(self):
        """
        Test that valid checksum of all zeros passes.

        Given: Valid checksum "sha256:000...000" (64 zeros)
        When: _validate_checksum is called
        Then: No exception is raised
        """
        valid_checksum = "sha256:" + "0" * 64
        HandoffCheckpoint._validate_checksum(valid_checksum)

    def test_valid_all_f(self):
        """
        Test that valid checksum of all 'f' characters passes.

        Given: Valid checksum "sha256:fff...fff" (64 f's)
        When: _validate_checksum is called
        Then: No exception is raised
        """
        valid_checksum = "sha256:" + "f" * 64
        HandoffCheckpoint._validate_checksum(valid_checksum)

    def test_valid_mixed_hex(self):
        """
        Test that valid checksum with mixed hex passes.

        Given: Valid checksum with various hex characters
        When: _validate_checksum is called
        Then: No exception is raised
        """
        # Realistic SHA256-like hex string
        valid_checksum = "sha256:a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f9012"
        HandoffCheckpoint._validate_checksum(valid_checksum)

    def test_valid_with_numbers_only(self):
        """
        Test that valid checksum with only numbers passes.

        Given: Valid checksum "sha256:000...999" (digits only)
        When: _validate_checksum is called
        Then: No exception is raised
        """
        # All digits 0-9 repeated
        valid_checksum = "sha256:" + "0123456789" * 6 + "0123"
        HandoffCheckpoint._validate_checksum(valid_checksum)


class TestChecksumFromDictIntegration:
    """Test checksum validation in HandoffCheckpoint.from_dict()."""

    def test_from_dict_rejects_invalid_checksum(self):
        """
        Test that from_dict() rejects invalid checksum format.

        Given: Handoff data with invalid checksum (missing prefix)
        When: HandoffCheckpoint.from_dict() is called
        Then: ValueError is raised from _validate_checksum()

        This tests the integration: from_dict() calls _validate_checksum()
        """
        handoff_data = {
            "checkpoint_id": "test-001",
            "chain_id": "chain-001",
            "created_at": "2026-03-01T00:00:00Z",
            "task_name": "Test task",
            "task_type": "formal",
            "progress_percent": 50,
            "next_steps": "Complete testing",
            "active_files": [],
            "recent_tools": [],
            "saved_at": "2026-03-01T00:00:00Z",
            "version": 1,
            "pending_operations": [],
            # Invalid: missing "sha256:" prefix
            "checksum": "a" * 64
        }

        with pytest.raises(ValueError) as exc_info:
            HandoffCheckpoint.from_dict(handoff_data)

        assert "checksum" in str(exc_info.value).lower()

    def test_from_dict_accepts_valid_checksum(self):
        """
        Test that from_dict() accepts valid checksum format.

        Given: Handoff data with valid checksum
        When: HandoffCheckpoint.from_dict() is called
        Then: HandoffCheckpoint object is created successfully

        This is a POSITIVE test case - valid data should work.
        """
        handoff_data = {
            "checkpoint_id": "test-001",
            "chain_id": "chain-001",
            "created_at": "2026-03-01T00:00:00Z",
            "task_name": "Test task",
            "task_type": "formal",
            "progress_percent": 50,
            "next_steps": "Complete testing",
            "active_files": [],
            "recent_tools": [],
            "saved_at": "2026-03-01T00:00:00Z",
            "version": 1,
            "pending_operations": [],
            # Valid checksum format
            "checksum": "sha256:" + "a" * 64
        }

        # Should not raise
        checkpoint = HandoffCheckpoint.from_dict(handoff_data)
        assert checkpoint.checksum == "sha256:" + "a" * 64

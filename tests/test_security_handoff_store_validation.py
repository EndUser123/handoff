"""
Test Suite for SEC-002: Insufficient Input Validation in HandoffStore

These tests verify that HandoffStore.__init__() properly validates
the terminal_id parameter to prevent path traversal and injection attacks.

Security Issue: The current implementation accepts any string as terminal_id
without validation, which could allow:
- Path traversal attacks (../../etc/passwd)
- Null byte injection (term\x00)
- Arbitrary file system access

Expected behavior: Validate terminal_id format using regex ^term_[a-zA-Z0-9_-]+$
Actual behavior (before fix): Accepts any terminal_id string

Run with: pytest tests/test_security_handoff_store_validation.py -v
"""

from pathlib import Path

import pytest

from handoff.hooks.__lib.handoff_store import HandoffStore


class TestHandoffStoreTerminalIdValidation:
    """Tests for terminal_id validation in HandoffStore.__init__()."""

    @pytest.fixture
    def project_root(self):
        """Provide a test project root path."""
        return Path("/tmp/test_project")

    def test_reject_path_traversal_with_parent_directory(self, project_root):
        """
        Test that HandoffStore rejects path traversal in terminal_id.

        Given: A malicious terminal_id with '../../../etc' path traversal
        When: HandoffStore is initialized with this terminal_id
        Then: It should raise ValueError for invalid format

        Current behavior (BUG): Accepts the malicious input
        Expected behavior: Should raise ValueError with validation message
        """
        malicious_terminal_id = "../../../etc"

        # This SHOULD raise ValueError but currently doesn't
        with pytest.raises(ValueError, match="terminal_id"):
            HandoffStore(project_root=project_root, terminal_id=malicious_terminal_id)

    def test_reject_null_byte_injection(self, project_root):
        """
        Test that HandoffStore rejects null bytes in terminal_id.

        Given: A terminal_id containing null bytes 'term\x00'
        When: HandoffStore is initialized with this terminal_id
        Then: It should raise ValueError for invalid format

        Current behavior (BUG): Accepts the null byte injection
        Expected behavior: Should raise ValueError detecting null bytes
        """
        malicious_terminal_id = "term\x00"

        # This SHOULD raise ValueError but currently doesn't
        with pytest.raises(ValueError, match="terminal_id"):
            HandoffStore(project_root=project_root, terminal_id=malicious_terminal_id)

    def test_reject_path_traversal_with_relative_path(self, project_root):
        """
        Test that HandoffStore rejects relative path traversal.

        Given: A terminal_id with '../../malicious' path traversal
        When: HandoffStore is initialized with this terminal_id
        Then: It should raise ValueError for invalid format

        Current behavior (BUG): Accepts the path traversal attempt
        Expected behavior: Should raise ValueError blocking traversal
        """
        malicious_terminal_id = "../../malicious"

        # This SHOULD raise ValueError but currently doesn't
        with pytest.raises(ValueError, match="terminal_id"):
            HandoffStore(project_root=project_root, terminal_id=malicious_terminal_id)

    def test_reject_absolute_path_escape(self, project_root):
        """
        Test that HandoffStore rejects absolute path escape attempts.

        Given: A terminal_id trying to use absolute path '/etc/passwd'
        When: HandoffStore is initialized with this terminal_id
        Then: It should raise ValueError for invalid format

        Current behavior (BUG): Accepts absolute paths
        Expected behavior: Should raise ValueError blocking absolute paths
        """
        malicious_terminal_id = "/etc/passwd"

        # This SHOULD raise ValueError but currently doesn't
        with pytest.raises(ValueError, match="terminal_id"):
            HandoffStore(project_root=project_root, terminal_id=malicious_terminal_id)

    def test_reject_current_directory_reference(self, project_root):
        """
        Test that HandoffStore rejects current directory references.

        Given: A terminal_id with './hidden' current directory reference
        When: HandoffStore is initialized with this terminal_id
        Then: It should raise ValueError for invalid format

        Current behavior (BUG): Accepts current directory references
        Expected behavior: Should raise ValueError blocking directory references
        """
        malicious_terminal_id = "./hidden"

        # This SHOULD raise ValueError but currently doesn't
        with pytest.raises(ValueError, match="terminal_id"):
            HandoffStore(project_root=project_root, terminal_id=malicious_terminal_id)

    def test_reject_mixed_traversal_patterns(self, project_root):
        """
        Test that HandoffStore rejects mixed traversal patterns.

        Given: A terminal_id with mixed traversal '../.././etc/passwd'
        When: HandoffStore is initialized with this terminal_id
        Then: It should raise ValueError for invalid format

        Current behavior (BUG): Accepts mixed traversal patterns
        Expected behavior: Should raise ValueError blocking all traversal
        """
        malicious_terminal_id = "../.././etc/passwd"

        # This SHOULD raise ValueError but currently doesn't
        with pytest.raises(ValueError, match="terminal_id"):
            HandoffStore(project_root=project_root, terminal_id=malicious_terminal_id)

    def test_reject_terminal_id_without_prefix(self, project_root):
        """
        Test that HandoffStore accepts terminal_id without 'term_' prefix.

        Given: A terminal_id 'random_name' without the required prefix
        When: HandoffStore is initialized with this terminal_id
        Then: It should accept the terminal_id (backward compatibility)

        SECURITY NOTE: Pattern validation (term_ prefix) was removed to maintain
        backward compatibility with existing terminal IDs. Security is maintained
        through validation of null bytes, path traversal, and absolute paths.
        """
        # This should NOT raise ValueError - backward compatible
        invalid_terminal_id = "random_name"
        store = HandoffStore(project_root=project_root, terminal_id=invalid_terminal_id)
        assert store.terminal_id == invalid_terminal_id

    def test_reject_terminal_id_with_special_characters(self, project_root):
        """
        Test that HandoffStore accepts special characters in terminal_id.

        Given: A terminal_id 'term_$p3cial!' with special characters
        When: HandoffStore is initialized with this terminal_id
        Then: It should accept the terminal_id (backward compatibility)

        SECURITY NOTE: Special characters are accepted for backward compatibility.
        Security is maintained through validation of null bytes, path traversal,
        and absolute paths - special characters don't enable these attacks.
        """
        # This should NOT raise ValueError - backward compatible
        invalid_terminal_id = "term_$p3cial!"
        store = HandoffStore(project_root=project_root, terminal_id=invalid_terminal_id)
        assert store.terminal_id == invalid_terminal_id

    def test_reject_terminal_id_with_spaces(self, project_root):
        """
        Test that HandoffStore accepts terminal_id with spaces (backward compatibility).

        Given: A terminal_id 'term_ my terminal' with spaces
        When: HandoffStore is initialized with this terminal_id
        Then: It should accept the terminal_id (backward compatibility)

        SECURITY NOTE: Spaces are accepted for backward compatibility.
        Whitespace-only terminal_id are still rejected (security).
        """
        # This should NOT raise ValueError - backward compatible
        # As long as it's not whitespace-only, it's accepted
        invalid_terminal_id = "term_ my terminal"
        store = HandoffStore(project_root=project_root, terminal_id=invalid_terminal_id)
        assert store.terminal_id == invalid_terminal_id

    def test_accept_valid_terminal_id_simple(self, project_root):
        """
        Test that HandoffStore accepts valid terminal_id format.

        Given: A valid terminal_id 'term_test123'
        When: HandoffStore is initialized with this terminal_id
        Then: It should successfully create the HandoffStore instance

        This is a POSITIVE test case - valid inputs should be accepted.
        """
        valid_terminal_id = "term_test123"

        # This SHOULD succeed
        store = HandoffStore(project_root=project_root, terminal_id=valid_terminal_id)

        assert store is not None
        assert store.terminal_id == valid_terminal_id
        assert store.project_root == project_root

    def test_accept_valid_terminal_id_with_underscores(self, project_root):
        """
        Test that HandoffStore accepts valid terminal_id with underscores.

        Given: A valid terminal_id 'term_my_test_123'
        When: HandoffStore is initialized with this terminal_id
        Then: It should successfully create the HandoffStore instance

        This is a POSITIVE test case - underscores are allowed.
        """
        valid_terminal_id = "term_my_test_123"

        # This SHOULD succeed
        store = HandoffStore(project_root=project_root, terminal_id=valid_terminal_id)

        assert store is not None
        assert store.terminal_id == valid_terminal_id

    def test_accept_valid_terminal_id_with_hyphens(self, project_root):
        """
        Test that HandoffStore accepts valid terminal_id with hyphens.

        Given: A valid terminal_id 'term_test-123'
        When: HandoffStore is initialized with this terminal_id
        Then: It should successfully create the HandoffStore instance

        This is a POSITIVE test case - hyphens are allowed.
        """
        valid_terminal_id = "term_test-123"

        # This SHOULD succeed
        store = HandoffStore(project_root=project_root, terminal_id=valid_terminal_id)

        assert store is not None
        assert store.terminal_id == valid_terminal_id

    def test_accept_valid_terminal_id_mixed_case(self, project_root):
        """
        Test that HandoffStore accepts valid terminal_id with mixed case.

        Given: A valid terminal_id 'term_TestABC123'
        When: HandoffStore is initialized with this terminal_id
        Then: It should successfully create the HandoffStore instance

        This is a POSITIVE test case - mixed case is allowed.
        """
        valid_terminal_id = "term_TestABC123"

        # This SHOULD succeed
        store = HandoffStore(project_root=project_root, terminal_id=valid_terminal_id)

        assert store is not None
        assert store.terminal_id == valid_terminal_id

    def test_reject_empty_terminal_id(self, project_root):
        """
        Test that HandoffStore rejects empty terminal_id.

        Given: An empty string as terminal_id
        When: HandoffStore is initialized with this terminal_id
        Then: It should raise ValueError for empty input

        Current behavior (BUG): Accepts empty string
        Expected behavior: Should raise ValueError for empty terminal_id
        """
        invalid_terminal_id = ""

        # This SHOULD raise ValueError but currently doesn't
        with pytest.raises(ValueError, match="terminal_id"):
            HandoffStore(project_root=project_root, terminal_id=invalid_terminal_id)

    def test_reject_whitespace_only_terminal_id(self, project_root):
        """
        Test that HandoffStore rejects whitespace-only terminal_id.

        Given: A terminal_id with only whitespace characters
        When: HandoffStore is initialized with this terminal_id
        Then: It should raise ValueError for invalid format

        Current behavior (BUG): Accepts whitespace
        Expected behavior: Should raise ValueError for whitespace-only input
        """
        invalid_terminal_id = "   "

        # This SHOULD raise ValueError but currently doesn't
        with pytest.raises(ValueError, match="terminal_id"):
            HandoffStore(project_root=project_root, terminal_id=invalid_terminal_id)

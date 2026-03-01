"""
Test Suite for SEC-001: Path Traversal Vulnerability in _safe_id()

These tests verify that the _safe_id() function properly prevents
path traversal attacks.

Security Issue: The current implementation uses a simple regex substitution
that allows path traversal sequences (../) to pass through after being
partially sanitized. This could allow attackers to access files outside
the intended directory.

Run with: pytest tests/test_security_path_traversal.py -v
"""

import pytest
from handoff.hooks.SessionStart_handoff_restore import _safe_id


class TestSafeIdPathTraversal:
    """Tests for path traversal vulnerability in _safe_id()."""

    def test_reject_parent_directory_traversal_simple(self):
        """
        Test that _safe_id() rejects simple parent directory traversal.

        Given: A malicious input with '../' path traversal sequence
        When: _safe_id() processes the input
        Then: It should raise an exception or return a safe value that blocks traversal

        Current behavior (BUG): Converts '../' to '__' which may still be unsafe
        Expected behavior: Should detect and reject path traversal attempts
        """
        malicious_input = "../../../etc/passwd"

        # This should either raise an exception or return a safe value
        # that doesn't allow path traversal
        result = _safe_id(malicious_input)

        # The result should NOT contain '..' sequences
        # Current implementation will FAIL this test because it converts to '______'
        # but doesn't validate for path traversal patterns
        assert '..' not in result, f"Path traversal sequence not blocked: {malicious_input} -> {result}"

        # The result should be alphanumeric + safe chars only
        # If it contains path traversal indicators, test should fail
        assert '../' not in result, f"Path traversal still present: {result}"

    def test_reject_parent_directory_traversal_with_malicious_file(self):
        """
        Test that _safe_id() rejects path traversal to malicious files.

        Given: A malicious input attempting to reach '../../../malicious'
        When: _safe_id() processes the input
        Then: It should block the path traversal attempt

        Current behavior (BUG): Accepts and sanitizes the traversal sequence
        Expected behavior: Should detect and reject any parent directory references
        """
        malicious_input = "../../../malicious"

        result = _safe_id(malicious_input)

        # Must not allow parent directory traversal
        assert '..' not in result, f"Parent directory reference not blocked: {malicious_input} -> {result}"
        assert '../' not in result, f"Path traversal sequence not blocked: {result}"

    def test_reject_absolute_path_escape(self):
        """
        Test that _safe_id() rejects absolute path escape attempts.

        Given: An input trying to escape using absolute paths like '/etc/passwd'
        When: _safe_id() processes the input
        Then: It should prevent absolute path usage

        Current behavior (BUG): Converts '/' to '_' but doesn't validate
        Expected behavior: Should detect and reject absolute path patterns
        """
        malicious_input = "/etc/passwd"

        result = _safe_id(malicious_input)

        # Should not allow leading slashes that create absolute paths
        assert not result.startswith('/'), f"Absolute path not blocked: {result}"

        # After sanitization, should not reconstruct path-like patterns
        # Current implementation converts to '_etc_passwd' which may be safe
        # but we're testing for proper validation
        assert '//' not in result, f"Path separator sequence not blocked: {result}"

    def test_reject_current_directory_reference(self):
        """
        Test that _safe_id() rejects current directory references.

        Given: An input with './' current directory references
        When: _safe_id() processes the input
        Then: It should sanitize or reject the reference

        Current behavior (BUG): Converts './' to '._' which may be unsafe
        Expected behavior: Should detect and remove directory references
        """
        malicious_input = "./hidden_file"

        result = _safe_id(malicious_input)

        # Should not allow current directory references
        # The '.' could be combined with other chars for path manipulation
        # This test verifies we handle it properly
        if '.' in result:
            # If dots remain, they should not form path sequences
            assert './' not in result, f"Current directory reference not blocked: {result}"

    def test_accept_safe_task_id(self):
        """
        Test that _safe_id() accepts legitimate safe task IDs.

        Given: A normal, safe task ID like 'normal_task'
        When: _safe_id() processes the input
        Then: It should accept and return the value unchanged (or safely sanitized)

        This is a POSITIVE test case - safe inputs should pass through.
        """
        safe_input = "normal_task"
        result = _safe_id(safe_input)

        # Safe input should pass through or be safely sanitized
        assert result is not None
        assert len(result) > 0
        # Should not contain path separators or dangerous chars
        assert '/' not in result
        assert '\\' not in result
        assert '..' not in result

    def test_accept_safe_id_with_underscores(self):
        """
        Test that _safe_id() accepts task IDs with underscores.

        Given: A safe task ID like 'my_task_123'
        When: _safe_id() processes the input
        Then: It should accept the safe input

        Underscores are allowed in safe IDs.
        """
        safe_input = "my_task_123"
        result = _safe_id(safe_input)

        assert result is not None
        assert len(result) > 0
        # Should preserve alphanumeric and underscore characters
        assert 'my_task' in result or result.replace('_', '') == 'mytask123'

    def test_reject_mixed_traversal_patterns(self):
        """
        Test that _safe_id() rejects mixed path traversal patterns.

        Given: An input with mixed traversal like '../.././etc/passwd'
        When: _safe_id() processes the input
        Then: It should detect and block the mixed traversal attempt

        Current behavior (BUG): Converts to '_______etc_passwd'
        Expected behavior: Should detect the pattern and reject
        """
        malicious_input = "../.././etc/passwd"

        result = _safe_id(malicious_input)

        # Must not allow any parent directory references
        assert '..' not in result, f"Parent directory reference not blocked: {result}"
        assert '../' not in result, f"Path traversal sequence not blocked: {result}"
        assert './' not in result, f"Current directory reference not blocked: {result}"

    def test_reject_encoded_traversal_attempts(self):
        """
        Test that _safe_id() rejects URL-encoded traversal attempts.

        Given: An input with URL-encoded '%2e%2e%2f' (../)
        When: _safe_id() processes the input
        Then: It should not decode or allow the encoded traversal

        Current behavior (BUG): May pass through if not validated
        Expected behavior: Should reject encoded sequences or fail safely
        """
        malicious_input = "%2e%2e%2fetc%2fpasswd"

        result = _safe_id(malicious_input)

        # Should not contain URL-encoded parent directory references
        # Even if encoded, the %2e%2e pattern should be flagged
        assert '..' not in result, f"Decoded traversal not blocked: {result}"
        assert '../' not in result, f"Path traversal not blocked: {result}"

        # URL encoding characters should be sanitized
        assert '%' not in result or result.count('%') == 0, f"URL-encoded chars not sanitized: {result}"

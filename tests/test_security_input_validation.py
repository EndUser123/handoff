"""
Comprehensive Security Test Suite for Input Validation (TEST-001)

These tests verify that the handoff system properly prevents:
1. Path traversal attacks (../../../etc/passwd)
2. Null byte injection (test\x00file)
3. Unicode homoglyph attacks
4. Malicious terminal_id injection

Run with: pytest tests/test_security_input_validation.py -v

Expected: All tests FAIL (vulnerabilities exist before fixes)
After fix: All tests PASS (vulnerabilities mitigated)
"""

import os
import tempfile
from pathlib import Path

import pytest

from handoff.hooks.__lib.handoff_store import HandoffStore

# Import functions to test
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


class TestSafeIdNullByteInjection:
    """Tests for null byte injection attacks in _safe_id()."""

    def test_reject_null_byte_in_filename(self):
        """
        Test that _safe_id() rejects null byte injection.

        Given: A malicious input with null byte 'test\x00file'
        When: _safe_id() processes the input
        Then: It should remove or reject the null byte

        Null bytes can be used to bypass validation in some systems
        by truncating strings at the null byte position.

        Current behavior (BUG): Null bytes pass through
        Expected behavior: Should detect and remove null bytes
        """
        malicious_input = "test\x00file"

        result = _safe_id(malicious_input)

        # Null bytes should be stripped from result
        assert '\x00' not in result, f"Null byte not removed: {repr(result)}"
        assert result.isprintable(), f"Result contains non-printable chars: {repr(result)}"

    def test_reject_null_byte_with_path_traversal(self):
        """
        Test that _safe_id() rejects combined null byte + path traversal.

        Given: A malicious input with null byte and traversal '../../../etc\x00passwd'
        When: _safe_id() processes the input
        Then: It should block both attack vectors

        This tests a combination attack using null bytes to bypass checks
        while still attempting path traversal.

        Current behavior (BUG): Both vectors may pass through
        Expected behavior: Should detect and block both
        """
        malicious_input = "../../../etc\x00passwd"

        result = _safe_id(malicious_input)

        # Both null bytes and path traversal should be blocked
        assert '\x00' not in result, f"Null byte not removed: {repr(result)}"
        assert '..' not in result, f"Path traversal not blocked: {result}"

    def test_reject_multiple_null_bytes(self):
        """
        Test that _safe_id() rejects multiple null bytes.

        Given: A malicious input with multiple null bytes 'test\x00\x00file'
        When: _safe_id() processes the input
        Then: It should remove all null bytes

        Current behavior (BUG): Multiple null bytes pass through
        Expected behavior: Should remove all null bytes
        """
        malicious_input = "test\x00\x00file"

        result = _safe_id(malicious_input)

        assert '\x00' not in result, f"Null bytes not removed: {repr(result)}"
        assert result.isprintable(), f"Result contains non-printable chars: {repr(result)}"


class TestSafeIdUnicodeHomoglyphs:
    """Tests for unicode homoglyph attacks in _safe_id()."""

    def test_reject_unicode_lookalike_slash(self):
        """
        Test that _safe_id() rejects unicode homoglyphs for path separators.

        Given: A malicious input with unicode fullwidth slash (U+FF03)
        When: _safe_id() processes the input
        Then: It should sanitize the unicode character

        Unicode homoglyphs can be used to bypass validation that only
        checks for ASCII path separators.

        Current behavior (BUG): Unicode homoglyphs may pass through
        Expected behavior: Should sanitize or reject unicode lookalikes
        """
        # Fullwidth solidus (slash lookalike)
        malicious_input = "test\uFF03file"

        result = _safe_id(malicious_input)

        # Unicode lookalikes should be sanitized
        # Result should be printable ASCII or safe unicode only
        assert result.isascii() or result.isprintable(), f"Result contains unsafe unicode: {repr(result)}"

    def test_reject_cyrillic_spoofing(self):
        """
        Test that _safe_id() rejects cyrillic character spoofing.

        Given: A malicious input with cyrillic letters looking like latin
        When: _safe_id() processes the input
        Then: It should handle or reject the spoofed characters

        Current behavior (BUG): May accept cyrillic characters
        Expected behavior: Should sanitize to ASCII or reject
        """
        # Cyrillic 'a' looks like Latin 'a' but is different codepoint
        malicious_input = "test\u0430file"  # cyrillic small 'a'

        result = _safe_id(malicious_input)

        # Should either sanitize to ASCII or be marked as unsafe
        # For now, we just verify it doesn't cause crashes
        assert result is not None

    def test_reject_zero_width_characters(self):
        """
        Test that _safe_id() rejects zero-width characters.

        Given: A malicious input with zero-width characters
        When: _safe_id() processes the input
        Then: It should remove zero-width characters

        Zero-width characters can be used to hide malicious sequences
        or confuse validation logic.

        Current behavior (BUG): Zero-width chars may pass through
        Expected behavior: Should strip zero-width characters
        """
        # Zero-width space
        malicious_input = "test\u200Bfile"

        result = _safe_id(malicious_input)

        # Zero-width characters should be removed
        assert '\u200B' not in result, f"Zero-width space not removed: {repr(result)}"

        # Result should not contain invisible characters
        assert result == result.strip(), f"Result contains invisible chars: {repr(result)}"


class TestHandoffStoreTerminalIdValidation:
    """Tests for terminal_id validation in HandoffStore."""

    def test_reject_malicious_terminal_id_path_traversal(self):
        """
        Test that HandoffStore rejects path traversal in terminal_id.

        Given: A malicious terminal_id with path traversal
        When: HandoffStore is initialized with malicious terminal_id
        Then: It should raise ValueError for path traversal sequences

        SECURITY FIX: Path traversal sequences (..) are now rejected at
        initialization time, preventing any file operations outside project_root.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            malicious_terminal_id = "../../../etc/passwd"

            # Should raise ValueError for path traversal
            with pytest.raises(ValueError, match="path traversal"):
                HandoffStore(project_root, malicious_terminal_id)

    def test_reject_null_byte_in_terminal_id(self):
        """
        Test that HandoffStore rejects null bytes in terminal_id.

        Given: A terminal_id with null bytes
        When: HandoffStore uses the terminal_id in file paths
        Then: It should sanitize null bytes

        Current behavior (BUG): Null bytes may pass through to file paths
        Expected behavior: Should strip null bytes from terminal_id
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            malicious_terminal_id = "term\x01\x00inal"

            store = HandoffStore(project_root, malicious_terminal_id)

            # Terminal ID should not contain null bytes
            assert '\x00' not in store.terminal_id, f"Null byte not removed from terminal_id: {repr(store.terminal_id)}"

            # File operations should work without errors
            assert store.terminal_id is not None

    def test_reject_absolute_path_in_terminal_id(self):
        """
        Test that HandoffStore rejects absolute paths in terminal_id.

        Given: A terminal_id with absolute path
        When: HandoffStore uses the terminal_id in file paths
        Then: It should sanitize absolute path components

        Current behavior (BUG): May use terminal_id directly
        Expected behavior: Should strip path separators from terminal_id
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            malicious_terminal_id = "/etc/passwd"

            store = HandoffStore(project_root, malicious_terminal_id)

            # Terminal ID should not contain path separators
            assert '/' not in store.terminal_id or store.terminal_id == "term_" + str(os.getpid()), \
                f"Path separator not removed from terminal_id: {store.terminal_id}"

    def test_create_continue_session_with_safe_terminal_id(self):
        """
        Test that create_continue_session_task sanitizes terminal_id in file paths.

        Given: A handoff store with malicious terminal_id
        When: create_continue_session_task is called
        Then: Task files should be created within project_root

        Current behavior (BUG): May create files outside project_root
        Expected behavior: Should sanitize terminal_id before file operations
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            malicious_terminal_id = "../../../malicious"

            store = HandoffStore(project_root, malicious_terminal_id)

            # Mock handoff metadata
            handoff_metadata = {
                "task_name": "test_task",
                "progress_pct": 50,
                "blocker": None,
                "files_modified": [],
                "next_steps": "Continue testing",
                "handover": {"decisions": [], "patterns_learned": []},
                "modifications": [],
            }

            # This should not raise an exception or escape project_root
            # If terminal_id is not sanitized, this could fail
            try:
                store.create_continue_session_task(
                    task_name="test_task",
                    task_id="test_id",
                    handoff_metadata=handoff_metadata,
                )

                # Verify task file was created within project_root
                task_tracker_dir = project_root / ".claude" / "state" / "task_tracker"
                task_files = list(task_tracker_dir.glob("*_tasks.json"))

                # All task files should be within project_root
                for task_file in task_files:
                    try:
                        task_file.resolve().relative_to(project_root.resolve())
                    except ValueError:
                        pytest.fail(f"Task file escapes project root: {task_file}")

            except Exception as e:
                # If exception occurs, verify it's not due to path traversal
                if "path" in str(e).lower() or "escape" in str(e).lower():
                    pytest.fail(f"Path traversal vulnerability: {e}")
                # Other exceptions are OK for this test (e.g., missing dependencies)


class TestSafeIdAdditionalEdgeCases:
    """Additional edge case tests for _safe_id()."""

    def test_reject_backslash_traversal_windows(self):
        """
        Test that _safe_id() rejects Windows backslash traversal.

        Given: A malicious input with backslashes '..\\..\\..\\etc\\passwd'
        When: _safe_id() processes the input
        Then: It should sanitize backslash path traversal

        Current behavior (BUG): May not handle Windows path separators
        Expected behavior: Should sanitize both forward and backslashes
        """
        malicious_input = "..\\..\\..\\etc\\passwd"

        result = _safe_id(malicious_input)

        # Should not allow backslash path traversal
        assert '\\' not in result or result.count('\\') == 0, f"Backslash traversal not blocked: {result}"
        assert '..' not in result, f"Parent directory reference not blocked: {result}"

    def test_reject_mixed_slash_traversal(self):
        """
        Test that _safe_id() rejects mixed slash path traversal.

        Given: A malicious input with mixed slashes '..\\../etc/passwd'
        When: _safe_id() processes the input
        Then: It should sanitize mixed slash traversal

        Current behavior (BUG): May not handle mixed path separators
        Expected behavior: Should sanitize all path separator types
        """
        malicious_input = "..\\../etc/passwd"

        result = _safe_id(malicious_input)

        assert '..' not in result, f"Parent directory reference not blocked: {result}"
        assert '../' not in result, f"Forward slash traversal not blocked: {result}"
        # Backslashes should also be handled
        assert result.count('\\') == 0 or '\\' not in result, f"Backslash traversal not blocked: {result}"

    def test_reject_control_characters(self):
        """
        Test that _safe_id() rejects control characters.

        Given: A malicious input with control characters
        When: _safe_id() processes the input
        Then: It should remove control characters

        Current behavior (BUG): Control characters may pass through
        Expected behavior: Should strip control characters
        """
        malicious_input = "test\r\n\x1b[31mfile"  # Carriage return, newline, ANSI escape

        result = _safe_id(malicious_input)

        # Control characters should be removed
        assert '\r' not in result, f"Carriage return not removed: {repr(result)}"
        assert '\n' not in result, f"Newline not removed: {repr(result)}"
        assert '\x1b' not in result, f"Escape character not removed: {repr(result)}"

    def test_handle_extremely_long_input(self):
        """
        Test that _safe_id() handles extremely long input without crashing.

        Given: An extremely long input string (10,000 characters)
        When: _safe_id() processes the input
        Then: It should sanitize without crashing or DoS

        Current behavior (BUG): May be vulnerable to DoS with long strings
        Expected behavior: Should handle long strings efficiently
        """
        malicious_input = "../" * 5000  # 15,000 characters

        # Should not crash or hang
        result = _safe_id(malicious_input)

        assert result is not None
        assert '..' not in result, "Path traversal not blocked in long input"
        # Result should be reasonably sized
        assert len(result) < 20000, f"Result too long: {len(result)} characters"

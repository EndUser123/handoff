#!/usr/bin/env python3
"""Test SessionTypeDetector module.

These tests FAIL because the SessionTypeDetector module doesn't exist yet.

Run with: pytest tests/test_session_type_detector.py -v
"""

import sys
from pathlib import Path

# Add handoff package to path
HANDOFF_PACKAGE = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(HANDOFF_PACKAGE))

import pytest

# Module doesn't exist yet - this will fail
from handoff.hooks.__lib.session_type_detector import SessionTypeDetector


class TestMessageKeywordDetection:
    """Tests for detecting session type from message keywords."""

    def test_debug_keywords_bug_fix_error(self):
        """Test detection of debug session from bug-related keywords."""
        message = "Fix the bug in the authentication module"
        result = SessionTypeDetector.detect_from_message(message)
        assert result == "debug", f"Expected 'debug', got '{result}'"

    def test_debug_keywords_crash_fails(self):
        """Test detection of debug session from crash/failure keywords."""
        message = "The application crashes when I click save"
        result = SessionTypeDetector.detect_from_message(message)
        assert result == "debug", f"Expected 'debug', got '{result}'"

    def test_feature_keywords_add_implement_create(self):
        """Test detection of feature session from feature keywords."""
        message = "Add a new user profile page"
        result = SessionTypeDetector.detect_from_message(message)
        assert result == "feature", f"Expected 'feature', got '{result}'"

    def test_feature_keywords_build(self):
        """Test detection of feature session from build keyword."""
        message = "Build a new REST API endpoint"
        result = SessionTypeDetector.detect_from_message(message)
        assert result == "feature", f"Expected 'feature', got '{result}'"

    def test_refactor_keywords_clean_simplify(self):
        """Test detection of refactor session from cleanup keywords."""
        message = "Clean up the database connection code"
        result = SessionTypeDetector.detect_from_message(message)
        assert result == "refactor", f"Expected 'refactor', got '{result}'"

    def test_refactor_keywords_optimize(self):
        """Test detection of refactor session from optimization keywords."""
        message = "Optimize the query performance"
        result = SessionTypeDetector.detect_from_message(message)
        assert result == "refactor", f"Expected 'refactor', got '{result}'"

    def test_test_keywords_verify_coverage(self):
        """Test detection of test session from testing keywords."""
        message = "Verify the test coverage for this module"
        result = SessionTypeDetector.detect_from_message(message)
        assert result == "test", f"Expected 'test', got '{result}'"

    def test_test_keywords_assert_pytest(self):
        """Test detection of test session from test-specific keywords."""
        message = "Add pytest assertions to validate the output"
        result = SessionTypeDetector.detect_from_message(message)
        assert result == "test", f"Expected 'test', got '{result}'"

    def test_docs_keywords_document_readme(self):
        """Test detection of docs session from documentation keywords."""
        message = "Document the API in the README"
        result = SessionTypeDetector.detect_from_message(message)
        assert result == "docs", f"Expected 'docs', got '{result}'"

    def test_docs_keywords_explain_comment(self):
        """Test detection of docs session from explanation keywords."""
        message = "Add comments to explain this complex logic"
        result = SessionTypeDetector.detect_from_message(message)
        assert result == "docs", f"Expected 'docs', got '{result}'"

    def test_no_keywords_detected(self):
        """Test message with no recognizable keywords returns unknown."""
        message = "Hello, how are you today?"
        result = SessionTypeDetector.detect_from_message(message)
        assert result == "unknown", f"Expected 'unknown', got '{result}'"

    def test_empty_message(self):
        """Test empty message returns unknown."""
        message = ""
        result = SessionTypeDetector.detect_from_message(message)
        assert result == "unknown", f"Expected 'unknown', got '{result}'"

    def test_case_insensitive_keyword_matching(self):
        """Test keyword matching is case-insensitive."""
        message = "FIX the Bug in the code"
        result = SessionTypeDetector.detect_from_message(message)
        assert result == "debug", f"Expected 'debug', got '{result}'"


class TestFilePatternDetection:
    """Tests for detecting session type from file patterns."""

    def test_test_files_pattern(self):
        """Test detection of test session from test file paths."""
        files = [
            "/project/tests/test_auth.py",
            "/project/tests/test_user.py",
        ]
        result = SessionTypeDetector.detect_from_files(files)
        assert result == "test", f"Expected 'test', got '{result}'"

    def test_error_logs_pattern(self):
        """Test detection of debug session from error log files."""
        files = [
            "/project/logs/error.log",
            "/project/logs/exceptions.log",
        ]
        result = SessionTypeDetector.detect_from_files(files)
        assert result == "debug", f"Expected 'debug', got '{result}'"

    def test_new_source_files_feature(self):
        """Test detection of feature session from new source files."""
        files = [
            "/project/src/new_feature.py",
            "/project/src/api/users.py",
        ]
        result = SessionTypeDetector.detect_from_files(files)
        assert result == "feature", f"Expected 'feature', got '{result}'"

    def test_existing_source_files_refactor(self):
        """Test detection of refactor session from existing source files."""
        files = [
            "/project/src/auth.py",
            "/project/src/database.py",
            "/project/src/utils.py",
        ]
        result = SessionTypeDetector.detect_from_files(files)
        assert result == "refactor", f"Expected 'refactor', got '{result}'"

    def test_markdown_files_docs(self):
        """Test detection of docs session from markdown files."""
        files = [
            "/project/README.md",
            "/project/docs/API.md",
        ]
        result = SessionTypeDetector.detect_from_files(files)
        assert result == "docs", f"Expected 'docs', got '{result}'"

    def test_pytest_config_test(self):
        """Test detection of test session from pytest config files."""
        files = [
            "/project/pytest.ini",
            "/project/tests/conftest.py",
        ]
        result = SessionTypeDetector.detect_from_files(files)
        assert result == "test", f"Expected 'test', got '{result}'"

    def test_mixed_file_patterns(self):
        """Test mixed file patterns return 'mixed' session type."""
        files = [
            "/project/src/auth.py",  # refactor
            "/project/tests/test_auth.py",  # test
        ]
        result = SessionTypeDetector.detect_from_files(files)
        assert result == "mixed", f"Expected 'mixed', got '{result}'"

    def test_empty_file_list(self):
        """Test empty file list returns 'unknown'."""
        files = []
        result = SessionTypeDetector.detect_from_files(files)
        assert result == "unknown", f"Expected 'unknown', got '{result}'"

    def test_unrecognized_file_patterns(self):
        """Test files with unrecognized patterns return 'unknown'."""
        files = [
            "/project/data/config.json",
            "/project/assets/logo.png",
        ]
        result = SessionTypeDetector.detect_from_files(files)
        assert result == "unknown", f"Expected 'unknown', got '{result}'"


class TestSignalCombination:
    """Tests for combining message and file signals."""

    def test_agreeing_signals_debug(self):
        """Test agreeing debug signals return 'debug'."""
        message = "Fix the authentication bug"
        files = ["/project/logs/error.log"]
        result = SessionTypeDetector.detect_session_type(message, files)
        assert result == "debug", f"Expected 'debug', got '{result}'"

    def test_agreeing_signals_feature(self):
        """Test agreeing feature signals return 'feature'."""
        message = "Add new user profile"
        files = ["/project/src/user_profile.py"]
        result = SessionTypeDetector.detect_session_type(message, files)
        assert result == "feature", f"Expected 'feature', got '{result}'"

    def test_agreeing_signals_test(self):
        """Test agreeing test signals return 'test'."""
        message = "Verify the test coverage"
        files = ["/project/tests/test_api.py"]
        result = SessionTypeDetector.detect_session_type(message, files)
        assert result == "test", f"Expected 'test', got '{result}'"

    def test_conflicting_signals_returns_mixed(self):
        """Test conflicting signals return 'mixed'."""
        message = "Fix the bug"  # debug
        files = ["/project/README.md"]  # docs
        result = SessionTypeDetector.detect_session_type(message, files)
        assert result == "mixed", f"Expected 'mixed', got '{result}'"

    def test_message_signal_only(self):
        """Test message signal without files returns detected type."""
        message = "Add new feature"
        files = []
        result = SessionTypeDetector.detect_session_type(message, files)
        assert result == "feature", f"Expected 'feature', got '{result}'"

    def test_file_signal_only(self):
        """Test file signal without message returns detected type."""
        message = ""
        files = ["/project/tests/test_auth.py"]
        result = SessionTypeDetector.detect_session_type(message, files)
        assert result == "test", f"Expected 'test', got '{result}'"

    def test_no_signals_returns_unknown(self):
        """Test no signals returns 'unknown'."""
        message = ""
        files = []
        result = SessionTypeDetector.detect_session_type(message, files)
        assert result == "unknown", f"Expected 'unknown', got '{result}'"

    def test_weak_message_with_strong_files(self):
        """Test weak message signal (unknown) with strong file signal."""
        message = "hello world"
        files = ["/project/src/refactor.py"]
        result = SessionTypeDetector.detect_session_type(message, files)
        assert result == "refactor", f"Expected 'refactor', got '{result}'"

    def test_strong_message_with_weak_files(self):
        """Test strong message signal with weak file signal (unknown)."""
        message = "fix the crash bug"
        files = ["/project/data/config.json"]
        result = SessionTypeDetector.detect_session_type(message, files)
        assert result == "debug", f"Expected 'debug', got '{result}'"

    def test_multiple_conflicting_signals(self):
        """Test multiple conflicting signals return 'mixed'."""
        message = "add feature and fix bug"  # both feature + debug
        files = ["/project/README.md"]  # docs
        result = SessionTypeDetector.detect_session_type(message, files)
        assert result == "mixed", f"Expected 'mixed', got '{result}'"


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_none_message(self):
        """Test None message returns 'unknown'."""
        message = None
        files = []
        result = SessionTypeDetector.detect_session_type(message, files)
        assert result == "unknown", f"Expected 'unknown', got '{result}'"

    def test_none_files(self):
        """Test None files returns 'unknown'."""
        message = "fix bug"
        files = None
        result = SessionTypeDetector.detect_session_type(message, files)
        assert result == "unknown", f"Expected 'unknown', got '{result}'"

    def test_whitespace_only_message(self):
        """Test whitespace-only message returns 'unknown'."""
        message = "   \n\t  "
        files = []
        result = SessionTypeDetector.detect_session_type(message, files)
        assert result == "unknown", f"Expected 'unknown', got '{result}'"

    def test_very_long_message(self):
        """Test very long message is processed correctly."""
        message = "fix " + "bug " * 1000
        result = SessionTypeDetector.detect_from_message(message)
        assert result == "debug", f"Expected 'debug', got '{result}'"

    def test_special_characters_in_message(self):
        """Test message with special characters is handled."""
        message = "Fix the bug! @#$%^&*()_+"
        result = SessionTypeDetector.detect_from_message(message)
        assert result == "debug", f"Expected 'debug', got '{result}'"

    def test_unicode_in_message(self):
        """Test message with unicode characters is handled."""
        message = "Fix the bug in the café code"
        result = SessionTypeDetector.detect_from_message(message)
        assert result == "debug", f"Expected 'debug', got '{result}'"

    def test_keyword_at_message_boundary(self):
        """Test keyword at message start/end is detected."""
        message_start = "Fix the code"
        message_end = "the code needs fixing"
        result_start = SessionTypeDetector.detect_from_message(message_start)
        result_end = SessionTypeDetector.detect_from_message(message_end)
        # Should detect keyword variations
        assert result_start in ["debug", "unknown"], f"Unexpected result: '{result_start}'"
        assert result_end in ["debug", "unknown"], f"Unexpected result: '{result_end}'"

    def test_multiple_keywords_same_type(self):
        """Test multiple keywords of same type reinforce detection."""
        message = "Fix the bug and error in the code"
        result = SessionTypeDetector.detect_from_message(message)
        assert result == "debug", f"Expected 'debug', got '{result}'"


class TestPublicAPI:
    """Tests for the main public API."""

    def test_detect_session_type_integration(self):
        """Test full integration of session type detection."""
        # Real-world scenario: debugging test failures
        message = "Fix the failing test in auth module"
        files = [
            "/project/tests/test_auth.py",
            "/project/logs/pytest-error.log",
        ]
        result = SessionTypeDetector.detect_session_type(message, files)
        assert result == "debug", f"Expected 'debug', got '{result}'"

    def test_detect_session_type_feature_work(self):
        """Test detection for feature development work."""
        message = "Implement new user registration flow"
        files = [
            "/project/src/registration.py",
            "/project/src/forms.py",
        ]
        result = SessionTypeDetector.detect_session_type(message, files)
        assert result == "feature", f"Expected 'feature', got '{result}'"

    def test_detect_session_type_refactor_work(self):
        """Test detection for refactoring work."""
        message = "Simplify the authentication logic"
        files = [
            "/project/src/auth.py",
            "/project/src/utils.py",
        ]
        result = SessionTypeDetector.detect_session_type(message, files)
        assert result == "refactor", f"Expected 'refactor', got '{result}'"

    def test_detect_session_type_mixed_workspace(self):
        """Test detection for mixed workspace activity."""
        message = "Add tests and update docs"
        files = [
            "/project/tests/test_api.py",
            "/project/README.md",
        ]
        result = SessionTypeDetector.detect_session_type(message, files)
        assert result == "mixed", f"Expected 'mixed', got '{result}'"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])

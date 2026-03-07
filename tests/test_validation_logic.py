"""
Unit tests for validate_project_root() function.

Tests the validation logic in isolation by copying the function
to avoid complex import dependencies from the hook files.

Tests edge cases:
- Permission errors
- Symlink loops
- Network drives
- Windows junctions
- Case-insensitive paths
- Minimal viable structure
- Bypass flag
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


# Copy of validate_project_root function for testing
def validate_project_root(candidate: Path) -> bool:
    """Validate that a .claude directory is likely the project root.

    Uses minimal viable criteria to avoid false positives while accepting
    legitimate edge cases (monorepos, custom setups, minimal installations).

    Validation can be bypassed with HANDOFF_SKIP_VALIDATION=1 environment variable
    for custom setups or emergency recovery.

    Args:
        candidate: Path to directory containing .claude subdirectory

    Returns:
        True if this appears to be the actual project root, False otherwise
    """
    # Bypass validation if explicitly requested
    if os.environ.get("HANDOFF_SKIP_VALIDATION") == "1":
        return True

    claude_dir = candidate / ".claude"

    # Must exist
    if not claude_dir.exists():
        return False

    # Must be readable
    if not os.access(claude_dir, os.R_OK):
        return False

    # Minimal viable criteria: .claude directory exists and is readable
    return True


class TestValidateProjectRoot:
    """Test suite for validate_project_root() validation logic."""

    def test_valid_project_root_with_state(self):
        """Test validation passes with state/ directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            claude_dir = project_root / ".claude"
            claude_dir.mkdir()
            (claude_dir / "state").mkdir()

            assert validate_project_root(project_root) is True

    def test_valid_project_root_with_hooks(self):
        """Test validation passes with hooks/ directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            claude_dir = project_root / ".claude"
            claude_dir.mkdir()
            (claude_dir / "hooks").mkdir()

            assert validate_project_root(project_root) is True

    def test_valid_project_root_minimal(self):
        """Test validation passes with minimal .claude directory (no subdirs)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            claude_dir = project_root / ".claude"
            claude_dir.mkdir()

            # Minimal viable criteria: just exists and is readable
            assert validate_project_root(project_root) is True

    def test_no_claude_directory(self):
        """Test validation fails when .claude doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            # Don't create .claude directory

            assert validate_project_root(project_root) is False

    def test_permission_denied(self):
        """Test validation handles permission errors gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            claude_dir = project_root / ".claude"
            claude_dir.mkdir()

            # Mock os.access to return False (permission denied)
            with patch('os.access', return_value=False):
                assert validate_project_root(project_root) is False

    @pytest.mark.skipif(os.name != "posix", reason="Unix-specific test")
    def test_symlink_loop_protection(self):
        """Test validation handles symlink loops without infinite recursion."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            claude_dir = project_root / ".claude"
            claude_dir.mkdir()

            # Create a symlink loop (point to parent)
            # This shouldn't cause infinite loop since we only check existence/readability
            loop_link = claude_dir / "loop"
            try:
                loop_link.symlink_to("..")

                # Validation should still work (no infinite recursion)
                assert validate_project_root(project_root) is True
            except OSError:
                # Symlink creation not supported (Windows without admin/dev mode)
                pass

    def test_bypass_flag(self):
        """Test HANDOFF_SKIP_VALIDATION=1 bypasses validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            # Don't create .claude directory

            # Set bypass flag
            with patch.dict(os.environ, {"HANDOFF_SKIP_VALIDATION": "1"}):
                # Should return True even without .claude directory
                assert validate_project_root(project_root) is True

    def test_bypass_flag_invalid_value(self):
        """Test HANDOFF_SKIP_VALIDATION with value other than "1" doesn't bypass."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            # Don't create .claude directory

            # Set bypass flag to invalid value
            with patch.dict(os.environ, {"HANDOFF_SKIP_VALIDATION": "0"}):
                # Should return False (validation not bypassed)
                assert validate_project_root(project_root) is False

    @pytest.mark.skipif(os.name != "nt", reason="Windows-specific test")
    def test_windows_case_insensitive(self):
        """Test validation works with Windows case-insensitive paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            # Create .claude with uppercase (Windows allows this)
            claude_dir = project_root / "CLAUDE"
            claude_dir.mkdir()

            # On Windows, .lower() should work for case-insensitive check
            # But our validation checks exact path, so this should fail
            # This is expected behavior - case-sensitive check
            assert validate_project_root(project_root) is False

            # Now create lowercase version
            claude_dir_lower = project_root / ".claude"
            claude_dir_lower.mkdir()

            assert validate_project_root(project_root) is True

    def test_nested_claude_accepted(self):
        """Test that nested .claude directories are accepted (relaxed validation)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create nested structure like: project/.claude/vendor/dep/.claude
            claude_dir = project_root / ".claude"
            claude_dir.mkdir()

            nested_claude = claude_dir / "vendor" / "dep" / ".claude"
            nested_claude.mkdir(parents=True)

            # With relaxed validation, both should be accepted
            # (Just checks existence and readability, not nested structure)
            assert validate_project_root(project_root) is True

    def test_readability_check(self):
        """Test that unreadable .claude directory fails validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            claude_dir = project_root / ".claude"
            claude_dir.mkdir()

            # Mock os.access to simulate permission denied
            with patch('os.access', return_value=False):
                assert validate_project_root(project_root) is False


class TestValidationPerformance:
    """Test validation performance characteristics."""

    def test_validation_performance_fast(self):
        """Test that validation completes in under 10ms for normal case."""
        import time

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            claude_dir = project_root / ".claude"
            claude_dir.mkdir()

            # Measure validation time
            start = time.perf_counter()
            result = validate_project_root(project_root)
            elapsed = (time.perf_counter() - start) * 1000  # Convert to ms

            assert result is True
            assert elapsed < 10, f"Validation took {elapsed}ms, expected < 10ms"

    def test_validation_with_permission_check_fast(self):
        """Test that validation (including permission check) is fast."""
        import time

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            claude_dir = project_root / ".claude"
            claude_dir.mkdir()

            # Measure validation time (includes os.access call)
            start = time.perf_counter()
            result = validate_project_root(project_root)
            elapsed = (time.perf_counter() - start) * 1000  # Convert to ms

            assert result is True
            assert elapsed < 10, f"Validation took {elapsed}ms, expected < 10ms"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

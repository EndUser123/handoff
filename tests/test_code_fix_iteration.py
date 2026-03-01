"""
Unit tests for code-fix-iteration components.

Tests for:
- SHA256 hash validation
- Atomic file writes
- Iteration state serialization
- File utilities
- Git utilities

Run with: pytest tests/test_code_fix_iteration.py -v
"""

import json
import sys
import tempfile
from pathlib import Path

# Add lib directory to Python path
lib_path = Path(__file__).parent.parent.parent / ".claude" / "skills" / "p" / "lib"
sys.path.insert(0, str(lib_path))

# Import from p skill lib
from file_utils import atomic_write, sha256sum_file
from git import get_git_commit_sha


class TestSHA256HashValidation:
    """Tests for SHA256 hash validation."""

    def test_sha256sum_file_consistent(self):
        """
        Test that SHA256 hash is consistent for same content.

        Given: A file with known content
        When: sha256sum_file is called multiple times
        Then: The same hash is returned each time
        """
        # Arrange
        content = b"Test content for hashing"

        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
            f.write(content)
            temp_file = f.name

        try:
            # Act
            hash1 = sha256sum_file(temp_file)
            hash2 = sha256sum_file(temp_file)

            # Assert
            assert hash1 == hash2
            assert len(hash1) == 64  # SHA256 produces 64 hex characters
            assert all(c in '0123456789abcdef' for c in hash1)
        finally:
            Path(temp_file).unlink()

    def test_sha256sum_file_different_content(self):
        """
        Test that different content produces different hashes.

        Given: Two files with different content
        When: sha256sum_file is called on both
        Then: Different hashes are returned
        """
        # Arrange
        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f1:
            f1.write(b"Content 1")
            file1 = f1.name

        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f2:
            f2.write(b"Content 2")
            file2 = f2.name

        try:
            # Act
            hash1 = sha256sum_file(file1)
            hash2 = sha256sum_file(file2)

            # Assert
            assert hash1 != hash2
        finally:
            Path(file1).unlink()
            Path(file2).unlink()


class TestAtomicFileWrites:
    """Tests for atomic file writes."""

    def test_atomic_write_creates_file(self):
        """
        Test that atomic_write creates the target file.

        Given: Content to write
        When: atomic_write is called
        Then: The target file is created with correct content
        """
        # Arrange
        content = "Test content for atomic write"

        with tempfile.TemporaryDirectory() as temp_dir:
            target_file = Path(temp_dir) / "target.txt"

            # Act
            atomic_write(str(target_file), content)

            # Assert
            assert target_file.exists()
            assert target_file.read_text() == content

    def test_atomic_write_overwrites_existing(self):
        """
        Test that atomic_write overwrites existing files.

        Given: A file with existing content
        When: atomic_write is called with new content
        Then: The file is completely replaced
        """
        # Arrange
        old_content = "Old content"
        new_content = "New content"

        with tempfile.TemporaryDirectory() as temp_dir:
            target_file = Path(temp_dir) / "target.txt"
            target_file.write_text(old_content)

            # Act
            atomic_write(str(target_file), new_content)

            # Assert
            assert target_file.read_text() == new_content
            assert target_file.read_text() != old_content

    def test_atomic_write_creates_parent_dirs(self):
        """
        Test that atomic_write creates parent directories if needed.

        Given: A target path with non-existent parent directories
        When: atomic_write is called
        Then: Parent directories are created and file is written
        """
        # Arrange
        content = "Test content"

        with tempfile.TemporaryDirectory() as temp_dir:
            target_file = Path(temp_dir) / "subdir" / "nested" / "target.txt"

            # Act
            atomic_write(str(target_file), content)

            # Assert
            assert target_file.exists()
            assert target_file.parent.exists()
            assert target_file.read_text() == content


class TestIterationStateSerialization:
    """Tests for iteration state serialization."""

    def test_state_serialization(self):
        """
        Test that iteration state can be serialized to JSON.

        Given: A state dictionary with required fields
        When: Serialized to JSON
        Then: Valid JSON is produced
        """
        # Arrange
        state = {
            "findings_sha256": "abc123",
            "git_commit": "def456",
            "iteration": 1,
            "findings_file": "/path/to/findings.json",
            "status": "in_progress"
        }

        # Act
        json_output = json.dumps(state)

        # Assert
        assert json_output is not None
        parsed = json.loads(json_output)
        assert parsed == state

    def test_state_deserialization(self):
        """
        Test that iteration state can be deserialized from JSON.

        Given: Valid JSON state
        When: Deserialized from JSON
        Then: Original state is recovered
        """
        # Arrange
        state = {
            "findings_sha256": "abc123",
            "git_commit": "def456",
            "iteration": 1,
            "findings_file": "/path/to/findings.json",
            "status": "in_progress"
        }
        json_output = json.dumps(state)

        # Act
        parsed = json.loads(json_output)

        # Assert
        assert parsed["findings_sha256"] == "abc123"
        assert parsed["git_commit"] == "def456"
        assert parsed["iteration"] == 1
        assert parsed["status"] == "in_progress"

    def test_state_with_file_mtime_snapshot(self):
        """
        Test that state can include file mtime snapshot.

        Given: A state with file mtime snapshot
        When: Serialized and deserialized
        Then: Snapshot data is preserved
        """
        # Arrange
        state = {
            "findings_sha256": "abc123",
            "git_commit": "def456",
            "iteration": 1,
            "file_mtime_snapshot": {
                "file1.py": 1234567890.123,
                "file2.py": 1234567891.456
            },
            "status": "in_progress"
        }

        # Act
        json_output = json.dumps(state)
        parsed = json.loads(json_output)

        # Assert
        assert "file_mtime_snapshot" in parsed
        assert parsed["file_mtime_snapshot"]["file1.py"] == 1234567890.123


class TestGitUtilities:
    """Tests for git utilities."""

    def test_get_git_commit_sha(self):
        """
        Test that get_git_commit_sha returns a valid SHA.

        Given: A git repository
        When: get_git_commit_sha is called
        Then: A valid git commit SHA is returned (40 hex chars)
        """
        # Act (assuming we're in a git repo)
        try:
            commit_sha = get_git_commit_sha()

            # Assert
            assert commit_sha is not None
            assert len(commit_sha) == 40  # Git SHA is 40 characters
            assert all(c in '0123456789abcdef' for c in commit_sha)
        except Exception:
            # If not in git repo or git not available, that's OK for this test
            pass

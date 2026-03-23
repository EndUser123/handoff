#!/usr/bin/env python3
"""Tests for git_state module."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add scripts directory to path for direct import
handoff_scripts = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(handoff_scripts))

# Import directly from module to avoid __init__.py dependency issues
import importlib.util

spec = importlib.util.spec_from_file_location(
    "git_state", handoff_scripts / "hooks" / "__lib" / "git_state.py"
)
git_state = importlib.util.module_from_spec(spec)
spec.loader.exec_module(git_state)
capture_git_state = git_state.capture_git_state


@pytest.fixture
def non_git_dir(tmp_path: Path) -> Path:
    """Create a temporary directory that is not a git repository."""
    return tmp_path


@pytest.fixture
def git_dir(tmp_path: Path) -> Path:
    """Create a temporary git repository."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    return tmp_path


@pytest.fixture
def git_repo_with_commit(git_dir: Path) -> Path:
    """Create a git repository with an initial commit."""
    test_file = git_dir / "test.txt"
    test_file.write_text("Initial content")
    subprocess.run(
        ["git", "add", "test.txt"],
        cwd=git_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=git_dir,
        check=True,
        capture_output=True,
    )
    return git_dir


@pytest.fixture
def git_repo_with_uncommitted_changes(git_repo_with_commit: Path) -> Path:
    """Create a git repository with uncommitted changes."""
    (git_repo_with_commit / "modified.txt").write_text("Modified content")
    return git_repo_with_commit


def test_capture_git_state_non_git_directory(non_git_dir: Path) -> None:
    """Test that capture_git_state returns None for non-git directories."""
    result = capture_git_state(str(non_git_dir))
    assert result is None


def test_capture_git_state_clean_repo(git_repo_with_commit: Path) -> None:
    """Test that capture_git_state captures clean repository state."""
    result = capture_git_state(str(git_repo_with_commit))

    assert result is not None
    assert "branch" in result
    assert "has_uncommitted_changes" in result
    assert "last_commit" in result

    # Clean repo should have no uncommitted changes
    assert result["has_uncommitted_changes"] is False

    # Should have a branch (likely "main" or "master")
    assert result["branch"] in ["main", "master"]

    # Should have last commit info
    assert result["last_commit"] is not None
    assert "hash" in result["last_commit"]
    assert "message" in result["last_commit"]
    assert "timestamp" in result["last_commit"]


def test_capture_git_state_with_uncommitted_changes(
    git_repo_with_uncommitted_changes: Path,
) -> None:
    """Test that capture_git_state detects uncommitted changes."""
    result = capture_git_state(str(git_repo_with_uncommitted_changes))

    assert result is not None
    assert result["has_uncommitted_changes"] is True


def test_capture_git_state_with_untracked_files(git_repo_with_commit: Path) -> None:
    """Test that capture_git_state detects untracked files."""
    # Create an untracked file
    (git_repo_with_commit / "untracked.txt").write_text("Untracked content")

    result = capture_git_state(str(git_repo_with_commit))

    assert result is not None
    # Untracked files count as uncommitted changes
    assert result["has_uncommitted_changes"] is True


def test_capture_git_state_invalid_path() -> None:
    """Test that capture_git_state handles invalid paths gracefully."""
    result = capture_git_state("/nonexistent/path/that/does/not/exist")
    assert result is None


def test_capture_git_state_subprocess_timeout(git_dir: Path) -> None:
    """Test that capture_git_state handles subprocess timeouts gracefully."""
    with patch.object(git_state.subprocess, "run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=2)
        result = capture_git_state(str(git_dir))
        # Should return None on timeout instead of crashing
        assert result is None


def test_capture_git_state_subprocess_error(git_dir: Path) -> None:
    """Test that capture_git_state handles subprocess errors gracefully."""
    with patch.object(git_state.subprocess, "run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(
            cmd=["git", "status"], returncode=1
        )
        result = capture_git_state(str(git_dir))
        # Should return partial result with None for failed commands
        # (graceful degradation - branch detection still works with fallback)
        assert result is not None
        assert result["last_commit"] is None  # Last commit failed


def test_capture_git_state_detached_head(git_repo_with_commit: Path) -> None:
    """Test that capture_git_state handles detached HEAD state."""
    # Checkout a specific commit to create detached HEAD
    subprocess.run(
        ["git", "checkout", "HEAD~0"],
        cwd=git_repo_with_commit,
        check=True,
        capture_output=True,
    )

    result = capture_git_state(str(git_repo_with_commit))

    assert result is not None
    assert "branch" in result
    # Detached HEAD should be indicated
    assert result["branch"] == "HEAD"


def test_capture_git_state_multiple_branches(git_repo_with_commit: Path) -> None:
    """Test that capture_git_state correctly identifies current branch."""
    # Create and checkout a new branch
    subprocess.run(
        ["git", "checkout", "-b", "feature-branch"],
        cwd=git_repo_with_commit,
        check=True,
        capture_output=True,
    )

    result = capture_git_state(str(git_repo_with_commit))

    assert result is not None
    assert result["branch"] == "feature-branch"


def test_capture_git_state_staged_changes(git_repo_with_commit: Path) -> None:
    """Test that capture_git_state detects staged changes."""
    # Create and stage a file
    (git_repo_with_commit / "staged.txt").write_text("Staged content")
    subprocess.run(
        ["git", "add", "staged.txt"],
        cwd=git_repo_with_commit,
        check=True,
        capture_output=True,
    )

    result = capture_git_state(str(git_repo_with_commit))

    assert result is not None
    # Staged changes count as uncommitted changes
    assert result["has_uncommitted_changes"] is True

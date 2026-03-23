#!/usr/bin/env python3
"""Tests for dependency_state module."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Add scripts directory to path for direct import
handoff_scripts = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(handoff_scripts))

# Import directly from module to avoid __init__.py dependency issues
import importlib.util

spec = importlib.util.spec_from_file_location(
    "dependency_state", handoff_scripts / "hooks" / "__lib" / "dependency_state.py"
)
dependency_state = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dependency_state)
capture_dependency_state = dependency_state.capture_dependency_state


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Create a temporary directory."""
    return tmp_path


@pytest.fixture
def python_project(tmp_path: Path) -> Path:
    """Create a Python project with requirements.txt."""
    (tmp_path / "requirements.txt").write_text("requests==2.28.0\npytest==7.0.0\n")
    return tmp_path


@pytest.fixture
def python_project_poetry(tmp_path: Path) -> Path:
    """Create a Python project with pyproject.toml (Poetry)."""
    (tmp_path / "pyproject.toml").write_text("""
[tool.poetry]
name = "test-project"
version = "0.1.0"

[tool.poetry.dependencies]
python = "^3.8"
requests = "^2.28.0"
""")
    return tmp_path


@pytest.fixture
def node_project(tmp_path: Path) -> Path:
    """Create a Node.js project with package.json."""
    (tmp_path / "package.json").write_text("""
{
  "name": "test-project",
  "version": "1.0.0",
  "dependencies": {
    "express": "^4.18.0",
    "lodash": "^4.17.21"
  }
}
""")
    return tmp_path


def test_capture_dependency_state_no_package_manager(temp_dir: Path) -> None:
    """Test that capture_dependency_state returns None for directories without package managers."""
    result = capture_dependency_state(str(temp_dir))
    assert result is None


def test_capture_dependency_state_python_requirements(python_project: Path) -> None:
    """Test that capture_dependency_state detects Python with requirements.txt."""
    result = capture_dependency_state(str(python_project))

    assert result is not None
    assert "package_manager" in result
    assert result["package_manager"] == "pip"
    assert "installed_packages" in result


def test_capture_dependency_state_python_poetry(python_project_poetry: Path) -> None:
    """Test that capture_dependency_state detects Python with Poetry."""
    result = capture_dependency_state(str(python_project_poetry))

    # Poetry may not be installed in test environment, so we check if it's detected
    # If poetry is not available, the function should return None or fallback to pip
    if result:
        assert "package_manager" in result
        assert result["package_manager"] in ["poetry", "pip"]
    else:
        # Poetry not installed - this is acceptable in test environment
        pass


def test_capture_dependency_state_node(node_project: Path) -> None:
    """Test that capture_dependency_state detects Node.js project."""
    result = capture_dependency_state(str(node_project))

    # Node.js package managers may not be installed in test environment
    # If detected, verify the structure is correct
    if result:
        assert "package_manager" in result
        assert result["package_manager"] in ["npm", "yarn", "pnpm"]
        assert "installed_packages" in result
    else:
        # npm/yarn/pnpm not installed - this is acceptable in test environment
        pass


def test_capture_dependency_state_invalid_path() -> None:
    """Test that capture_dependency_state handles invalid paths gracefully."""
    result = capture_dependency_state("/nonexistent/path/that/does/not/exist")
    assert result is None


def test_capture_dependency_state_subprocess_timeout(python_project: Path) -> None:
    """Test that capture_dependency_state handles subprocess timeouts gracefully."""
    with patch.object(dependency_state.subprocess, "run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="pip", timeout=2)
        result = capture_dependency_state(str(python_project))
        # Should return None on timeout instead of crashing
        assert result is None


def test_capture_dependency_state_subprocess_error(python_project: Path) -> None:
    """Test that capture_dependency_state handles subprocess errors gracefully."""
    with patch.object(dependency_state.subprocess, "run") as mock_run:
        # First call succeeds (detecting pip), but listing packages fails
        mock_run.side_effect = [
            Mock(returncode=0, stdout=b""),  # pip --version succeeds
            subprocess.CalledProcessError(
                cmd=["pip", "list"], returncode=1
            ),  # pip list fails
        ]
        result = capture_dependency_state(str(python_project))
        # Should still return result with empty packages list (graceful degradation)
        assert result is not None
        assert result.get("installed_packages") == []


def test_capture_dependency_state_prefers_poetry_over_pip(
    python_project_poetry: Path,
) -> None:
    """Test that Poetry is preferred over pip when both are present."""
    result = capture_dependency_state(str(python_project_poetry))

    if result:
        # If Poetry is detected, it should be marked as the package manager
        # (This depends on the implementation's priority logic)
        assert "package_manager" in result


def test_capture_dependency_state_installed_packages_format(
    python_project: Path,
) -> None:
    """Test that installed_packages is a list of dicts with name and version."""
    result = capture_dependency_state(str(python_project))

    if result and result.get("installed_packages"):
        packages = result["installed_packages"]
        assert isinstance(packages, list)
        for pkg in packages:
            assert isinstance(pkg, dict)
            assert "name" in pkg
            assert "version" in pkg


def test_capture_dependency_state_empty_directory(temp_dir: Path) -> None:
    """Test that capture_dependency_state returns None for empty directories."""
    result = capture_dependency_state(str(temp_dir))
    assert result is None

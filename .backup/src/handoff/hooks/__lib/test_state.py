#!/usr/bin/env python3
"""
Test State Capture Module

Captures test results and coverage information from the project.
Supports pytest, jest, and cargo test frameworks.
"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def capture_test_state(project_root: Path) -> dict | None:
    """Capture test state from the project.

    Args:
        project_root: Path to the project root directory

    Returns:
        Dict with keys:
            - last_run: ISO timestamp of last test run (or None)
            - pass_count: int - number of passing tests
            - fail_count: int - number of failing tests
            - coverage_percentage: float | None - test coverage (0-100)
            - test_file_paths: list[str] - paths to test files found
        Returns None if no tests found or detection fails.

    Raises:
        subprocess.TimeoutExpired: If test discovery exceeds 2s timeout
    """
    try:
        # Find test files first
        test_files = _find_test_files(project_root)
        if not test_files:
            logger.info(f"[test_state] No test files found in {project_root}")
            return None

        # Detect test framework and parse results
        test_results = _parse_test_results(project_root, test_files)

        # Build result dict
        return {
            "last_run": datetime.now(UTC).isoformat(),
            "pass_count": test_results.get("pass_count", 0),
            "fail_count": test_results.get("fail_count", 0),
            "coverage_percentage": _get_coverage(project_root),
            "test_file_paths": test_files
        }

    except subprocess.TimeoutExpired:
        logger.warning(f"[test_state] Test state capture timed out for {project_root}")
        return None
    except Exception as e:
        logger.warning(f"[test_state] Failed to capture test state: {e}")
        return None


def _find_test_files(project_root: Path) -> list[str]:
    """Find test files in the project.

    Args:
        project_root: Path to the project root directory

    Returns:
        List of test file paths relative to project_root.
        Returns empty list if no tests found.
    """
    test_files = []

    # Common test directories and patterns
    test_patterns = [
        "tests/**/*.py",
        "test/**/*.py",
        "**/test_*.py",
        "**/*_test.py",
        "tests/**/*.js",
        "**/*.test.js",
        "tests/**/*.ts",
        "**/*.test.ts",
    ]

    try:
        # Use find to locate test files
        for pattern in test_patterns:
            result = subprocess.run(
                ["find", ".", "-name", pattern, "-type", "f"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line:
                        test_files.append(line)

        # Remove duplicates and sort
        test_files = sorted(set(test_files))

        # Limit to top 20 test files to avoid bloat
        if len(test_files) > 20:
            test_files = test_files[:20]

    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning(f"[test_state] Test file discovery failed: {e}")

    return test_files


def _parse_test_results(project_root: Path, test_files: list[str]) -> dict[str, int]:
    """Parse test results from the project.

    Args:
        project_root: Path to the project root directory
        test_files: List of test file paths

    Returns:
        Dict with pass_count and fail_count (both default to 0)
    """
    pass_count = 0
    fail_count = 0

    # Detect test framework
    if _is_pytest_project(project_root, test_files):
        # Try to read pytest cache or run pytest with --collect-only
        pytest_cache = project_root / ".pytest_cache"
        if pytest_cache.exists():
            # Try to read pytest cache JSON
            cache_file = pytest_cache / "v" / "cache" / "lastfailed"
            if cache_file.exists():
                try:
                    with open(cache_file) as f:
                        data = json.load(f)
                    # Parse pytest results
                    pass_count = data.get("summary", {}).get("passed", 0)
                    fail_count = data.get("summary", {}).get("failed", 0) + \
                               data.get("summary", {}).get("errors", 0)
                except (json.JSONDecodeError, OSError):
                    pass

    elif _is_jest_project(project_root, test_files):
        # Try to read Jest test results
        jest_results = project_root / "coverage" / "coverage-final.json"
        if jest_results.exists():
            try:
                with open(jest_results) as f:
                    data = json.load(f)
                # Parse Jest results
                success = data.get("success", True)
                pass_count = data.get("coverage", {}).get("covered", 0)
                fail_count = 0 if success else 1
            except (json.JSONDecodeError, OSError):
                pass

    elif _is_cargo_project(project_root, test_files):
        # Try to read Cargo test results
        # Cargo doesn't cache results by default, so we estimate
        pass_count = 0  # Unknown
        fail_count = 0

    return {"pass_count": pass_count, "fail_count": fail_count}


def _get_coverage(project_root: Path) -> float | None:
    """Get test coverage percentage.

    Args:
        project_root: Path to the project root directory

    Returns:
        Coverage percentage (0-100) or None if unavailable.
    """
    # Check for coverage files
    coverage_files = [
        project_root / ".coverage",
        project_root / "coverage.xml",
        project_root / "htmlcov" / "index.html",
        project_root / "coverage" / "coverage-final.json",
        project_root / "coverage" / "lcov.info",
    ]

    for cov_file in coverage_files:
        if cov_file.exists():
            # Parse coverage based on file type
            if cov_file.suffix == ".json":
                try:
                    with open(cov_file) as f:
                        data = json.load(f)
                    # Try common JSON coverage formats
                    if "total" in data and "covered" in data:
                        return (data["covered"] / data["total"]) * 100
                    elif "coverage" in data:
                        return data["coverage"].get("pct", None)
                except (json.JSONDecodeError, OSError):
                    pass
            elif cov_file.name == ".coverage":
                # Parse Python .coverage file
                try:
                    with open(cov_file) as f:
                        lines = f.readlines()
                    for line in lines:
                        if line.startswith("coverage: "):
                            # Format: "coverage: 85.2%"
                            try:
                                return float(line.split(":")[1].strip().rstrip('%'))
                            except (ValueError, IndexError):
                                pass
                except OSError:
                    pass

    return None


def _is_pytest_project(project_root: Path, test_files: list[str]) -> bool:
    """Check if project uses pytest.

    Args:
        project_root: Path to the project root directory
        test_files: List of test file paths

    Returns:
        True if pytest is detected.
    """
    # Check for pytest configuration files
    pytest_configs = [
        project_root / "pytest.ini",
        project_root / "pyproject.toml",
        project_root / "setup.cfg",
        project_root / "tox.ini",
    ]

    for config in pytest_configs:
        if config.exists():
            # Check if config mentions pytest
            try:
                with open(config) as f:
                    content = f.read()
                if "pytest" in content.lower():
                    return True
            except OSError:
                pass

    # Check test file patterns
    for test_file in test_files[:5]:  # Check first 5 files
        if "test_" in test_file or "_test.py" in test_file:
            # Read file to check for pytest usage
            test_file_path = project_root / test_file
            if test_file_path.exists():
                try:
                    with open(test_file_path) as f:
                        content = f.read()
                    if "def test_" in content or "pytest" in content:
                        return True
                except OSError:
                    pass

    return False


def _is_jest_project(project_root: Path, test_files: list[str]) -> bool:
    """Check if project uses Jest.

    Args:
        project_root: Path to the project root directory
        test_files: List of test file paths

    Returns:
        True if Jest is detected.
    """
    # Check for Jest configuration files
    jest_configs = [
        project_root / "jest.config.js",
        project_root / "jest.config.json",
        project_root / "package.json",
    ]

    for config in jest_configs:
        if config.exists():
            try:
                with open(config) as f:
                    content = f.read()
                if "jest" in content.lower():
                    return True
            except OSError:
                pass

    # Check test file patterns
    for test_file in test_files[:5]:
        if ".test.js" in test_file or ".test.ts" in test_file:
            return True

    return False


def _is_cargo_project(project_root: Path, test_files: list[str]) -> bool:
    """Check if project uses cargo test.

    Args:
        project_root: Path to the project root directory
        test_files: List of test file paths

    Returns:
        True if Cargo is detected.
    """
    # Check for Cargo.toml
    cargo_toml = project_root / "Cargo.toml"
    if cargo_toml.exists():
        try:
            with open(cargo_toml) as f:
                content = f.read()
            # Check for dev-dependencies with test frameworks
            if "tokio" in content.lower() or "test" in content.lower():
                return True
        except OSError:
            pass

    # Check for tests directory
    tests_dir = project_root / "tests"
    if tests_dir.exists():
        return True

    return False

#!/usr/bin/env python3
"""Dependency state capture for handoff system.

This module provides terminal-isolation-safe dependency capture,
detecting package managers and installed packages.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Timeout for package manager operations (seconds)
PKG_TIMEOUT = 2


def capture_dependency_state(project_root: str) -> dict | None:
    """Capture dependency state from project.

    Detects:
    - Package manager (pip, poetry, npm, yarn, pnpm)
    - Installed packages with versions

    Args:
        project_root: Path to project directory (must exist and be accessible)

    Returns:
        Dict with dependency state or None if:
        - No package manager detected
        - Operations fail or timeout
        - Path is invalid

    Example:
        >>> state = capture_dependency_state("/path/to/project")
        >>> if state:
        ...     print(f"Manager: {state['package_manager']}")
        ...     print(f"Packages: {len(state['installed_packages'])}")
    """
    # Validate path before subprocess calls
    if not project_root:
        logger.warning("[DependencyState] No project root provided")
        return None

    project_path = Path(project_root)

    # Check if path exists and is accessible
    try:
        if not project_path.exists():
            logger.warning(f"[DependencyState] Path does not exist: {project_root}")
            return None

        if not project_path.is_dir():
            logger.warning(f"[DependencyState] Path is not a directory: {project_root}")
            return None

    except OSError as e:
        logger.warning(f"[DependencyState] Error accessing path {project_root}: {e}")
        return None

    # Detect package manager
    package_manager = _detect_package_manager(project_path)
    if not package_manager:
        logger.info(f"[DependencyState] No package manager detected in {project_root}")
        return None

    # Get installed packages
    try:
        installed_packages = _get_installed_packages(package_manager, project_path)
        return {
            "package_manager": package_manager,
            "installed_packages": installed_packages,
        }

    except subprocess.TimeoutExpired:
        logger.warning(
            f"[DependencyState] Package manager operation timeout in {project_root}"
        )
        return None
    except subprocess.CalledProcessError as e:
        logger.warning(
            f"[DependencyState] Package manager command failed: {e.cmd} returned {e.returncode}"
        )
        # Return graceful degradation with empty packages list
        return {
            "package_manager": package_manager,
            "installed_packages": [],
        }
    except OSError as e:
        logger.warning(f"[DependencyState] OS error during package operations: {e}")
        return None
    except Exception as e:
        logger.warning(
            f"[DependencyState] Unexpected error capturing dependency state: {e}"
        )
        return None


def _detect_package_manager(project_path: Path) -> str | None:
    """Detect which package manager is used in the project.

    Priority: Poetry > pip > npm/yarn/pnpm

    Returns:
        Package manager name or None
    """
    # Check for Python package managers
    if (project_path / "pyproject.toml").exists():
        # Check if it's a Poetry project
        try:
            pyproject_content = (project_path / "pyproject.toml").read_text()
            if "[tool.poetry]" in pyproject_content:
                return "poetry"
        except OSError:
            pass

    if (project_path / "requirements.txt").exists() or (
        project_path / "setup.py"
    ).exists():
        # Verify pip is available
        if _command_available(["pip", "--version"]):
            return "pip"

    if (project_path / "Pipfile").exists():
        return "pipenv"

    # Check for Node.js package managers
    if (project_path / "package.json").exists():
        # Detect which Node.js package manager is available
        if _command_available(["pnpm", "--version"]):
            return "pnpm"
        elif _command_available(["yarn", "--version"]):
            return "yarn"
        elif _command_available(["npm", "--version"]):
            return "npm"

    # No package manager detected
    return None


def _command_available(cmd: list[str]) -> bool:
    """Check if a command is available.

    Args:
        cmd: Command list to test

    Returns:
        True if command succeeds, False otherwise
    """
    try:
        subprocess.run(
            cmd,
            capture_output=True,
            timeout=PKG_TIMEOUT,
            check=False,
        )
        return True
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        return False


def _get_installed_packages(package_manager: str, project_path: Path) -> list[dict]:
    """Get list of installed packages.

    Args:
        package_manager: Detected package manager
        project_path: Project directory path

    Returns:
        List of dicts with 'name' and 'version' keys
    """
    if package_manager == "pip":
        return _get_pip_packages()
    elif package_manager == "poetry":
        return _get_poetry_packages(project_path)
    elif package_manager == "pipenv":
        return _get_pipenv_packages(project_path)
    elif package_manager in ["npm", "yarn", "pnpm"]:
        return _get_npm_packages(package_manager)
    else:
        return []


def _get_pip_packages() -> list[dict]:
    """Get packages installed via pip.

    Returns:
        List of dicts with 'name' and 'version'
    """
    try:
        result = subprocess.run(
            ["pip", "list", "--format=json"],
            capture_output=True,
            text=True,
            timeout=PKG_TIMEOUT,
            check=True,
        )

        packages = json.loads(result.stdout)
        return [{"name": pkg["name"], "version": pkg["version"]} for pkg in packages]

    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError):
        return []


def _get_poetry_packages(project_path: Path) -> list[dict]:
    """Get packages from Poetry project.

    Returns:
        List of dicts with 'name' and 'version'
    """
    try:
        result = subprocess.run(
            ["poetry", "show", "--format=json"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=PKG_TIMEOUT,
            check=False,
        )

        if result.returncode != 0:
            # Poetry might not be initialized, try pip as fallback
            return _get_pip_packages()

        packages = json.loads(result.stdout)
        return [{"name": pkg["name"], "version": pkg["version"]} for pkg in packages]

    except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError):
        return []


def _get_pipenv_packages(project_path: Path) -> list[dict]:
    """Get packages from Pipenv project.

    Returns:
        List of dicts with 'name' and 'version'
    """
    try:
        result = subprocess.run(
            ["pipenv", "run", "pip", "list", "--format=json"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=PKG_TIMEOUT,
            check=False,
        )

        if result.returncode != 0:
            return []

        packages = json.loads(result.stdout)
        return [{"name": pkg["name"], "version": pkg["version"]} for pkg in packages]

    except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError):
        return []


def _get_npm_packages(package_manager: str) -> list[dict]:
    """Get packages from npm/yarn/pnpm.

    Args:
        package_manager: One of 'npm', 'yarn', 'pnpm'

    Returns:
        List of dicts with 'name' and 'version'
    """
    try:
        if package_manager == "npm":
            cmd = ["npm", "list", "--json", "--depth=0"]
        elif package_manager == "yarn":
            cmd = ["yarn", "list", "--json"]
        else:  # pnpm
            cmd = ["pnpm", "list", "--json", "--depth=0"]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=PKG_TIMEOUT,
            check=False,
        )

        if result.returncode != 0:
            return []

        data = json.loads(result.stdout)

        # npm/yarn/pnpm have different JSON structures
        packages = []

        if "dependencies" in data:
            # npm format
            for name, info in data["dependencies"].items():
                if isinstance(info, dict) and "version" in info:
                    packages.append({"name": name, "version": info["version"]})

        return packages

    except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError):
        return []

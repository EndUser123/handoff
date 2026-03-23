#!/usr/bin/env python3
"""Parallel capture execution for handoff system.

This module executes capture operations in parallel using ThreadPoolExecutor,
reducing total capture time from ~6s (sequential) to ~2s (parallel).
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

logger = logging.getLogger(__name__)

# Capture timeout (seconds)
CAPTURE_TIMEOUT = 2

# Thread pool size (one per capture module)
THREAD_POOL_SIZE = 4


def capture_all_parallel(project_root: Path, transcript: str) -> dict:
    """Execute all capture operations in parallel.

    Captures:
    - git_state: Git repository state (branch, uncommitted changes, last commit)
    - dependency_state: Project dependencies and package management
    - test_state: Test framework availability and recent test results
    - architectural_context: Project structure and key files

    Args:
        project_root: Path to project root directory
        transcript: Transcript content for context extraction

    Returns:
        Dict with capture results (keys: git_state, dependency_state,
        test_state, architectural_context). Failed captures return None.

    Example:
        >>> result = capture_all_parallel(Path("/path/to/project"), "transcript content")
        >>> print(result['git_state']['branch'])
        'main'
    """
    results = {
        "git_state": None,
        "dependency_state": None,
        "test_state": None,
        "architectural_context": None,
    }

    # Define capture tasks
    capture_tasks = [
        ("git_state", _capture_git_state, project_root),
        ("dependency_state", _capture_dependency_state, project_root),
        ("test_state", _capture_test_state, project_root),
        (
            "architectural_context",
            _capture_architectural_context,
            project_root,
            transcript,
        ),
    ]

    # Execute captures in parallel
    with ThreadPoolExecutor(max_workers=THREAD_POOL_SIZE) as executor:
        # Submit all tasks
        futures = {
            executor.submit(task[1], *task[2:]): task[0] for task in capture_tasks
        }

        # Collect results with timeout
        try:
            for future in as_completed(futures, timeout=CAPTURE_TIMEOUT):
                task_name = futures[future]
                try:
                    results[task_name] = future.result()
                    logger.debug(f"[ParallelCapture] {task_name} captured successfully")
                except Exception as e:
                    logger.warning(f"[ParallelCapture] {task_name} failed: {e}")
                    results[task_name] = None
        except TimeoutError:
            # Handle timeout for incomplete futures
            logger.warning(f"[ParallelCapture] Timeout after {CAPTURE_TIMEOUT}s")
            # Cancel remaining futures and mark as None
            for future in futures:
                if not future.done():
                    future.cancel()
                    task_name = futures[future]
                    results[task_name] = None

    return results


def _capture_git_state(project_root: Path) -> dict | None:
    """Capture git repository state.

    Args:
        project_root: Path to project root directory

    Returns:
        Git state dict or None if capture fails
    """
    try:
        # Import here to avoid issues if module doesn't exist
        from scripts.hooks.__lib.git_state import capture_git_state

        return capture_git_state(str(project_root))
    except ImportError:
        logger.warning("[ParallelCapture] git_state module not available")
        return None
    except Exception as e:
        logger.warning(f"[ParallelCapture] git_state capture failed: {e}")
        return None


def _capture_dependency_state(project_root: Path) -> dict | None:
    """Capture project dependency state.

    Args:
        project_root: Path to project root directory

    Returns:
        Dependency state dict or None if capture fails
    """
    try:
        # Import here to avoid issues if module doesn't exist
        from scripts.hooks.__lib.dependency_state import capture_dependency_state

        return capture_dependency_state(str(project_root))
    except ImportError:
        logger.warning("[ParallelCapture] dependency_state module not available")
        return None
    except Exception as e:
        logger.warning(f"[ParallelCapture] dependency_state capture failed: {e}")
        return None


def _capture_test_state(project_root: Path) -> dict | None:
    """Capture test framework state.

    Args:
        project_root: Path to project root directory

    Returns:
        Test state dict or None if capture fails
    """
    try:
        # Import here to avoid issues if module doesn't exist
        from scripts.hooks.__lib.test_state import capture_test_state

        return capture_test_state(str(project_root))
    except ImportError:
        logger.warning("[ParallelCapture] test_state module not available")
        return None
    except Exception as e:
        logger.warning(f"[ParallelCapture] test_state capture failed: {e}")
        return None


def _capture_architectural_context(project_root: Path, transcript: str) -> dict | None:
    """Capture architectural context from project.

    Args:
        project_root: Path to project root directory
        transcript: Transcript content for context extraction

    Returns:
        Architectural context dict or None if capture fails
    """
    try:
        # Import here to avoid issues if module doesn't exist
        from scripts.hooks.__lib.architectural_context import (
            capture_architectural_context,
        )

        return capture_architectural_context(str(project_root), transcript)
    except ImportError:
        logger.warning("[ParallelCapture] architectural_context module not available")
        return None
    except Exception as e:
        logger.warning(f"[ParallelCapture] architectural_context capture failed: {e}")
        return None

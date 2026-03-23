#!/usr/bin/env python3
"""Project root detection utilities for handoff system.

This module provides robust project root detection that works correctly
when hooks are executed from the .claude/hooks/ directory.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def detect_project_root(
    transcript_path: str | None = None,
    current_dir: Path | None = None,
    max_depth: int = 10
) -> Path:
    """Detect project root using multiple strategies with fallbacks.

    Strategy priority:
    1. transcriptPath (most reliable - from hook input)
    2. current_dir with hooks-aware traversal (handles .claude/hooks/ execution)
    3. Path.cwd() with smart traversal (last resort)

    Args:
        transcript_path: Optional transcript path from hook input
        current_dir: Optional current directory (defaults to Path.cwd())
        max_depth: Maximum parent directories to search

    Returns:
        Detected project root path

    Raises:
        ValueError: If project root cannot be detected
    """
    # Strategy 1: Use transcriptPath (most reliable)
    if transcript_path:
        try:
            transcript_path_obj = Path(transcript_path)
            # Resolve to absolute path if possible
            try:
                transcript_path_obj = transcript_path_obj.resolve()
            except (OSError, RuntimeError):
                # Fallback to unresolved path if resolution fails
                pass

            # Start from transcript parent and search up
            candidate = transcript_path_obj.parent
            for _ in range(max_depth):
                if (candidate / ".claude").exists():
                    logger.info(
                        f"[ProjectRoot] Found root via transcriptPath: {candidate} "
                        f"(from transcript: {transcript_path})"
                    )
                    return candidate
                if candidate == candidate.parent:
                    break  # Reached filesystem root
                candidate = candidate.parent

        except Exception as e:
            logger.warning(
                f"[ProjectRoot] transcriptPath detection failed: {e}, "
                "falling back to directory traversal"
            )

    # Strategy 2: Use current_dir with hooks-aware traversal
    if current_dir is None:
        current_dir = Path.cwd()

    # Check if we're inside .claude/hooks/ or .claude/ already
    current_dir_str = str(current_dir).replace("\\", "/")
    hooks_markers = ["/.claude/hooks/", "/.claude/hooks"]
    claude_markers = ["/.claude/", "/.claude"]

    # Find where we are in the directory hierarchy
    project_root = current_dir
    traversal_start = project_root

    # If we're inside .claude/hooks/, navigate to parent of .claude
    for hooks_marker in hooks_markers:
        if hooks_marker in current_dir_str:
            # We're inside .claude/hooks/, navigate up to parent of .claude
            # The actual project root is TWO levels up from hooks/ directory
            # hooks/ → .claude/ → project_root
            project_root = current_dir.parent.parent

            # Verify it has .claude (this should be project_root/.claude)
            if (project_root / ".claude").exists():
                logger.info(
                    f"[ProjectRoot] Found root via hooks-aware traversal: {project_root} "
                    f"(started from: {current_dir})"
                )
                return project_root

    # If we're inside .claude/ (but not hooks/), navigate to parent
    for claude_marker in claude_markers:
        if claude_marker in current_dir_str and not any(m in current_dir_str for m in hooks_markers):
            # We're inside .claude/ but not .claude/hooks/
            parts = current_dir_str.split(claude_marker)
            if len(parts) >= 2:
                root_part = parts[0]
                project_root = Path(root_part) if root_part else current_dir.parent

                # Verify it has .claude
                if (project_root / ".claude").exists():
                    logger.info(
                        f"[ProjectRoot] Found root via .claude parent traversal: {project_root} "
                        f"(started from: {current_dir})"
                    )
                    return project_root

    # Strategy 3: Standard upward traversal (original logic)
    project_root = current_dir
    for depth in range(max_depth):
        if (project_root / ".claude").exists():
            logger.info(
                f"[ProjectRoot] Found root via standard traversal at depth {depth}: {project_root} "
                f"(started from: {current_dir})"
            )
            return project_root
        if project_root == project_root.parent:
            break  # Reached filesystem root
        project_root = project_root.parent

    # All strategies failed
    raise ValueError(
        f"Cannot detect project root from {current_dir}. "
        f"Searched {max_depth} directories up. "
        f"transcript_path was: {transcript_path}"
    )

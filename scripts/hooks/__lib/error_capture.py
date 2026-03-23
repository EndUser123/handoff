#!/usr/bin/env python3
"""
Error Capture Module

Filters terminal-specific vs project-level errors from transcript.
Terminal-specific errors (file not found, command not found) are excluded.
Project-level errors (test failures, import errors, logic bugs) are included.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def capture_recent_errors(transcript: str, project_root: Path) -> dict | None:
    """Capture project-level errors from the chat transcript.

    Args:
        transcript: Chat transcript text
        project_root: Path to the project root directory

    Returns:
        Dict with keys:
            - errors: list[dict] - project-level errors with metadata
            - total_count: int - total number of errors
        Returns None if no errors found or parsing fails.

    Raises:
        None: This function does not raise exceptions, returns None on failure
    """
    try:
        if not transcript or not transcript.strip():
            logger.info("[error_capture] Empty transcript provided")
            return None

        # Extract errors from transcript
        all_errors = _extract_errors(transcript)

        # Filter out terminal-specific errors
        project_errors = _filter_terminal_specific_errors(all_errors)

        if not project_errors:
            logger.info("[error_capture] No project-level errors found in transcript")
            return None

        # Build result dict
        return {"errors": project_errors, "total_count": len(project_errors)}

    except Exception as e:
        logger.warning(f"[error_capture] Failed to capture recent errors: {e}")
        return None


def _extract_errors(transcript: str) -> list[dict]:
    """Extract errors from transcript.

    Args:
        transcript: Chat transcript text

    Returns:
        List of error dicts with keys:
            - error_message: str - error text
            - error_type: str - error type (exception, test_failure, syntax_error, etc.)
            - context: str | None - surrounding context snippet
    """
    errors = []

    # Error patterns (common error indicators)
    error_patterns = [
        # Python exceptions
        r"(Traceback \(most recent call last\):.*?(?:Error|Exception|Warning):[^\n]+)",
        # Test failures
        r"(?:FAILED|ERROR|FAIL)\s+(?:\S+\s+)+.*?(?=\n|$)",
        # Syntax errors
        r"(?:SyntaxError|IndentationError|TabError):[^\n]+",
        # Import errors
        r"(?:ImportError|ModuleNotFoundError):[^\n]+",
        # Type errors
        r"(?:TypeError|ValueError|AttributeError|KeyError|IndexError):[^\n]+",
        # File not found (will be filtered later if terminal-specific)
        r"(?:FileNotFoundError|File not found):[^\n]+",
        # Command not found (will be filtered later - terminal-specific)
        r"(?:command not found|not recognized as an internal or external command):[^\n]+",
        # Generic error patterns
        r"(?:Error:|ERROR:|\[ERROR\]).*?(?=\n|$)",
    ]

    lines = transcript.split("\n")

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Check if this line contains an error
        for pattern in error_patterns:
            match = re.search(pattern, stripped, re.MULTILINE | re.DOTALL)
            if match:
                error_text = match.group(1) if match.groups() else match.group(0)
                error_text = error_text.strip()

                # Minimum length filter (avoid single words)
                if len(error_text) < 10:
                    continue

                # Get surrounding context
                context_start = max(0, i - 2)
                context_end = min(len(lines), i + 3)
                context = "\n".join(lines[context_start:context_end]).strip()

                # Classify error type
                error_type = _classify_error(error_text)

                errors.append(
                    {
                        "error_message": error_text,
                        "error_type": error_type,
                        "context": context[:500],  # Limit context to 500 chars
                    }
                )

    # Limit to top 20 errors to avoid bloat
    errors = errors[:20]

    return errors


def _classify_error(error_message: str) -> str:
    """Classify error by type.

    Args:
        error_message: Error message text

    Returns:
        Error type: exception, test_failure, syntax_error, import_error, or other
    """
    error_lower = error_message.lower()

    # Test failures
    if re.search(r"\b(?:failed|error|fail)\s+\w+\s*(?:test|spec)", error_lower):
        return "test_failure"

    # Python exceptions
    if re.search(r"\b(?:Error|Exception|Warning):", error_message):
        # Extract specific exception type
        match = re.search(r"(\w+Error|\w+Exception|\w+Warning):", error_message)
        if match:
            exception_type = match.group(1)
            # Map common exceptions to categories
            if exception_type in ("ImportError", "ModuleNotFoundError"):
                return "import_error"
            elif exception_type in ("SyntaxError", "IndentationError", "TabError"):
                return "syntax_error"
            elif exception_type in ("TypeError", "ValueError", "AttributeError"):
                return exception_type.lower()
        return "exception"

    # Syntax errors
    if re.search(r"syntaxerror", error_lower):
        return "syntax_error"

    # Import errors
    if re.search(r"importerror|modulenotfounderror", error_lower):
        return "import_error"

    return "other"


def _filter_terminal_specific_errors(errors: list[dict]) -> list[dict]:
    """Filter out terminal-specific errors, keep project-level errors.

    Terminal-specific errors (exclude):
    - File not found errors for user-specific paths
    - Command not found errors
    - Permission errors for system directories

    Project-level errors (include):
    - Test failures
    - Import errors for project dependencies
    - Syntax errors in project files
    - Logic errors (TypeError, ValueError, etc.)

    Args:
        errors: List of error dicts

    Returns:
        Filtered list containing only project-level errors
    """
    project_errors = []

    # Terminal-specific error patterns
    terminal_specific_patterns = [
        r"command not found",
        r"not recognized as an internal or external command",
        r"no such file or directory.*?(?:/\.(?:bash|zsh|git)|/home|/users?|/tmp)",
        r"permission denied.*?(?:/\.(?:bash|zsh|git)|/home|/users?|/tmp)",
        r"file not found.*?\.(?:bash|zsh|sh|ps1)",
    ]

    for error in errors:
        error_message = error["error_message"].lower()
        error_type = error.get("error_type", "other")

        # Exclude terminal-specific errors
        is_terminal_specific = False
        for pattern in terminal_specific_patterns:
            if re.search(pattern, error_message):
                is_terminal_specific = True
                break

        if is_terminal_specific:
            continue

        # Include project-level errors
        project_errors.append(error)

    return project_errors

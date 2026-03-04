"""SessionTypeDetector module for analyzing development session context.

Determines session type (debug, feature, refactor, test, docs, mixed, unknown)
by analyzing user messages and active file patterns.
"""

from pathlib import Path
from typing import Final


# Session type constants
DEBUG: Final = "debug"
FEATURE: Final = "feature"
REFACTOR: Final = "refactor"
TEST: Final = "test"
DOCS: Final = "docs"
MIXED: Final = "mixed"
UNKNOWN: Final = "unknown"


class SessionTypeDetector:
    """Detects development session type from message content and file patterns."""

    # Keyword patterns for each session type
    DEBUG_KEYWORDS: Final = (
        "fix", "bug", "error", "broken", "fails", "crash",
    )

    FEATURE_KEYWORDS: Final = (
        "add", "implement", "create", "build", "new",
    )

    REFACTOR_KEYWORDS: Final = (
        "refactor", "clean up", "simplify", "optimize", "restructure",
    )

    TEST_KEYWORDS: Final = (
        "test", "verify", "coverage", "assert", "pytest",
    )

    DOCS_KEYWORDS: Final = (
        "document", "readme", "comment", "explain", "docstring",
    )

    # Priority for tie-breaking (higher priority = lower index)
    _TYPE_PRIORITY = {DEBUG: 0, FEATURE: 1, REFACTOR: 2, TEST: 3, DOCS: 4}

    @classmethod
    def detect_from_message(cls, message: str | None) -> str:
        """Analyze message content for session type keywords.

        Args:
            message: User message to analyze

        Returns:
            Session type: 'debug', 'feature', 'refactor', 'test', 'docs', 'mixed', 'unknown'
        """
        if not message or not message.strip():
            return UNKNOWN

        message_lower = message.lower()

        # Count keyword matches for each session type
        scores = {
            DEBUG: 0,
            FEATURE: 0,
            REFACTOR: 0,
            TEST: 0,
            DOCS: 0,
        }

        # Score each session type by keyword matches
        for keyword in cls.DEBUG_KEYWORDS:
            if keyword in message_lower:
                scores[DEBUG] += message_lower.count(keyword)
        for keyword in cls.FEATURE_KEYWORDS:
            if keyword in message_lower:
                scores[FEATURE] += message_lower.count(keyword)
        for keyword in cls.REFACTOR_KEYWORDS:
            if keyword in message_lower:
                scores[REFACTOR] += message_lower.count(keyword)
        for keyword in cls.TEST_KEYWORDS:
            if keyword in message_lower:
                scores[TEST] += message_lower.count(keyword)
        for keyword in cls.DOCS_KEYWORDS:
            if keyword in message_lower:
                scores[DOCS] += message_lower.count(keyword)

        # Get types with non-zero scores
        detected_types = [(session_type, score) for session_type, score in scores.items() if score > 0]

        # Sort by score descending, then by priority
        detected_types.sort(key=lambda x: (x[1], -cls._TYPE_PRIORITY[x[0]]), reverse=True)

        if not detected_types:
            return UNKNOWN

        # If there are 3+ types with the same top score, return mixed
        if len(detected_types) >= 3:
            top_score = detected_types[0][1]
            top_types = [t for t, s in detected_types if s == top_score]
            if len(top_types) >= 3:
                return MIXED

        # Use priority to break ties - return top type
        return detected_types[0][0]

    @classmethod
    def detect_from_files(cls, files: list[str] | None) -> str:
        """Analyze file paths for session type patterns.

        Args:
            files: List of file paths to analyze

        Returns:
            Session type: 'debug', 'feature', 'refactor', 'test', 'docs', 'mixed', 'unknown'
        """
        if not files:
            return UNKNOWN

        detected_types = set()

        for file_path in files:
            path_str = str(file_path)
            path_lower = path_str.lower()

            # Check debug patterns (error logs, traceback)
            if "error.log" in path_lower or "traceback" in path_lower:
                detected_types.add(DEBUG)
            
            # Check test patterns (test files, pytest config)
            elif ("test_" in path_lower and path_lower.endswith(".py")) or                  "_test.py" in path_lower or                  "pytest.ini" in path_lower or                  "conftest.py" in path_lower:
                detected_types.add(TEST)
            
            # Check docs patterns (markdown files)
            elif path_lower.endswith(".md") or "readme" in path_lower or                  ("doc/" in path_lower and path_lower.endswith(".rst")):
                detected_types.add(DOCS)
            
            # Check feature patterns:
            # - Files with "new" in the name
            # - Files in src/api/ or lib/api/ (new API endpoints)
            elif ("new" in path_lower and path_lower.endswith(".py")) or                  (("src/api/" in path_lower or "lib/api/" in path_lower) and path_lower.endswith(".py")):
                detected_types.add(FEATURE)
            
            # Check refactor patterns (other .py files in src/lib)
            elif ("src/" in path_lower or "lib/" in path_lower) and                  path_lower.endswith(".py") and                  "test_" not in path_lower and                  "_test.py" not in path_lower and                  "/api/" not in path_lower:
                detected_types.add(REFACTOR)
            
            # Check refactor patterns for other .py files
            elif path_lower.endswith(".py") and                  "test_" not in path_lower and                  "_test.py" not in path_lower:
                detected_types.add(REFACTOR)

        # Return single type or MIXED if multiple detected
        if len(detected_types) == 1:
            return detected_types.pop()
        elif len(detected_types) > 1:
            return MIXED
        else:
            return UNKNOWN

    @classmethod
    def detect_session_type(
        cls,
        last_message: str | None,
        active_files: list[str] | None
    ) -> str:
        """Detect session type by combining message and file analysis.

        Args:
            last_message: Last user message from transcript
            active_files: List of active file paths

        Returns:
            Session type: 'debug', 'feature', 'refactor', 'test', 'docs', 'mixed', 'unknown'
        """
        # If either input is None, return unknown (not enough data)
        if last_message is None or active_files is None:
            return UNKNOWN

        # Handle empty inputs
        message = last_message if last_message else ""
        files = active_files if active_files else []

        # Detect from both signals
        message_type = cls.detect_from_message(message)
        file_type = cls.detect_from_files(files)

        # Handle None/empty cases
        if message_type == UNKNOWN and file_type == UNKNOWN:
            return UNKNOWN

        # If one signal is unknown, use the other
        if message_type == UNKNOWN:
            return file_type
        if file_type == UNKNOWN:
            return message_type

        # If both signals agree, return that type
        if message_type == file_type:
            return message_type

        # If one signal is mixed and the other is clear, prefer the clear signal
        if message_type == MIXED and file_type != MIXED:
            return file_type
        if file_type == MIXED and message_type != MIXED:
            return message_type

        # If both are mixed or both are different clear types, return mixed
        return MIXED

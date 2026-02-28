"""Terminal identification for handoff session isolation.

Rationale: PID-based isolation prevents cross-terminal contamination.
Each terminal/process gets its own handoff file, matching redis-py approach
of using PID detection to prevent shared session issues.

Reference: https://xiaorui.cc/archives/6245 (Python requests multiprocess safety)
"""

import os


def detect_terminal_id() -> str:
    """
    Detect terminal identifier for session-scoped handoff storage.

    Returns:
        Terminal ID string (format: term_{PID})

    Rationale:
        - PID identifies unique process/terminal session
        - Prevents cross-terminal handoff contamination
        - Matches redis-py pattern for connection pool isolation
        - Each process gets its own session file (no sharing)

    Example:
        >>> os.getpid()
        12345
        >>> detect_terminal_id()
        'term_12345'
    """
    return f"term_{os.getpid()}"

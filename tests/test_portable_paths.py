"""
Test that verifies all paths are portable (no hardcoded P:/ prefixes).

This test ensures the handoff package is portable across different environments
by checking that no absolute Windows paths (P:/) are hardcoded in the source code.
Paths should be:
- Relative to the project root
- Computed dynamically from environment variables
- Derived from configuration files

Test Scope: All Python files in src/handoff/

Given: The handoff package should work in any environment
When: Scanning all Python source files
Then: No hardcoded P:/ paths should exist
"""

import re
from pathlib import Path

import pytest


def test_no_hardcoded_p_drive_paths():
    """
    Test that no hardcoded P:/ paths exist in the source code.

    This is a RED phase test - it currently FAILS because:
    - config.py line 22: PROJECT_ROOT defaults to "P:/"
    - cli.py line 613: task_tracker_dir uses hardcoded "P:/.claude/state/task_tracker"

    The test will pass after these are refactored to use dynamic path resolution.
    """
    # Arrange: Get the source directory
    project_root = Path(__file__).parent.parent
    src_dir = project_root / "src" / "handoff"

    # Find all Python files in src/handoff/
    python_files = list(src_dir.rglob("*.py"))

    # Pattern to match hardcoded P:/ paths (with variations)
    # Matches: "P:/...", 'P:/...', "P:\\...", 'P:\\...', r"P:/...", r"P:\\..."
    # The pattern matches opening quote, optional raw prefix, P:/ or P:\, then any path chars, then closing quote
    hardcoded_p_pattern = re.compile(
        r'["\']'        # Opening quote
        r'[rR]?'         # Optional raw string prefix
        r'P:[/\\]'       # P:/ or P:\
        r'[^"\']*'       # Any characters except quotes (the path content)
        r'["\']'         # Closing quote
    )

    violations = []

    # Act: Scan each file for hardcoded P:/ paths
    for py_file in python_files:
        try:
            content = py_file.read_text(encoding='utf-8')

            # Check each line
            for line_num, line in enumerate(content.split('\n'), start=1):
                # Skip comment lines that explain the default
                if 'defaults to P:/' in line or 'P:/ for CSF' in line:
                    continue

                matches = hardcoded_p_pattern.findall(line)
                if matches:
                    violations.append({
                        'file': py_file.relative_to(project_root),
                        'line': line_num,
                        'content': line.strip(),
                        'matches': matches
                    })
        except Exception as e:
            pytest.fail(f"Failed to read {py_file}: {e}")

    # Assert: No hardcoded P:/ paths should exist
    # Format violations for readable error message
    if violations:
        error_msg = "Found hardcoded P:/ paths in the following locations:\n\n"
        for v in violations:
            error_msg += f"  {v['file']}:{v['line']}\n"
            error_msg += f"    {v['content']}\n"
            error_msg += f"    Matches: {v['matches']}\n\n"

        # Show count of violations
        error_msg += f"\nTotal violations: {len(violations)}\n"
        error_msg += "\nExpected: All paths should be relative or computed dynamically.\n"
        error_msg += "Fix: Use environment variables, config files, or relative paths."

        pytest.fail(error_msg)


def test_portable_path_patterns():
    """
    Test that demonstrates the EXPECTED portable path patterns.

    This test shows what code SHOULD look like - all these examples
    use portable path construction methods.

    Given: Portable code uses dynamic path resolution
    When: Examining path construction patterns
    Then: All patterns should be environment-independent
    """
    # Examples of ACCEPTABLE patterns (these should work):

    # 1. Environment variable with fallback to relative path
    # os.getenv("HANDOFF_PROJECT_ROOT", str(Path.cwd() / ".claude"))

    # 2. Path relative to current working directory
    # Path(".claude") / "handoffs"

    # 3. Path relative to user home
    # Path.home() / ".claude" / "handoffs"

    # 4. Computed from config file
    # config = load_config()
    # Path(config.get("project_root", "."))

    # This test always passes - it's documentation of expected patterns
    assert True

#!/usr/bin/env python3
"""Fix long lines in handoff package by breaking them intelligently."""

import re
from pathlib import Path

MAX_LENGTH = 100

def should_break_line(line: str) -> bool:
    """Check if line should be broken (exclude certain patterns)."""
    # Don't break comments or docstrings
    stripped = line.strip()
    if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
        return False
    # Don't break if it's just a string
    if stripped.startswith('"') or stripped.startswith("'"):
        return False
    return True

def fix_long_line(line: str) -> str:
    """Break a long line intelligently."""
    stripped = line.rstrip()
    indent = len(line) - len(line.lstrip())
    base_indent = " " * indent

    # Default: break at first space after MAX_LENGTH
    if len(stripped) > MAX_LENGTH:
        break_point = MAX_LENGTH
        # Find nearest space or comma
        while break_point > 0 and stripped[break_point] not in " ,)]}=":
            break_point -= 1

        if break_point > 0 and break_point < len(stripped):
            return (
                stripped[:break_point] +
                "\n" +
                base_indent + "    " +
                stripped[break_point + 1:].lstrip()
            )

    return line

def fix_file(file_path: Path) -> int:
    """Fix long lines in a file, return number of fixes."""
    try:
        with open(file_path, encoding='utf-8') as f:
            lines = f.readlines()

        fixed_lines = []
        fixes = 0

        for line in lines:
            if len(line.rstrip()) > MAX_LENGTH and should_break_line(line):
                fixed = fix_long_line(line)
                if fixed != line:
                    fixes += 1
                    fixed_lines.append(fixed)
                else:
                    fixed_lines.append(line)
            else:
                fixed_lines.append(line)

        if fixes > 0:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(fixed_lines)

        return fixes
    except Exception as e:
        print(f"Error fixing {file_path}: {e}")
        return 0

def main():
    """Fix all long lines in handoff package."""
    handoff_dir = Path("src/handoff")
    total_fixes = 0

    for py_file in handoff_dir.rglob("*.py"):
        fixes = fix_file(py_file)
        if fixes > 0:
            print(f"Fixed {fixes} lines in {py_file}")
            total_fixes += fixes

    print(f"\nTotal fixes: {total_fixes}")

if __name__ == "__main__":
    main()

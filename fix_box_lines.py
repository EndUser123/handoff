#!/usr/bin/env python3
"""Fix long box-drawing comment lines."""

import re
from pathlib import Path

def fix_box_lines(file_path: Path) -> int:
    """Fix long box-drawing comment lines by truncating to 100 chars."""
    try:
        with open(file_path, encoding='utf-8') as f:
            lines = f.readlines()

        fixed_lines = []
        fixes = 0

        for line in lines:
            stripped = line.rstrip()
            # Check if it's a long box-drawing comment line
            if len(stripped) > 100 and stripped.strip().startswith('#') and '═' in stripped:
                # Truncate to 100 chars
                fixed_lines.append(stripped[:100] + '\n')
                fixes += 1
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
    """Fix all box-drawing lines in handoff package."""
    handoff_dir = Path("src/handoff")
    total_fixes = 0

    for py_file in handoff_dir.rglob("*.py"):
        fixes = fix_box_lines(py_file)
        if fixes > 0:
            print(f"Fixed {fixes} box lines in {py_file}")
            total_fixes += fixes

    print(f"\nTotal fixes: {total_fixes}")

if __name__ == "__main__":
    main()

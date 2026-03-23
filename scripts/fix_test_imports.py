#!/usr/bin/env python3
"""Fix broken test imports after core/ → scripts/ migration."""

import re
from pathlib import Path

# Fix pattern: replace core.hooks.__lib imports with __lib imports
OLD_PATTERN = r'from core\.hooks\.__lib\.'
NEW_IMPORT = 'from __lib.'

# Files to fix
test_files = [
    "tests/test_canonical_goal_extraction.py",
    "tests/test_context_gathering_boundaries.py",
    "tests/test_deterministic_checksums.py",
    "tests/test_handoff_integration.py",
    "tests/test_last_user_message.py",
    "tests/test_pending_operations_extraction.py",
    "tests/test_performance_canonical_goal.py",
    "tests/test_restoration_message.py",
    "tests/test_task_identity_manager_terminal_scope.py",
    "tests/test_terminal_isolation.py",
    "tests/test_tool_result_skipping.py",
    "tests/test_transcript_extract.py",
    "tests/test_variable_shadowing_fix.py",
    "tests/test_visual_context.py",
]

def fix_test_file(test_path: Path) -> bool:
    """Fix imports in a test file.

    Returns:
        True if file was modified, False otherwise
    """
    content = test_path.read_text()
    original_content = content

    # Replace old import pattern with new one
    content = re.sub(OLD_PATTERN, NEW_IMPORT, content)

    # Add hooks root setup if not present
    hooks_setup = """# Add hooks root to path (same as actual hooks)
HOOKS_ROOT = Path(__file__).resolve().parents[1] / "scripts" / "hooks"
if str(HOOKS_ROOT) not in sys.path:
    sys.path.insert(0, str(HOOKS_ROOT))

"""

    # Check if hooks setup already exists
    if "HOOKS_ROOT" not in content and "scripts/hooks" not in content:
        # Find where to insert (after existing sys.path setup)
        pattern = r'(sys\.path\.insert\(0, str\(HANDOFF_PACKAGE\)\)\n)'
        match = re.search(pattern, content)
        if match:
            insert_pos = match.end()
            content = content[:insert_pos] + hooks_setup + content[insert_pos:]

    # Write back if changed
    if content != original_content:
        test_path.write_text(content)
        return True
    return False

def main():
    """Fix all test files."""
    handoff_root = Path(__file__).resolve().parents[1]

    print("=== FIXING BROKEN TEST IMPORTS ===\n")

    fixed_count = 0
    for test_file in test_files:
        test_path = handoff_root / test_file
        if not test_path.exists():
            print(f"⚠️  SKIP: {test_file} (not found)")
            continue

        if fix_test_file(test_path):
            print(f"✅ FIXED: {test_file}")
            fixed_count += 1
        else:
            print(f"✓ OK: {test_file} (no changes needed)")

    print("\n=== SUMMARY ===")
    print(f"Fixed: {fixed_count}/{len(test_files)} files")

    if fixed_count > 0:
        print("\n✓ Test imports fixed. Run pytest to verify:")
        print("  pytest tests/ -v")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Test the new active work section logic."""

import sys
from pathlib import Path

# Add handoff package to path
HANDOFF_PACKAGE = Path("P:/packages/handoff/src")
if str(HANDOFF_PACKAGE) not in sys.path:
    sys.path.insert(0, str(HANDOFF_PACKAGE))

# Import the function
from handoff.hooks.SessionStart_handoff_restore import _build_active_work_section

# Test case 1: In-progress task (should show ACTIVE WORK - CONTINUE THIS)
print("=" * 80)
print("TEST 1: In-progress task")
print("=" * 80)
handoff_data_1 = {
    "todo_list": [
        {"content": "Fix handoff system bug", "status": "in_progress"},
        {"content": "Write tests", "status": "pending"},
    ],
    "recent_exchanges": [
        {"role": "assistant", "text": "I've identified the bug in line 44. Fixing now."}
    ],
    "recent_edits": []
}
result_1 = _build_active_work_section(handoff_data_1)
print("\n".join(result_1))
print()

# Test case 2: Pending tasks with recent work (should show ACTIVE WORK)
print("=" * 80)
print("TEST 2: Pending tasks with recent work")
print("=" * 80)
handoff_data_2 = {
    "todo_list": [
        {"content": "Verify the fix", "status": "pending"},
    ],
    "recent_exchanges": [
        {"role": "user", "text": "Does the fix work?"},
        {"role": "assistant", "text": "Testing now..."}
    ],
    "recent_edits": [
        {"file": "SessionStart_handoff_restore.py", "snippet": "PROJECT_ROOT = Path('P:/')", "tool": "Edit"}
    ]
}
result_2 = _build_active_work_section(handoff_data_2)
print("\n".join(result_2))
print()

# Test case 3: Only pending tasks (should show PENDING WORK)
print("=" * 80)
print("TEST 3: Only pending tasks")
print("=" * 80)
handoff_data_3 = {
    "todo_list": [
        {"content": "Next task", "status": "pending"},
    ],
    "recent_exchanges": [],
    "recent_edits": []
}
result_3 = _build_active_work_section(handoff_data_3)
print("\n".join(result_3))
print()

# Test case 4: No tasks or work (should show SESSION CONTEXT)
print("=" * 80)
print("TEST 4: No tasks or work")
print("=" * 80)
handoff_data_4 = {
    "todo_list": [],
    "recent_exchanges": [],
    "recent_edits": []
}
result_4 = _build_active_work_section(handoff_data_4)
print("\n".join(result_4))
print()

print("✅ All test cases completed successfully!")

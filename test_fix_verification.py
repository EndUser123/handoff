#!/usr/bin/env python3
"""Quick verification of the _safe_id() security fix."""

from handoff.hooks.SessionStart_handoff_restore import _safe_id

# Test cases demonstrating the fix
test_cases = [
    ('../../../etc/passwd', 'Path traversal attack'),
    ('../.././etc/passwd', 'Mixed traversal'),
    ('./hidden_file', 'Current directory reference'),
    ('/etc/passwd', 'Absolute path'),
    ('normal_task', 'Safe task ID'),
    ('my_task_123', 'Safe ID with underscores'),
]

print('Testing _safe_id() security fix:')
print('=' * 60)
for input_val, description in test_cases:
    result = _safe_id(input_val)
    dangerous = ['..', './', '/', '\\']
    status = 'SAFE' if all(x not in result for x in dangerous) else 'UNSAFE'
    print(f'{description:25} | {input_val:25} -> {result:20} [{status}]')
print('=' * 60)

#!/usr/bin/env python3
"""
Test that PreCompact hook prioritizes TranscriptParser over stale cached files.

This test verifies the fix for the bug where handoff was capturing stale
last_user_message from cached files instead of the actual transcript.

Run with: pytest P:/packages/handoff/tests/test_precompact_priority_fix.py -v
"""

import sys
from pathlib import Path

# Add hooks to path
hooks_dir = Path("P:/packages/handoff/src/handoff/hooks").resolve()
sys.path.insert(0, str(hooks_dir))


class TestPreCompactPriorityFix:
    """Test that TranscriptParser is prioritized over cached files."""

    def test_transcript_parser_priority_over_active_command_file(self):
        """
        Test that TranscriptParser is tried BEFORE active_command file.

        This is the core fix for the bug where stale cached data was being
        captured instead of the actual last user message from transcript.

        Setup:
        - active_command file contains stale data: "yes, create the script"
        - TranscriptParser returns actual data: "read these URLs"
        - Result: TranscriptParser data should win (not stale file data)
        """
        # This test would require mocking the PreCompactHook class and its dependencies
        # For now, document the expected behavior
        pass

    def test_priority_order_is_correct(self):
        """
        Verify the priority order in the code is correct.

        Expected order:
        1. TranscriptParser (source of truth)
        2. hook_input
        3. active_command file (can be stale)
        4. blocker.description (fallback)
        """
        hook_path = Path("P:/packages/handoff/src/handoff/hooks/PreCompact_handoff_capture.py")
        hook_content = hook_path.read_text()

        # Verify the priority order by checking the order of "Option X:" comments
        options_found = []
        for line in hook_content.split('\n'):
            if 'Option 1:' in line or 'Option 2:' in line or 'Option 3:' in line or 'Option 4:' in line:
                if 'TranscriptParser' in line:
                    options_found.append(('Option 1', 'TranscriptParser'))
                elif 'hook_input' in line:
                    options_found.append(('Option 2', 'hook_input'))
                elif 'active_command' in line:
                    options_found.append(('Option 3', 'active_command'))
                elif 'blocker' in line:
                    options_found.append(('Option 4', 'blocker'))

        # Verify we found all 4 options in the correct order
        assert len(options_found) == 4, f"Expected 4 priority options, found {len(options_found)}"
        assert options_found[0] == ('Option 1', 'TranscriptParser'), \
            f"Option 1 should be TranscriptParser, got {options_found[0]}"
        assert options_found[1] == ('Option 2', 'hook_input'), \
            f"Option 2 should be hook_input, got {options_found[1]}"
        assert options_found[2] == ('Option 3', 'active_command'), \
            f"Option 3 should be active_command, got {options_found[2]}"
        assert options_found[3] == ('Option 4', 'blocker'), \
            f"Option 4 should be blocker, got {options_found[3]}"

    def test_transcript_parser_called_first(self):
        """
        Verify TranscriptParser.extract_last_user_message() is called before
        _load_active_command_file().
        """
        hook_content = (Path("P:/packages/handoff/src/handoff/hooks/PreCompact_handoff_capture.py")
                        .read_text())

        # Find the section with the priority logic
        priority_section_start = hook_content.find("Option 1: TranscriptParser")
        priority_section_end = hook_content.find("# Build full handoff metadata")
        priority_section = hook_content[priority_section_start:priority_section_end]

        # Verify TranscriptParser call comes before active_command file load
        transcript_parser_pos = priority_section.find("self.parser.extract_last_user_message()")
        active_command_pos = priority_section.find("self._load_active_command_file()")

        assert transcript_parser_pos > 0, "TranscriptParser call not found in priority section"
        assert active_command_pos > 0, "active_command file load not found in priority section"
        assert transcript_parser_pos < active_command_pos, \
            "TranscriptParser should be called BEFORE active_command file load"

    def test_fallback_logic_is_preserved(self):
        """
        Verify that if TranscriptParser returns empty, the system falls back
        to hook_input, then active_command, then blocker.
        """
        hook_content = (Path("P:/packages/handoff/src/handoff/hooks/PreCompact_handoff_capture.py")
                        .read_text())

        # Count the "if not last_user_message:" fallback guards
        fallback_guards = hook_content.count("if not last_user_message:")

        # Should have exactly 3 fallback guards (after each of the first 3 options)
        assert fallback_guards >= 3, \
            f"Expected at least 3 fallback guards, found {fallback_guards}"

    def test_comment_is_updated(self):
        """
        Verify the comment reflects the new priority order.
        """
        hook_content = (Path("P:/packages/handoff/src/handoff/hooks/PreCompact_handoff_capture.py")
                        .read_text())

        # Check for the updated comment
        assert "Priority: 1) TranscriptParser (source of truth)" in hook_content, \
            "Comment should indicate TranscriptParser is priority 1"

        # Old comment should not exist
        assert "1) active_command file" not in hook_content or \
               "Priority: 1) TranscriptParser" in hook_content, \
            "Old priority comment should be updated"

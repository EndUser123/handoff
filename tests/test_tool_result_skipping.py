"""Tests for tool_result entry skipping in extract_last_substantive_user_message.

Tests that the extraction function correctly skips user entries that contain
only tool_result content, which are not actual user questions.

Relates to fix for handoff regression where tool_result entries were
incorrectly treated as user tasks.
"""

import json

from core.hooks.__lib.transcript import extract_last_substantive_user_message


class TestToolResultSkipping:
    """Test that tool_result entries are skipped during message extraction."""

    def test_skip_tool_result_only_entries(self, tmp_path):
        """Test that user entries with only tool_result content are skipped."""
        transcript_file = tmp_path / "test.jsonl"

        # Create a transcript where the last user message is a tool_result
        entries = [
            {"type": "user", "message": {"content": "My original task"}},
            {"type": "assistant", "message": {"content": "Let me help"}},
            {
                "type": "user",
                "message": {
                    "content": [{"type": "tool_result", "content": "Some file content"}]
                },
            },
        ]

        transcript_file.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        result_dict = extract_last_substantive_user_message(transcript_file)
        result = result_dict.get("goal", "Unknown task")

        # Should extract "My original task", not the tool_result content
        assert "My original task" in result
        assert "Some file content" not in result

    def test_extract_real_user_message_after_tool_result(self, tmp_path):
        """Test that real user messages after tool_result entries are extracted."""
        transcript_file = tmp_path / "test.jsonl"

        # Create a transcript with a tool_result followed by a real user message
        entries = [
            {"type": "assistant", "message": {"content": "Check this file"}},
            {
                "type": "user",
                "message": {
                    "content": [{"type": "tool_result", "content": "File content here"}]
                },
            },
            {"type": "user", "message": {"content": "Now do something else"}},
        ]

        transcript_file.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        result_dict = extract_last_substantive_user_message(transcript_file)
        result = result_dict.get("goal", "Unknown task")

        # Should extract "Now do something else"
        assert "Now do something else" in result
        assert "File content here" not in result

    def test_tool_result_with_teammate_messages(self, tmp_path):
        """Test handling of tool_result entries mixed with teammate messages."""
        transcript_file = tmp_path / "test.jsonl"

        # Create a transcript similar to the actual regression case
        entries = [
            {"type": "user", "message": {"content": "Can you audit all the features?"}},
            {
                "type": "user",
                "message": {
                    "content": [
                        {"type": "tool_result", "content": "Team status update"}
                    ]
                },
            },
            {
                "type": "user",
                "message": {
                    "content": '<teammate-message teammate_id="auditor">{"type":"idle"}</teammate-message>'
                },
            },
        ]

        transcript_file.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        result_dict = extract_last_substantive_user_message(transcript_file)
        result = result_dict.get("goal", "Unknown task")

        # Should extract the audit request, not tool_result or teammate messages
        assert "audit all the features" in result
        assert "Team status update" not in result
        assert "teammate-message" not in result

    def test_command_message_not_treated_as_tool_result(self, tmp_path):
        """Test that <command-message> entries are not treated as tool_result."""
        transcript_file = tmp_path / "test.jsonl"

        # Create a transcript with command messages (which start with <)
        entries = [
            {
                "type": "user",
                "message": {
                    "content": "<command-message>rca</command-message>\nInvestigate the bug"
                },
            },
            {"type": "user", "message": {"content": "Continue investigating"}},
        ]

        transcript_file.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        result_dict = extract_last_substantive_user_message(transcript_file)
        result = result_dict.get("goal", "Unknown task")

        # Should extract the second message (command-message is skipped by meta-instruction check)
        assert "Continue investigating" in result

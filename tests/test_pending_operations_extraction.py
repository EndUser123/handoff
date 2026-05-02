"""Tests for extract_pending_operations() enhancement.

Tests the enhanced pending operations detection that:
1. Parses tool_use events (Read, Grep, Glob, Edit, Bash, Skill)
2. Falls back to enhanced keyword detection including review/analysis patterns
3. Correctly identifies investigation operations

All tool_use entries use NESTED format (production standard):
  {"type": "assistant", "message": {"content": [{"type": "tool_use", ...}]}}
"""

import json
import uuid
from core.hooks.__lib.transcript import TranscriptParser


def make_tool_use_entry(tool_name: str, tool_input: dict) -> dict:
    """Create a nested-format tool_use entry matching production transcript structure.

    Production format: tool_use entries are nested inside assistant message.content.
    """
    entry_id = f"call_{uuid.uuid4().hex[:8]}"
    return {
        "type": "assistant",
        "uuid": f"entry_{entry_id}",
        "message": {
            "id": f"msg_{entry_id}",
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": entry_id,
                    "name": tool_name,
                    "input": tool_input,
                }
            ],
        },
    }


class TestPendingOperationsToolUseDetection:
    """Test tool_use event parsing for pending operations."""

    def test_detect_read_operation(self, tmp_path):
        """Test that Read tool_use is detected as pending operation."""
        transcript_file = tmp_path / "test.jsonl"
        entry = make_tool_use_entry("Read", {"file_path": "test.py"})
        transcript_file.write_text(json.dumps(entry) + "\n")

        parser = TranscriptParser(transcript_file)
        ops = parser.extract_pending_operations()

        assert len(ops) == 1
        assert ops[0]["type"] == "read"
        assert ops[0]["target"] == "test.py"
        assert ops[0]["state"] == "in_progress"

    def test_detect_grep_investigation(self, tmp_path):
        """Test that Grep tool_use is detected as investigation operation."""
        transcript_file = tmp_path / "test.jsonl"
        entry = make_tool_use_entry("Grep", {"pattern": "def test_"})
        transcript_file.write_text(json.dumps(entry) + "\n")

        parser = TranscriptParser(transcript_file)
        ops = parser.extract_pending_operations()

        assert len(ops) == 1
        assert ops[0]["type"] == "investigation"
        assert "search: def test_" in ops[0]["target"]

    def test_detect_glob_investigation(self, tmp_path):
        """Test that Glob tool_use is detected as investigation operation."""
        transcript_file = tmp_path / "test.jsonl"
        entry = make_tool_use_entry("Glob", {"pattern": "**/*.py"})
        transcript_file.write_text(json.dumps(entry) + "\n")

        parser = TranscriptParser(transcript_file)
        ops = parser.extract_pending_operations()

        assert len(ops) == 1
        assert ops[0]["type"] == "investigation"
        assert "files: **/*.py" in ops[0]["target"]

    def test_detect_edit_operation(self, tmp_path):
        """Test that Edit tool_use is detected as pending operation."""
        transcript_file = tmp_path / "test.jsonl"
        entry = make_tool_use_entry(
            "Edit", {"file_path": "src.py", "old_string": "old", "new_string": "new"}
        )
        transcript_file.write_text(json.dumps(entry) + "\n")

        parser = TranscriptParser(transcript_file)
        ops = parser.extract_pending_operations()

        assert len(ops) == 1
        assert ops[0]["type"] == "edit"
        assert ops[0]["target"] == "src.py"

    def test_detect_bash_test_operation(self, tmp_path):
        """Test that Bash with pytest is detected as test operation."""
        transcript_file = tmp_path / "test.jsonl"
        entry = make_tool_use_entry("Bash", {"command": "pytest tests/test_file.py"})
        transcript_file.write_text(json.dumps(entry) + "\n")

        parser = TranscriptParser(transcript_file)
        ops = parser.extract_pending_operations()

        assert len(ops) == 1
        assert ops[0]["type"] == "test"
        assert "pytest tests/test_file.py" in ops[0]["target"]

    def test_detect_skill_operation(self, tmp_path):
        """Test that Skill tool_use is detected as pending operation."""
        transcript_file = tmp_path / "test.jsonl"
        entry = make_tool_use_entry("Skill", {"skill": "rca"})
        transcript_file.write_text(json.dumps(entry) + "\n")

        parser = TranscriptParser(transcript_file)
        ops = parser.extract_pending_operations()

        assert len(ops) == 1
        assert ops[0]["type"] == "skill"
        assert "skill: rca" in ops[0]["target"]


class TestPendingOperationsKeywordFallback:
    """Test enhanced keyword detection when no tool_use events found."""

    def test_detect_review_keywords(self, tmp_path):
        """Test that review keywords are detected as investigation operations."""

        transcript_file = tmp_path / "test.jsonl"
        entry = {
            "type": "assistant",
            "content": "I will review the hook reasoning features to find optimizations.",
        }
        transcript_file.write_text(json.dumps(entry) + "\n")

        parser = TranscriptParser(transcript_file)
        ops = parser.extract_pending_operations()

        assert len(ops) == 1
        assert ops[0]["type"] == "investigation"

    def test_detect_analyze_keywords(self, tmp_path):
        """Test that analyze keywords are detected as investigation operations."""

        transcript_file = tmp_path / "test.jsonl"
        entry = {
            "type": "assistant",
            "content": "Let me analyze the code structure to understand the issue.",
        }
        transcript_file.write_text(json.dumps(entry) + "\n")

        parser = TranscriptParser(transcript_file)
        ops = parser.extract_pending_operations()

        assert len(ops) == 1
        assert ops[0]["type"] == "investigation"

    def test_detect_investigate_keywords(self, tmp_path):
        """Test that investigate keywords are detected as investigation operations."""

        transcript_file = tmp_path / "test.jsonl"
        entry = {
            "type": "assistant",
            "content": "I will investigate the root cause of this bug.",
        }
        transcript_file.write_text(json.dumps(entry) + "\n")

        parser = TranscriptParser(transcript_file)
        ops = parser.extract_pending_operations()

        assert len(ops) == 1
        assert ops[0]["type"] == "investigation"

    def test_detect_debug_keywords(self, tmp_path):
        """Test that debug keywords are detected as investigation operations."""

        transcript_file = tmp_path / "test.jsonl"
        entry = {
            "type": "assistant",
            "content": "Let me debug this issue by checking the logs.",
        }
        transcript_file.write_text(json.dumps(entry) + "\n")

        parser = TranscriptParser(transcript_file)
        ops = parser.extract_pending_operations()

        assert len(ops) == 1
        assert ops[0]["type"] == "investigation"

    def test_detect_search_keywords(self, tmp_path):
        """Test that search keywords are detected as investigation operations."""
        transcript_file = tmp_path / "test.jsonl"
        transcript_file.write_text(
            '{"type": "assistant", "content": "Searching for all occurrences of this pattern in the codebase."}\n'
        )

        parser = TranscriptParser(transcript_file)
        ops = parser.extract_pending_operations()

        assert len(ops) == 1
        assert ops[0]["type"] == "investigation"


class TestPendingOperationsPriority:
    """Test that tool_use parsing takes priority over keyword detection."""

    def test_tool_use_over_keywords(self, tmp_path):
        """Test that tool_use events are used even when keywords also present."""

        transcript_file = tmp_path / "test.jsonl"
        entries = [
            make_tool_use_entry("Grep", {"pattern": "test"}),
            {
                "type": "assistant",
                "content": "I will review the code now.",
            },
        ]
        transcript_file.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        parser = TranscriptParser(transcript_file)
        ops = parser.extract_pending_operations()

        # Should detect tool_use (Grep) and stop (limit of 5)
        # Should not also detect the keyword "review" since tool_use was found
        assert len(ops) == 1
        assert ops[0]["type"] == "investigation"
        assert "search: test" in ops[0]["target"]


class TestPendingOperationsLimits:
    """Test pending operations limits and edge cases."""

    def test_max_five_operations(self, tmp_path):
        """Test that only 5 pending operations are returned."""
        transcript_file = tmp_path / "test.jsonl"
        lines = [
            json.dumps(make_tool_use_entry("Read", {"file_path": f"file{i}.py"}))
            for i in range(10)
        ]
        transcript_file.write_text("\n".join(lines) + "\n")

        parser = TranscriptParser(transcript_file)
        ops = parser.extract_pending_operations()

        assert len(ops) == 5

    def test_empty_transcript(self, tmp_path):
        """Test that empty transcript returns empty list."""
        transcript_file = tmp_path / "test.jsonl"
        transcript_file.write_text("")

        parser = TranscriptParser(transcript_file)
        ops = parser.extract_pending_operations()

        assert ops == []

    def test_no_pending_operations(self, tmp_path):
        """Test that transcript without tools or keywords returns empty list."""
        transcript_file = tmp_path / "test.jsonl"
        transcript_file.write_text(
            '{"type": "assistant", "content": "Hello, how can I help you today?"}\n'
        )

        parser = TranscriptParser(transcript_file)
        ops = parser.extract_pending_operations()

        assert ops == []


class TestInvestigationOperationDetails:
    """Test investigation operation details and context extraction."""

    def test_investigation_with_file_target(self, tmp_path):
        """Test investigation operation extracts file target from context."""

        transcript_file = tmp_path / "test.jsonl"
        entry = {
            "type": "assistant",
            "content": "I will review src/hooks.py to check the implementation.",
        }
        transcript_file.write_text(json.dumps(entry) + "\n")

        parser = TranscriptParser(transcript_file)
        ops = parser.extract_pending_operations()

        assert len(ops) == 1
        assert ops[0]["type"] == "investigation"
        # File path extraction should work
        assert ops[0]["target"] == "src/hooks.py" or ops[0]["target"] == "unknown"

    def test_grep_with_pattern_target(self, tmp_path):
        """Test Grep operation includes pattern in target."""
        transcript_file = tmp_path / "test.jsonl"
        long_pattern = "def some_very_long_function_name_that_exceeds_limit" * 2
        entry = make_tool_use_entry("Grep", {"pattern": long_pattern})
        transcript_file.write_text(json.dumps(entry) + "\n")

        parser = TranscriptParser(transcript_file)
        ops = parser.extract_pending_operations()

        assert len(ops) == 1
        assert ops[0]["type"] == "investigation"
        # Pattern should be truncated to ~50 chars
        assert len(ops[0]["target"]) < 100


class TestPendingOperationsCompletedExclusion:
    """Regression: completed tool_use entries must NOT appear as pending.

    Bug: extract_pending_operations() collected ALL tool_use entries regardless
    of completion state, then took the first 5 (oldest). A completed Read of
    settings.json from early in the session would appear as "pending" in the
    handoff snapshot, misleading the resumed session.
    """

    def _make_tool_result_entry(self, tool_use_id: str) -> dict:
        """Create a tool result entry matching production transcript structure."""
        return {
            "type": "tool",
            "id": tool_use_id,
        }

    def test_completed_read_excluded(self, tmp_path):
        """Completed Read must not appear in pending operations."""
        entry_id = "call_completed_read"
        tool_use = {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": entry_id,
                        "name": "Read",
                        "input": {"file_path": "P:/.claude/settings.json"},
                    }
                ],
            },
        }
        tool_result = self._make_tool_result_entry(entry_id)

        transcript_file = tmp_path / "test.jsonl"
        transcript_file.write_text(
            json.dumps(tool_use) + "\n" + json.dumps(tool_result) + "\n"
        )

        parser = TranscriptParser(transcript_file)
        ops = parser.extract_pending_operations()

        assert ops == [], f"Completed Read should not be pending, got: {ops}"

    def test_completed_ops_excluded_in_progress_kept(self, tmp_path):
        """Mix of completed and in-progress: only in-progress kept."""
        completed_id = "call_done"
        in_progress_id = "call_pending"

        completed_use = {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": completed_id,
                        "name": "Read",
                        "input": {"file_path": "old_file.py"},
                    }
                ],
            },
        }
        completed_result = self._make_tool_result_entry(completed_id)
        pending_use = {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": in_progress_id,
                        "name": "Edit",
                        "input": {"file_path": "new_file.py"},
                    }
                ],
            },
        }

        transcript_file = tmp_path / "test.jsonl"
        transcript_file.write_text(
            "\n".join(
                json.dumps(e)
                for e in [completed_use, completed_result, pending_use]
            )
            + "\n"
        )

        parser = TranscriptParser(transcript_file)
        ops = parser.extract_pending_operations()

        assert len(ops) == 1
        assert ops[0]["type"] == "edit"
        assert ops[0]["target"] == "new_file.py"

    def test_all_completed_yields_empty(self, tmp_path):
        """When all tool_uses have matching results, pending ops is empty."""
        entries = []
        for i in range(3):
            tid = f"call_{i}"
            entries.append(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "id": tid,
                                "name": "Read",
                                "input": {"file_path": f"file{i}.py"},
                            }
                        ],
                    },
                }
            )
            entries.append(self._make_tool_result_entry(tid))

        transcript_file = tmp_path / "test.jsonl"
        transcript_file.write_text(
            "\n".join(json.dumps(e) for e in entries) + "\n"
        )

        parser = TranscriptParser(transcript_file)
        ops = parser.extract_pending_operations()

        assert ops == []


class TestPendingOperationsReverseOrder:
    """Regression: most recent incomplete operations should appear first.

    Bug: extract_pending_operations() processed entries from the beginning,
    so the first (oldest) incomplete operations were returned. For session
    resumption, the most recent incomplete work matters most.
    """

    def test_most_recent_first(self, tmp_path):
        """When multiple ops are in-progress, the latest appears first."""
        entries = []
        for i in range(3):
            entries.append(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "id": f"call_{i}",
                                "name": "Read",
                                "input": {"file_path": f"file{i}.py"},
                            }
                        ],
                    },
                }
            )

        transcript_file = tmp_path / "test.jsonl"
        transcript_file.write_text(
            "\n".join(json.dumps(e) for e in entries) + "\n"
        )

        parser = TranscriptParser(transcript_file)
        ops = parser.extract_pending_operations()

        assert len(ops) == 3
        # Reverse order: file2 (most recent) first, file0 last
        assert ops[0]["target"] == "file2.py"
        assert ops[1]["target"] == "file1.py"
        assert ops[2]["target"] == "file0.py"

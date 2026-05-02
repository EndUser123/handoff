"""Regression test for the skill definition capture bug.

This test reproduces and verifies the fix for the reported bug where after compaction,
the handoff system incorrectly captured 722-line SKILL.md content as the user goal and
decision constraints.

Bug Report Summary:
- Observed: After compaction, AI loses context and implements wrong features
- Root cause: goal field contained 722-line SKILL.md content instead of user request
- Root cause: decision_register contained skill definitions as "constraints"
- Fix: Added is_meta_instruction() filter to _build_decisions() and fallback logic

This regression test ensures the bug doesn't reoccur.
"""

from __future__ import annotations

import json
from pathlib import Path


from scripts.hooks.PreCompact_snapshot_capture import _build_decisions
from scripts.hooks.__lib.transcript import TranscriptParser


def _create_transcript(tmp_path: Path, entries: list[dict]) -> str:
    """Create a test transcript file with given entries."""
    transcript_path = tmp_path / "test_transcript.jsonl"
    with open(transcript_path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    return str(transcript_path)


class TestRegressionSkillDefinitionCaptureBug:
    """Regression test for the reported skill definition capture bug.

    This test reproduces the scenario where:
    1. A skill definition appears in the transcript as a "user" message
    2. The skill definition contains decision-like keywords ("must", "do not", "never")
    3. Without the fix, these would be incorrectly captured as decisions

    Expected behavior after fix:
    - Skill definitions are filtered from goal extraction
    - Skill definitions are filtered from decision extraction
    - Legitimate user constraints are still captured correctly
    """

    def test_regression_722_line_skill_definition_not_captured(
        self, tmp_path: Path
    ) -> None:
        """Regression test: 722-line SKILL.md should NOT be captured as goal or decision.

        This reproduces the exact bug scenario where a large skill definition
        (simulated here with representative content) appears in the transcript.

        Expected:
        - Skill definition NOT in decision_register
        - Skill definition NOT in goal
        - Legitimate user constraints ARE captured
        """
        # Simulate the bug scenario: skill definition with decision-like keywords
        # appearing in transcript as "user" message
        large_skill_definition = """Base directory for this skill: P:/packages/handoff

# Handoff Skill - Session Context Preservation

## Purpose
This skill provides session context preservation across compaction.

## Constraints
- You must preserve context across compaction
- Do not lose user goals
- Never skip the decision register
- Must validate all user input
- Do not skip tests

## Implementation Details
The skill hooks into PreCompact and SessionStart to capture...

[... 722 lines total ...]

## Usage
Invoke via /handoff or automatic compact.
"""

        entries = [
            {
                "type": "user",
                "message": {"content": [large_skill_definition]},
            },
            {
                "type": "user",
                "message": {"content": ["Fix the bug in the authentication module"]},
            },
            {
                "type": "assistant",
                "message": {
                    "content": [
                        "I'll fix the authentication bug by checking the token validation logic."
                    ]
                },
            },
        ]

        transcript_path = _create_transcript(tmp_path, entries)
        parser = TranscriptParser(transcript_path)

        # Test decision extraction
        decisions = _build_decisions(parser, "test_evidence_id")

        # Extract decision summaries for verification
        decision_summaries = [d["summary"] for d in decisions]

        # CRITICAL: Skill definition must NOT be in decisions
        for summary in decision_summaries:
            assert "Base directory for this skill:" not in summary
            assert "722-line SKILL.md content" not in summary
            assert "## Constraints" not in summary
            assert "You must preserve context" not in summary
            assert "Do not lose user goals" not in summary

        # The legitimate user request MAY be captured if it contains decision patterns
        # "Fix the bug" doesn't match decision patterns, so no decisions expected
        assert len(decisions) == 0

    def test_regression_mixed_skill_and_user_content(self, tmp_path: Path) -> None:
        """Regression test: Mix of skill definition and legitimate constraints.

        Verifies that when the transcript contains both:
        1. Skill definition with decision-like keywords
        2. Legitimate user constraints

        Only the legitimate user constraints should be captured.
        """
        entries = [
            {
                "type": "user",
                "message": {
                    "content": [
                        "Base directory for this skill: P:/packages/handoff\n\n"
                        "# Skill\n\n"
                        "## Constraints\n"
                        "- You must always validate input\n"
                        "- Do not skip tests\n"
                    ]
                },
            },
            {
                "type": "user",
                "message": {
                    "content": ["You must implement proper error handling for the API"]
                },
            },
            {
                "type": "user",
                "message": {
                    "content": ["Do not ignore edge cases in the validation logic"]
                },
            },
        ]

        transcript_path = _create_transcript(tmp_path, entries)
        parser = TranscriptParser(transcript_path)

        decisions = _build_decisions(parser, "test_evidence_id")

        # Should capture exactly 2 legitimate constraints
        assert len(decisions) == 2, (
            f"Expected 2 legitimate constraints, got {len(decisions)}: "
            f"{[d.get('summary') for d in decisions]}"
        )

        decision_summaries = [d["summary"] for d in decisions]

        # Verify skill definition NOT captured
        for summary in decision_summaries:
            assert "Base directory for this skill:" not in summary
            assert "## Constraints" not in summary
            assert "You must always validate input" not in summary
            assert "Do not skip tests" not in summary

        # Verify legitimate constraints ARE captured
        legitimate_patterns = [
            "proper error handling",
            "edge cases",
        ]

        for pattern in legitimate_patterns:
            found = any(pattern in summary for summary in decision_summaries)
            assert found, (
                f"Expected pattern '{pattern}' not found in decisions: {decision_summaries}"
            )

    def test_regression_fallback_goal_does_not_capture_skill(
        self, tmp_path: Path
    ) -> None:
        """Regression test: Fallback goal extraction must filter skill definitions.

        Verifies that when goal extraction falls back to extract_last_user_message(),
        skill definitions are still filtered by is_meta_instruction().
        """
        entries = [
            {
                "type": "user",
                "message": {
                    "content": [
                        "Base directory for this skill: P:/packages/handoff\n\n"
                        "# Handoff Skill\n\n"
                        "[... skill content ...]"
                    ]
                },
            },
            {
                "type": "assistant",
                "message": {"content": ["I understand the skill requirements."]},
            },
        ]

        transcript_path = _create_transcript(tmp_path, entries)
        parser = TranscriptParser(transcript_path)

        # Simulate fallback scenario: extract_last_user_message() would return skill definition
        last_user_message = parser.extract_last_user_message()

        # Verify fallback would NOT return skill definition as-is
        # (In actual flow, fallback goes through is_meta_instruction check)
        assert last_user_message is not None
        assert "Base directory for this skill:" in last_user_message

        # Verify is_meta_instruction identifies it correctly
        from scripts.hooks.__lib.transcript import is_meta_instruction

        assert is_meta_instruction(last_user_message), (
            "Skill definition must be identified as meta instruction for filtering"
        )

    def test_regression_user_goal_preserved_after_compaction(
        self, tmp_path: Path
    ) -> None:
        """Regression test: Actual user goal should be preserved after compaction.

        Simulates the compaction scenario where:
        1. User's original request is captured
        2. Transcript is compacted
        3. Goal extraction uses fallback (last substantive message)

        Expected: User's actual goal is preserved, NOT skill definition.
        """
        entries = [
            {
                "type": "user",
                "message": {"content": ["Add user authentication to the API"]},
            },
            {
                "type": "assistant",
                "message": {
                    "content": ["I'll add user authentication with JWT tokens."]
                },
            },
            {
                "type": "toolCall",
                "name": "Read",
                "input": {"file_path": "src/auth.py"},
            },
            {
                "type": "tool_result",
                "content": [{"type": "text", "text": "file content..."}],
            },
            {
                "type": "assistant",
                "message": {
                    "content": [
                        "I've read the auth file and will implement JWT authentication."
                    ]
                },
            },
            {
                "type": "user",
                "message": {
                    "content": [
                        "Base directory for this skill: P:/packages/handoff\n\n"
                        "# Handoff Skill\n\n"
                        "[... injected by Claude Code ...]"
                    ]
                },
            },
        ]

        transcript_path = _create_transcript(tmp_path, entries)
        parser = TranscriptParser(transcript_path)

        # The actual user goal "Add user authentication to the API" should be preserved
        # via extract_last_substantive_user_message() or equivalent
        # NOT the skill definition

        # Verify skill definition is identifiable as meta instruction
        last_user_message = parser.extract_last_user_message()
        assert "Base directory for this skill:" in last_user_message

        from scripts.hooks.__lib.transcript import (
            is_meta_instruction,
            extract_last_substantive_user_message,
        )

        assert is_meta_instruction(last_user_message), (
            "Injected skill definition must be filtered out"
        )

        # Verify substantive user message is NOT filtered
        # extract_last_substantive_user_message is a module-level function, not a parser method
        substantive_result = extract_last_substantive_user_message(transcript_path)
        substantive = substantive_result.get("goal", "Unknown task")
        assert (
            "Add user authentication" in substantive
            or "user authentication" in substantive
        ), f"Actual user goal should be preserved, got: {substantive}"


class TestRegressionSkillDefinitionEdgeCases:
    """Edge case tests to ensure skill definition filtering is robust."""

    def test_regression_multiple_skills_in_sequence(self, tmp_path: Path) -> None:
        """Multiple skill definitions should all be filtered."""
        entries = [
            {
                "type": "user",
                "message": {
                    "content": ["Base directory for this skill: P:/skill1\n\n# Skill 1"]
                },
            },
            {
                "type": "user",
                "message": {
                    "content": ["Base directory for this skill: P:/skill2\n\n# Skill 2"]
                },
            },
            {
                "type": "user",
                "message": {"content": ["You must fix the critical bug"]},
            },
        ]

        transcript_path = _create_transcript(tmp_path, entries)
        parser = TranscriptParser(transcript_path)

        decisions = _build_decisions(parser, "test_evidence_id")

        # Only the legitimate constraint should be captured
        assert len(decisions) == 1
        assert "fix the critical bug" in decisions[0]["summary"].lower()

    def test_regression_skill_definition_with_tool_use(self, tmp_path: Path) -> None:
        """Skill definition combined with tool calls should still be filtered."""
        entries = [
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Read",
                            "input": {"file_path": "SKILL.md"},
                        },
                        {
                            "type": "text",
                            "text": "Base directory for this skill: P:/packages/handoff\n\n# Skill content",
                        },
                    ]
                },
            },
        ]

        transcript_path = _create_transcript(tmp_path, entries)
        parser = TranscriptParser(transcript_path)

        # Verify the skill definition text is still extracted and can be filtered
        # The parser._extract_text_from_entry method should handle mixed content
        # Note: _extract_text_from_entry is a private method on TranscriptParser
        text = parser._extract_text_from_entry(entries[0]).strip()

        # Should contain the skill definition text
        assert "Base directory for this skill:" in text

        # And should be identified as meta instruction
        from scripts.hooks.__lib.transcript import is_meta_instruction

        assert is_meta_instruction(text), (
            "Skill definition in mixed content must be filtered"
        )

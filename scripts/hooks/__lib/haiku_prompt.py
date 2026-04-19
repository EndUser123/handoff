#!/usr/bin/env python3
"""Haiku prompt builder for handoff conversation summary."""

from __future__ import annotations

from pathlib import Path

# Threshold constants
MIN_MESSAGE_COUNT = 10
MIN_BYTE_COUNT = 5000

PROMPT_TEMPLATE = """You are summarizing a Claude Code session for a daily memory log.

Read the conversation extract below and write ONE memory entry in this exact format:

## {{TIME}} | {{BRANCH}}
[One sentence: what was done. Be specific — mention files, MR numbers, issue numbers.]

Rules:
- ONE sentence only. Short and specific.
- Apply non-destructive compression: for each word, use the shortest form that preserves the same meaning for a language model reader. Keep all facts, all refs, all specifics — just fewer tokens. Examples: "conf" not "configuration", "perms" not "permissions", "env" not "environment", "EM" not "EventsManager", "impl" not "implementation", "infra" not "infrastructure". Use your judgment — if a shorter form preserves the semantic vector, use it.
- Drop filler: "in order to", "that handle", "for proper", "successfully"
- No fluff, no preamble — just the entry block
- Do NOT include markdown fences or any other formatting
- If the conversation covers the SAME work as the previous entry with no meaningful new progress, return exactly the word SKIP — nothing else

Previous entry for context (do not repeat it):
---
{{LAST_ENTRY}}
---

Conversation to summarize:
---
{{EXTRACT}}
---

Write the entry now:"""


def should_skip_haiku(message_count: int, byte_count: int) -> tuple[bool, int, int]:
    """Check if Haiku summarization should be skipped based on thresholds.

    Returns:
        (should_skip, message_count, byte_count) — skip if True
    """
    skip = message_count < MIN_MESSAGE_COUNT or byte_count < MIN_BYTE_COUNT
    return (skip, message_count, byte_count)


def build_haiku_prompt(transcript_path: Path, last_entry: str | None = None) -> str:
    """Build the Haiku summarization prompt from a transcript file.

    Args:
        transcript_path: Path to the conversation transcript JSONL
        last_entry: Optional previous summary entry to avoid repetition

    Returns:
        Formatted prompt string with TIME, BRANCH, LAST_ENTRY, EXTRACT substituted
    """
    from datetime import datetime, timezone

    # Read transcript
    transcript_text = ""
    if transcript_path.exists():
        try:
            content = transcript_path.read_text(encoding="utf-8")
            # Extract conversation text from JSONL entries
            import json

            lines = content.strip().split("\n")
            for line in lines:
                if line:
                    try:
                        entry = json.loads(line)
                        if isinstance(entry, dict):
                            # Get role + content for each message
                            role = entry.get("role", "unknown")
                            content = entry.get("content", "")
                            if content:
                                transcript_text += f"[{role}] {content}\n"
                    except json.JSONDecodeError:
                        continue
        except Exception:
            transcript_text = ""

    # Format placeholders
    now = datetime.now(timezone.utc)
    time_str = now.strftime("%Y-%m-%d %H:%M")
    branch_name = "handoff-v2"

    last_entry_block = last_entry if last_entry else "(none)"

    prompt = PROMPT_TEMPLATE
    prompt = prompt.replace("{{TIME}}", time_str)
    prompt = prompt.replace("{{BRANCH}}", branch_name)
    prompt = prompt.replace("{{LAST_ENTRY}}", last_entry_block)
    prompt = prompt.replace("{{EXTRACT}}", transcript_text or "(no transcript content)")

    return prompt
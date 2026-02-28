#!/usr/bin/env python3
"""Transcript parsing utilities for handoff capture.

This module provides classes for parsing Claude Code transcript JSON files
to extract session data including decisions, patterns, modifications, and blockers.

Classes:
    TranscriptLines: Streaming transcript lines with lazy loading and list-like interface
    TranscriptParser: Parse transcript JSON for session data extraction
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Module-level helper functions (extracted from HandoverBuilder static methods)
def extract_topic_from_content(content: str, task_name: str = "") -> str:
    """Extract topic from content using keyword analysis.

    Args:
        content: Text content to analyze
        task_name: Optional task name for context

    Returns:
        Extracted topic (max 80 chars)
    """
    # Technical keywords that often indicate topic
    tech_keywords = [
        "authentication",
        "authorization",
        "jwt",
        "oauth",
        "api",
        "database",
        "handoff",
        "compact",
        "hook",
        "semantic",
        "search",
        "decision",
        "pattern",
        "bridge token",
        "context",
        "session",
        "terminal",
        "sqlite",
        "postgres",
        "schema",
        "migration",
        "deployment",
        "testing",
        "tdd",
        "test",
        "validation",
        "verification",
    ]

    content_lower = content.lower()

    # Find most relevant keyword
    for keyword in tech_keywords:
        if keyword in content_lower:
            return keyword

    # Fall back to first few words
    words = content.split()[:5]
    return " ".join(words)[:80]


def detect_structure_type(content: str) -> dict[str, Any] | None:
    """Detect structured content format (tables, comparisons, assessments).

    Args:
        content: Text content to analyze

    Returns:
        Dict with "type" and optional "search_keys", or None if unstructured
    """
    content_lower = content.lower()

    # Table indicators (box drawing, markdown tables, ASCII tables)
    table_indicators = [
        "\u250c",  # ┌ top-left corner
        "\u252c",  # ┬ tee-down
        "\u251c",  # ├ tee-right
        "\u2502",  # │ vertical line
        "\u2514",  # └ bottom-left corner
        "\u2534",  # ┴ tee-up
        "\u253c",  # ┼ cross
        "\u2500",  # ─ horizontal line
        "\u2550",  # ╔ double top-left corner
        "\u2551",  # ║ double vertical line
        "\u2554",  # ╔ double top-left corner (alt)
        "\u2566",  # ╦ double tee-down
        "\u2563",  # ╣ double tee-left
        "\u2560",  # ╠ double tee-right
        "\u255a",  # ╚ double bottom-left corner
        "\u2569",  # ╩ double tee-up
        "\u256c",  # ╬ double cross
        "\u2550",  # ═ double horizontal line
        "|=",
        "|-",
        "enhancement",
        "assessment",
    ]
    has_table_structure = any(indicator in content for indicator in table_indicators)

    # Value assessment indicators (priority matrices, rankings)
    assessment_indicators = [
        "high",
        "medium",
        "low",
        "priority",
        "value",
        "rationale",
        "assessment",
    ]
    has_assessment = sum(1 for ind in assessment_indicators if ind in content_lower) >= 3

    # Comparison indicators (options vs each other)
    comparison_indicators = [
        "pros",
        "cons",
        "trade-off",
        "versus",
        "vs.",
        "option a",
        "option b",
    ]
    has_comparison = any(ind in content_lower for ind in comparison_indicators)

    # Extract search keys from content (nouns/technical terms)
    search_keys = []
    if has_table_structure or has_assessment or has_comparison:
        # Extract key terms for searching (skip common words)
        key_terms = [w for w in content_lower.split() if len(w) > 4 and w.isalpha()]
        # Filter to unique, meaningful terms
        seen = set()
        for term in key_terms:
            if term not in seen and term not in {"this", "that", "with", "from", "been"}:
                search_keys.append(term)
                seen.add(term)
                if len(search_keys) >= 5:
                    break

    # Determine structure type
    if has_table_structure:
        return {"type": "analysis_table", "search_keys": search_keys}
    elif has_assessment:
        return {"type": "priority_matrix", "search_keys": search_keys}
    elif has_comparison:
        return {"type": "comparison", "search_keys": search_keys}

    return None


class TranscriptLines(Sequence[str]):
    """Streaming transcript lines with lazy loading and list-like interface.

    Provides O(1) memory access for recent lines by only caching what's needed.
    Supports negative indexing, slicing, and random access patterns.

    Memory usage is constant relative to file size - only stores the most
    recently accessed lines in cache.
    """

    def __init__(self, path: str | None) -> None:
        """Initialize streaming transcript lines.

        Args:
            path: Path to transcript file (None returns empty sequence)
        """
        self._path = path
        self._cache: list[str] = []
        self._length: int | None = None

    def _ensure_length(self) -> int:
        """Get total line count without loading all lines into memory.

        Returns:
            Total number of lines in the transcript file.
        """
        if self._length is not None:
            return self._length

        if not self._path or not Path(self._path).exists():
            self._length = 0
            return 0

        try:
            # Count lines without storing them
            with open(self._path, encoding="utf-8") as f:
                self._length = sum(1 for _ in f)
            return self._length
        except (OSError, UnicodeDecodeError) as e:
            logger.debug(f"[TranscriptLines] Could not read transcript for length calculation: {e}")
            self._length = 0
            return 0

    def __len__(self) -> int:
        """Return total number of lines.

        Returns:
            Total line count.
        """
        return self._ensure_length()

    def __getitem__(self, key: int | slice) -> str | list[str]:
        """Get line(s) by index/slice with lazy loading.

        Args:
            key: Integer index or slice object

        Returns:
            Single line (str) or list of lines (list[str])
        """
        length = self._ensure_length()

        if isinstance(key, slice):
            # Handle slicing
            start, stop, step = key.indices(length)
            if step != 1:
                # For non-trivial steps, load the range
                return self._load_range(start, stop)[::step]
            return self._load_range(start, stop)

        # Handle integer indexing
        if key < 0:
            key = length + key

        if key < 0 or key >= length:
            raise IndexError("TranscriptLines index out of range")

        # Check cache first
        if self._cache and key == len(self._cache) - 1:
            return self._cache[-1]

        # Load from file
        return self._load_line(key)

    def _load_line(self, index: int) -> str:
        """Load a single line from file without loading entire file.

        Args:
            index: Zero-based line index to load

        Returns:
            The line at that index

        Raises:
            IndexError: If line cannot be read
        """
        if not self._path or not Path(self._path).exists():
            raise IndexError("Transcript file not available")

        try:
            with open(self._path, encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i == index:
                        # Cache this line for potential subsequent access
                        if len(self._cache) < 100:
                            self._cache.append(line)
                        return line
        except (OSError, UnicodeDecodeError) as e:
            logger.warning(f"[TranscriptLines] Could not read line {index}: {e}")

        raise IndexError(f"Could not read line {index}")

    def _load_range(self, start: int, stop: int) -> list[str]:
        """Load a range of lines from file.

        Args:
            start: Start index (inclusive)
            stop: Stop index (exclusive)

        Returns:
            List of lines in range
        """
        if not self._path or not Path(self._path).exists():
            return []

        if start >= stop:
            return []

        length = self._ensure_length()
        start = max(0, min(start, length))
        stop = max(0, min(stop, length))

        result = []
        try:
            with open(self._path, encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i >= stop:
                        break
                    if i >= start:
                        result.append(line)
        except (OSError, UnicodeDecodeError) as e:
            logger.warning(f"[TranscriptLines] Could not read range {start}:{stop}: {e}")
            return []

        # Cache recent lines if this is a tail access
        if start >= length - 100:
            self._cache = result[-min(len(result), 100):]

        return result

    def __iter__(self) -> Iterator[str]:
        """Iterate over all lines using streaming.

        Yields:
            Transcript lines one at a time.
        """
        if not self._path or not Path(self._path).exists():
            return

        try:
            with open(self._path, encoding="utf-8") as f:
                for line in f:
                    yield line
        except (OSError, UnicodeDecodeError) as e:
            logger.warning(f"[TranscriptLines] Could not iterate: {e}")


class TranscriptParser:
    """Parse transcript JSON for session data extraction.

    Handles all transcript parsing operations including:
    - Extracting current blocker from user messages
    - Extracting modifications from Edit tool operations
    - Extracting conversation context
    - Extracting session decisions and patterns
    - Extracting controversial decisions

    Attributes:
        transcript_path: Path to the transcript JSON file
        _transcript_cache: Cached transcript lines (lazy loaded)
        _parsed_entries_cache: Cached parsed JSON entries (lazy loaded)
    """

    # Minimum content length for meaningful message extraction
    _MIN_CONTENT_LENGTH = 15
    # Maximum number of modifications to extract (FIFO - keeps most recent)
    _MAX_MODIFICATIONS = 50
    # Maximum file size in bytes (10MB) - prevents OOM from large files (QUAL-006)
    _MAX_FILE_SIZE = 10 * 1024 * 1024
    # Maximum number of entries to parse - prevents hang from excessive entries (QUAL-006)
    _MAX_ENTRIES = 50000

    def __init__(self, transcript_path: str | None = None) -> None:
        """Initialize transcript parser.

        Args:
            transcript_path: Path to the transcript JSON file
        """
        self.transcript_path = transcript_path
        self._transcript_cache: Sequence[str] | None = None
        self._parsed_entries_cache: list[dict[str, Any]] | None = None

    def _get_transcript_lines(self) -> Sequence[str]:
        """Get transcript lines from cache (read once, use many times).

        Returns:
            Sequence of transcript lines (empty sequence if transcript unavailable).
            Uses TranscriptLines for streaming with O(1) memory for cached access.
        """
        if self._transcript_cache is not None:
            return self._transcript_cache

        if not self.transcript_path or not Path(self.transcript_path).exists():
            self._transcript_cache = []
            return self._transcript_cache

        # Use TranscriptLines for streaming instead of loading entire file
        self._transcript_cache = TranscriptLines(self.transcript_path)
        return self._transcript_cache

    def _iter_transcript_lines(self) -> Iterator[str]:
        """Iterate over transcript lines using streaming (O(1) memory).

        Yields:
            Transcript lines one at a time without loading entire file.

        Returns:
            Iterator over transcript lines.
        """
        if not self.transcript_path or not Path(self.transcript_path).exists():
            return iter([])

        try:
            with open(self.transcript_path, encoding="utf-8") as f:
                for line in f:
                    yield line
        except (OSError, UnicodeDecodeError) as e:
            logger.warning(f"[TranscriptParser] Could not iterate transcript: {e}")
            return iter([])

    def _get_parsed_entries(self) -> list[dict[str, Any]]:
        """Get parsed transcript entries (parse once, use many times).

        This method caches parsed JSON entries to avoid repeated JSON parsing
        when multiple extraction methods are called during handoff capture.
        This fixes PERF-003: Multiple full transcript reads.

        Includes size and entry count limits to prevent OOM and hangs (QUAL-006).

        Returns:
            List of parsed JSON dicts from transcript (empty list if unavailable).
            Caches parsed entries to avoid repeated JSON parsing.
        """
        if self._parsed_entries_cache is not None:
            return self._parsed_entries_cache

        if not self.transcript_path or not Path(self.transcript_path).exists():
            self._parsed_entries_cache = []
            return self._parsed_entries_cache

        # QUAL-006: Check file size before parsing to prevent OOM
        transcript_file = Path(self.transcript_path)
        try:
            file_size = transcript_file.stat().st_size
            if file_size > self._MAX_FILE_SIZE:
                print(
                    f"[TranscriptParser] Warning: Transcript file size ({file_size / 1024 / 1024:.1f}MB) "
                    f"exceeds limit ({self._MAX_FILE_SIZE / 1024 / 1024:.1f}MB). "
                    f"Skipping parsing to prevent OOM (QUAL-006)."
                )
                self._parsed_entries_cache = []
                return self._parsed_entries_cache
        except OSError as e:
            logger.warning(f"[TranscriptParser] Could not check file size: {e}")
            self._parsed_entries_cache = []
            return self._parsed_entries_cache

        # Parse transcript once into memory with entry count limit (QUAL-006)
        entries = []
        entry_count = 0
        for line in self._iter_transcript_lines():
            # QUAL-006: Stop parsing if we exceed max entries
            if entry_count >= self._MAX_ENTRIES:
                print(
                    f"[TranscriptParser] Warning: Reached maximum entry count ({self._MAX_ENTRIES}). "
                    f"Stopping parsing early to prevent hang (QUAL-006)."
                )
                break

            try:
                entry = json.loads(line)
                entries.append(entry)
                entry_count += 1
            except json.JSONDecodeError:
                continue

        self._parsed_entries_cache = entries
        return self._parsed_entries_cache

    def _extract_text_from_entry(self, entry: dict[str, Any]) -> str:
        """Extract and concatenate text content from a transcript entry.

        This is a helper method that reduces code duplication across multiple
        extraction methods. It handles both list and string content formats.

        Args:
            entry: A transcript entry dict with optional "message" field

        Returns:
            Concatenated text content from the entry, or empty string if none found
        """
        msg_obj = entry.get("message", {})
        if not isinstance(msg_obj, dict):
            return ""

        content = msg_obj.get("content", "")
        content_text = ""

        if isinstance(content, list):
            # Handle list content (most common case)
            for item in content:
                if isinstance(item, str) and not item.startswith("<"):
                    content_text += item + " "
        elif isinstance(content, str):
            # Handle string content (less common)
            content_text = content

        return content_text.strip()

    def _filter_entries_by_type(
        self, entries: list[dict[str, Any]], entry_type: str
    ) -> list[dict[str, Any]]:
        """Filter transcript entries by type.

        Args:
            entries: List of transcript entries
            entry_type: Type to filter by (e.g., "user", "assistant", "tool_use")

        Returns:
            Filtered list of entries matching the specified type
        """
        return [e for e in entries if e.get("type") == entry_type]

    def extract_current_blocker(self) -> dict[str, Any] | None:
        """Extract current blocker from transcript's last user message.

        Returns:
            Dict with description, severity, and source, or None if no blocker found.
        """
        entries = self._get_parsed_entries()
        if not entries:
            return None

        try:
            # Read backwards to find the last user message
            # Transcript structure: {"type": "user", "message": {"content": [text_items]}}
            for i in range(len(entries) - 1, -1, -1):
                entry = entries[i]
                # Check for user-type entry (Claude Code uses "type", not "role")
                if entry.get("type") == "user":
                    # Extract content from message object
                    msg_obj = entry.get("message", {})
                    if not isinstance(msg_obj, dict):
                        continue

                    content = msg_obj.get("content", "")

                    # Handle list content (most common case)
                    if isinstance(content, list):
                        # Find actual text content, skip tool results and meta tags
                        for item in content:
                            # Skip dict items (tool_result, thinking, etc.) - only extract user text
                            if isinstance(item, dict):
                                continue
                            if isinstance(item, str):
                                item = item.strip()
                                # Skip meta tags and system messages
                                if (
                                    item.startswith("<")
                                    or item.startswith("This session is being continued")
                                    or item.startswith("Stop hook feedback")
                                    or len(item) < self._MIN_CONTENT_LENGTH
                                ):
                                    continue
                                # Found substantial user message
                                return {
                                    "description": f"User's last question: {item[:200]}{'...' if len(item) > 200 else ''}",
                                    "severity": "info",
                                    "source": "transcript",
                                }
                    # Handle string content (less common)
                    elif isinstance(content, str) and len(content.strip()) > self._MIN_CONTENT_LENGTH:
                        user_message = content.strip()
                        if not user_message.startswith("<"):
                            return {
                                "description": f"User's last question: {user_message[:200]}{'...' if len(user_message) > 200 else ''}",
                                "severity": "info",
                                "source": "transcript",
                            }
        except Exception as e:
            print(f"[TranscriptParser] Warning: Could not read transcript: {e}")

        return None

    def extract_modifications(self, limit: int = _MAX_MODIFICATIONS) -> list[dict[str, Any]]:
        """Extract file modifications (Edit operations) from transcript.

        Parses transcript for Edit tool_use entries and extracts:
        - file: Path to the modified file
        - line: Line number of the edit
        - before: Original content (old_string)
        - after: New content (new_string)
        - reason: Reason for the edit (from context)

        Args:
            limit: Maximum number of recent modifications to return (default: 50).
                   Uses FIFO (first-in-first-out) - keeps the most recent N edits.

        Returns:
            List of modification dicts with file, line, before, after, reason (max N items)
        """
        modifications: list[dict[str, Any]] = []

        entries = self._get_parsed_entries()
        if not entries:
            return modifications

        try:
            # Scan transcript for Edit tool_use entries
            for entry in entries:
                if entry.get("type") == "tool_use" and entry.get("name") == "Edit":
                    input_data = entry.get("input", {})
                    if not input_data:
                        continue

                    file_path = input_data.get("file_path")
                    old_string = input_data.get("old_string")
                    new_string = input_data.get("new_string")
                    line_num = input_data.get("line")

                    # Only add if we have the minimum required fields
                    if file_path and old_string is not None and new_string is not None:
                        modifications.append(
                            {
                                "file": file_path,
                                "line": line_num,
                                "before": old_string,
                                "after": new_string,
                                "reason": "Edit operation",
                            }
                        )

        except Exception as e:
            print(f"[TranscriptParser] Warning: Could not extract modifications: {e}")

        # Apply FIFO limit - keep only the most recent N modifications
        if len(modifications) > limit:
            modifications = modifications[-limit:]

        return modifications

    def extract_open_conversation_context(self) -> dict[str, Any] | None:
        """Extract open conversation context from recent user messages.

        Captures:
        - Questions that were asked but not fully answered
        - Active discussion threads
        - User's expressed intent for next steps

        Returns:
            Dict with description and context type, or None
        """
        entries = self._get_parsed_entries()
        if not entries:
            return None

        try:
            # Read last 20 user messages to find open discussion threads
            recent_user_messages: list[str] = []
            for i in range(len(entries) - 1, max(-1, len(entries) - 50), -1):
                entry = entries[i]
                if entry.get("type") == "user":
                    content_text = self._extract_text_from_entry(entry)
                    if len(content_text) > self._MIN_CONTENT_LENGTH:
                        recent_user_messages.insert(0, content_text)

                    if len(recent_user_messages) >= 5:
                        break

            # Check for open discussion indicators
            open_context_patterns = [
                r"related questions",
                r"follow up",
                r"more about",
                r"what about",
                r"also",
                r"and then",
                r"next",
            ]

            for msg in recent_user_messages[-3:]:  # Check last 3 messages
                msg_lower = msg.lower()
                for pattern in open_context_patterns:
                    if re.search(pattern, msg_lower):
                        return {
                            "description": f"Open discussion: {msg[:200]}{'...' if len(msg) > 200 else ''}",
                            "context_type": "open_discussion",
                            "original_message": msg[:500],
                        }

            # If no explicit patterns, check if last message was a question
            if recent_user_messages:
                last_msg = recent_user_messages[-1]
                if "?" in last_msg or any(
                    q in last_msg.lower() for q in ["why", "how", "what", "when", "where", "which"]
                ):
                    return {
                        "description": f"User's last question: {last_msg[:200]}{'...' if len(last_msg) > 200 else ''}",
                        "context_type": "question",
                        "original_message": last_msg[:500],
                    }

            return None

        except Exception as e:
            print(f"[TranscriptParser] Warning: Could not extract conversation context: {e}")
            return None

    def extract_session_decisions(self, task_name: str = "session") -> list[dict[str, Any]]:
        """Extract decisions made during THIS SESSION from transcript.

        Parses transcript for decision patterns like:
        - "Decision: use X instead of Y"
        - "Going with X approach"
        - "Chose X because..."
        - "Recommend: X"

        Args:
            task_name: Optional task name for context

        Returns:
            List of session decision dicts with topic, decision, rationale
        """
        decisions: list[dict[str, Any]] = []

        entries = self._get_parsed_entries()
        if not entries:
            return decisions

        try:
            # Decision patterns to look for
            decision_patterns = [
                r"(?:decision:|decided to|going with|chose|recommend|use\s+\w+\s+instead)",
                r"(?:i'll|i will|we'll|we will)\s+(?:use|go with|implement)",
                r"(?:let's|lets)\s+(?:use|go with|try)",
                r"(?:approach|plan|strategy):\s+(?:\w+.{0,100}?)(?:\.|\n|$)",
            ]

            combined_pattern = "|".join(f"(?:{p})" for p in decision_patterns)

            # Scan transcript for decision indicators
            for entry in self._filter_entries_by_type(entries, "user"):
                content_text = self._extract_text_from_entry(entry)
                if len(content_text) < 20:
                    continue

                # Check for decision patterns
                if re.search(combined_pattern, content_text, re.IGNORECASE):
                    # Extract decision context
                    decision_text = content_text[:300]

                    # Try to extract topic (what is this about?)
                    topic = extract_topic_from_content(decision_text, task_name)

                    # Detect structured content (tables, comparisons, assessments)
                    structure_info = detect_structure_type(content_text)

                    from handoff.config import utcnow_iso
                    decision_entry = {
                        "timestamp": entry.get("timestamp", utcnow_iso()),
                        "topic": topic,
                        "decision": decision_text[:200],
                        "direct_quote": content_text[:1000],
                        "source": "session_transcript",
                    }

                    # Add minimal structure metadata if detected
                    if structure_info:
                        decision_entry["format"] = structure_info["type"]
                        if structure_info.get("search_keys"):
                            decision_entry["search_keys"] = structure_info["search_keys"][:5]

                    decisions.append(decision_entry)

                    if len(decisions) >= 7:  # Cap at 7 session decisions
                        break

        except Exception as e:
            print(f"[TranscriptParser] Warning: Could not extract session decisions: {e}")

        return decisions

    def extract_session_patterns(self) -> list[str]:
        """Extract patterns discovered during THIS SESSION from transcript.

        Looks for pattern discoveries like:
        - "Pattern: X works better than Y"
        - "I notice that..."
        - "The pattern here is..."
        - "This suggests that..."

        Returns:
            List of pattern descriptions
        """
        patterns: list[str] = []

        entries = self._get_parsed_entries()
        if not entries:
            return patterns

        try:
            # Pattern discovery indicators
            pattern_indicators = [
                "pattern:",
                "i notice",
                "the pattern",
                "this suggests",
                "trend:",
                "observation:",
                "insight:",
            ]

            # Scan last 50 entries for patterns
            for entry in entries[-50:]:
                if entry.get("type") != "assistant":
                    continue

                content_text = self._extract_text_from_entry(entry)
                content_lower = content_text.lower()

                # Check for pattern indicators
                for indicator in pattern_indicators:
                    if indicator in content_lower:
                        # Extract the pattern description
                        pattern_start = content_lower.find(indicator)
                        if pattern_start >= 0:
                            pattern_desc = content_lower[pattern_start : pattern_start + 200]
                            patterns.append(pattern_desc.strip())
                            break

                if len(patterns) >= 5:  # Cap at 5 session patterns
                    break

        except Exception as e:
            print(f"[TranscriptParser] Warning: Could not extract session patterns: {e}")

        return patterns

    def extract_controversial_decisions(self) -> list[dict[str, Any]]:
        """Extract controversial decisions from transcript (verbatim quotes).

        Detects backtracking, reconsideration, and debate:
        - "actually", "wait", "hold on" - backtracking indicators
        - "never mind", "ignore that" - discarded suggestions
        - "scratch that", "revert" - changes of mind
        - "on second thought" - reconsideration

        Returns:
            List of controversial decision dicts with verbatim quotes
        """
        controversial: list[dict[str, Any]] = []

        entries = self._get_parsed_entries()
        if not entries:
            return controversial

        try:
            # Backtracking/reconsideration indicators
            controversy_indicators = [
                "actually",
                "wait",
                "hold on",
                "never mind",
                "ignore that",
                "scratch that",
                "revert",
                "on second thought",
                "let me reconsider",
                "i was wrong",
                "correction",
                "that was wrong",
                "no wait",
                "actually let",
                "going to change",
            ]

            # Scan last 150 entries for controversial moments
            for entry in entries[-150:]:
                if entry.get("type") != "assistant":
                    continue

                content_text = self._extract_text_from_entry(entry)
                if len(content_text) < 30:
                    continue

                # Check for controversy indicators (case-insensitive)
                content_lower = content_text.lower()
                for indicator in controversy_indicators:
                    if indicator in content_lower:
                        # Extract verbatim quote (more context around indicator)
                        quote_start = max(0, content_lower.find(indicator) - 50)
                        quote_end = min(len(content_text), quote_start + 400)
                        quote = content_text[quote_start:quote_end].strip()

                        controversial.append(
                            {
                                "quote": quote,
                                "indicator": indicator,
                                "timestamp": entry.get("timestamp", ""),
                                "type": "controversial",
                            }
                        )
                        break

                if len(controversial) >= 5:  # Cap at 5 controversial decisions
                    break

        except Exception as e:
            print(f"[TranscriptParser] Warning: Could not extract controversial decisions: {e}")

        return controversial

    def extract_visual_context(self) -> dict[str, Any] | None:
        """Extract visual context (screenshots, image analysis) from recent transcript.

        Looks for:
        - Image tool results (screenshots, photos)
        - Image analysis outputs
        - User references to visual evidence ("see screenshot", "as shown in image")

        Returns:
            Dict with description, type, and context, or None if no visual context found
        """
        entries = self._get_parsed_entries()
        if not entries:
            return None

        try:
            # Import utility for DRY compliance
            # Scan last 50 entries for visual context
            start_idx = max(0, len(entries) - 50)
            for abs_idx, entry in enumerate(entries[-50:], start=start_idx):
                # Check for tool_use entries that might be image-related
                if entry.get("type") == "tool_use":
                    tool_name = entry.get("name", "")
                    # Image analysis tools
                    if any(img_tool in tool_name.lower() for img_tool in [
                        "analyze_image", "diagnose_error", "extract_text",
                        "ui_to_artifact", "screenshot", "image"
                    ]):
                        # Get tool input/output for context
                        tool_input = entry.get("input", {})
                        tool_result = entry.get("result", {})

                        # Extract image path/prompt if available
                        image_source = tool_input.get("image_source") or tool_input.get("imageSource") or tool_input.get("file_path")
                        prompt = tool_input.get("prompt", "")

                        # Build description
                        desc_parts = [f"Visual analysis using {tool_name}"]
                        if image_source:
                            desc_parts.append(f"of {image_source}")
                        if prompt:
                            desc_parts.append(f"- prompt: '{prompt[:100]}...'")

                        # Check if there's a user message right after this (user responding to image)
                        # Look ahead a few entries using absolute index (avoids duplicate-dict issue)
                        user_response = ""
                        if 0 <= abs_idx < len(entries) - 1:
                            for next_entry in entries[abs_idx + 1:min(abs_idx + 5, len(entries))]:
                                if next_entry.get("type") == "user":
                                    user_response = self._extract_text_from_entry(next_entry)[:200]
                                    break

                        from handoff.config import utcnow_iso
                        return {
                            "description": " ".join(desc_parts),
                            "type": "image_analysis",
                            "tool": tool_name,
                            "user_response": user_response,
                            "timestamp": entry.get("timestamp", utcnow_iso()),
                        }

                # Check user messages for visual references
                if entry.get("type") == "user":
                    content_text = self._extract_text_from_entry(entry).lower()
                    visual_keywords = ["screenshot", "image", "picture", "see the", "as shown", "visual", "ui mockup"]
                    if any(keyword in content_text for keyword in visual_keywords):
                        # Get full text for context
                        full_text = self._extract_text_from_entry(entry)
                        from handoff.config import utcnow_iso
                        return {
                            "description": f"User referenced visual content: {full_text[:200]}",
                            "type": "visual_reference",
                            "timestamp": entry.get("timestamp", utcnow_iso()),
                        }

        except Exception as e:
            print(f"[TranscriptParser] Warning: Could not extract visual context: {e}")

        return None

    def extract_last_user_message(self) -> str | None:
        """Extract the FULL last user message from transcript (untruncated).

        Unlike extract_current_blocker() which truncates to 200 chars,
        this returns the complete message for use in handoff restoration.

        Returns:
            Full user message text, or None if no substantial message found
        """
        entries = self._get_parsed_entries()
        if not entries:
            return None

        try:
            # Read backwards to find the last user message
            for i in range(len(entries) - 1, -1, -1):
                entry = entries[i]
                if entry.get("type") == "user":
                    msg_obj = entry.get("message", {})
                    if not isinstance(msg_obj, dict):
                        continue

                    content = msg_obj.get("content", "")

                    # Handle list content (most common case)
                    if isinstance(content, list):
                        for item in content:
                            # Skip dict items (tool_result, thinking, etc.) - only extract user text
                            if isinstance(item, dict):
                                continue
                            if isinstance(item, str):
                                item = item.strip()
                                # Skip meta tags and system messages
                                if (
                                    item.startswith("<")
                                    or item.startswith("This session is being continued")
                                    or item.startswith("Stop hook feedback")
                                    or len(item) < self._MIN_CONTENT_LENGTH
                                ):
                                    continue
                                # Return FULL message, not truncated
                                return item
                    # Handle string content
                    elif isinstance(content, str) and len(content.strip()) > self._MIN_CONTENT_LENGTH:
                        user_message = content.strip()
                        if not user_message.startswith("<"):
                            return user_message
        except Exception as e:
            print(f"[TranscriptParser] Warning: Could not extract last user message: {e}")

        return None

    def get_transcript_offset(self) -> int:
        """Get the character offset (position) in the transcript file.

        This represents the exact position where the transcript currently ends,
        which can be used for exact resume tracking. The offset is the total
        number of characters in the transcript file.

        Returns:
            Character offset in the transcript file (0 if file unavailable)
        """
        if not self.transcript_path or not Path(self.transcript_path).exists():
            return 0

        try:
            return Path(self.transcript_path).stat().st_size
        except OSError as e:
            print(f"[TranscriptParser] Warning: Could not get transcript size: {e}")
            return 0

    def get_transcript_entry_count(self) -> int:
        """Get the number of entries in the transcript.

        Returns the count of parsed JSON entries at checkpoint time.

        Returns:
            Number of entries in the transcript (0 if unavailable)
        """
        entries = self._get_parsed_entries()
        return len(entries)

    def extract_pending_operations(self) -> list[dict[str, Any]]:
        """Extract incomplete operations from transcript for fault tolerance.

        Detects tool calls that were invoked but may not have completed,
        allowing recovery after compaction or interruption.

        Returns:
            List of pending operation dicts with type, target, state, details

        Note:
            - Incomplete operations identified by tool invocation without matching result
            - Returns empty list if no pending operations detected
            - Operations include: edit, test, read, command, skill
        """
        entries = self._get_parsed_entries()
        if not entries:
            return []

        pending_ops = []

        # Track tool calls that may not have completed
        # Simple heuristic: consecutive tool calls without results suggest pending work
        for i, entry in enumerate(entries):
            entry_type = entry.get("type", "")

            # Detect tool calls
            if entry_type == "assistant":
                content = self._extract_text_from_entry(entry).lower()

                # Look for patterns indicating incomplete operations
                # This is a simple heuristic - can be enhanced with more sophisticated analysis
                if any(keyword in content for keyword in [
                    "editing", "running test", "executing", "processing"
                ]):
                    # Try to extract target from context
                    target = "unknown"
                    if "file" in content:
                        # Simple file path extraction
                        words = content.split()
                        for word in words:
                            if "." in word and "/" in word:
                                target = word.strip('".')
                                break

                    # Determine operation type from context
                    op_type = "command"  # default
                    if "edit" in content or "modify" in content or "write" in content:
                        op_type = "edit"
                    elif "test" in content:
                        op_type = "test"
                    elif "read" in content:
                        op_type = "read"

                    pending_ops.append({
                        "type": op_type,
                        "target": target,
                        "state": "in_progress",
                        "details": {"context": content[:200]}  # Truncate for size
                    })

                    # Limit to prevent excessive pending operations
                    if len(pending_ops) >= 5:
                        break

        return pending_ops


if __name__ == "__main__":
    # Direct test block for manual testing
    import sys

    # Usage: python transcript.py <path_to_transcript.json>
    if len(sys.argv) > 1:
        test_path = sys.argv[1]
        parser = TranscriptParser(test_path)

        print("=== Testing TranscriptLines ===")
        lines = TranscriptLines(test_path)
        print(f"Total lines: {len(lines)}")
        if len(lines) > 0:
            print(f"First line: {lines[0][:100]}")
        if len(lines) > 1:
            print(f"Last line: {lines[-1][:100]}")

        print("\n=== Testing TranscriptParser ===")
        blocker = parser.extract_current_blocker()
        print(f"Current blocker: {blocker}")

        mods = parser.extract_modifications()
        print(f"Modifications: {len(mods)} found")

        decisions = parser.extract_session_decisions()
        print(f"Session decisions: {len(decisions)} found")

        patterns = parser.extract_session_patterns()
        print(f"Session patterns: {len(patterns)} found")

        controversial = parser.extract_controversial_decisions()
        print(f"Controversial decisions: {len(controversial)} found")
    else:
        print("Usage: python transcript.py <path_to_transcript.json>")


def extract_user_message_from_blocker(blocker: dict[str, Any] | str | None) -> str | None:
    """Extract the user's last message from a blocker.

    The blocker description may contain a "User's last question:" prefix.
    This function strips that prefix to return the actual user message.

    Args:
        blocker: Blocker dict with 'description' field, or string description

    Returns:
        The user's message without the prefix, or None if no valid message found

    Examples:
        >>> blocker = {"description": "User's last question: implement feature X"}
        >>> extract_user_message_from_blocker(blocker)
        'implement feature X'

        >>> extract_user_message_from_blocker("User's last question: fix bug")
        'fix bug'

        >>> extract_user_message_from_blocker(None)
        None
    """
    if not blocker:
        return None

    # Get description from dict or use string directly
    if isinstance(blocker, dict):
        description = blocker.get("description", "")
    elif isinstance(blocker, str):
        description = blocker
    else:
        return None

    if not description:
        return None

    # Strip "User's last question:" prefix if present
    prefix = "User's last question:"
    if prefix in description:
        # Split on prefix and take everything after it
        user_message = description.split(prefix, 1)[-1].strip()
        return user_message if user_message else None

    # No prefix found - return description as-is (might already be clean)
    return description if description else None


def filter_valid_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter valid messages from a list, removing invalid entries.

    This function validates and filters messages, handling:
    - Non-dict items (None, strings, numbers, lists, etc.)
    - Messages missing required 'role' field
    - Messages with invalid value types (e.g., role not a string, content not a string)

    Args:
        messages: List of message items (may contain non-dict items)

    Returns:
        Filtered list of valid message dictionaries with all fields preserved.
        Returns empty list if no valid messages found.
    """
    if not messages:
        return []

    valid_messages = []

    for message in messages:
        # Skip if message is not a dict
        if not isinstance(message, dict):
            continue

        # Check for required 'role' field
        if "role" not in message:
            continue

        # Validate that 'role' is a string
        role = message.get("role")
        if not isinstance(role, str):
            continue

        # If 'content' field exists, validate it's a string
        if "content" in message:
            content = message.get("content")
            # Content must be a string (can be empty string, but not None, list, dict, etc.)
            if not isinstance(content, str):
                continue

        # Message is valid - preserve all fields
        valid_messages.append(message)

    return valid_messages


def extract_transcript_from_messages(messages: list[dict[str, Any]]) -> str:
    """Extract transcript text from a list of messages.

    This function extracts and concatenates the 'content' field from valid messages,
    handling edge cases gracefully:
    - Empty lists return empty string
    - Missing 'content' fields are skipped
    - None content values are skipped
    - Empty/whitespace-only strings are skipped
    - Non-string content types are converted to strings

    Args:
        messages: List of message dictionaries

    Returns:
        Concatenated transcript text with newlines between messages.
        Returns empty string if no valid content found.
    """
    if not messages:
        return ""

    transcript_parts = []

    for message in messages:
        # Skip messages without 'content' field
        if "content" not in message:
            continue

        content = message.get("content")

        # Skip None values
        if content is None:
            continue

        # Convert non-string types to string
        if not isinstance(content, str):
            content = str(content)

        # Strip whitespace
        content = content.strip()

        # Skip empty strings after stripping
        if not content:
            continue

        transcript_parts.append(content)

    return "\n".join(transcript_parts)

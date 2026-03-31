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
from typing import Annotated, Any, Literal, TypedDict, overload

logger = logging.getLogger(__name__)

# Intent classification types
MessageIntent = Literal[
    "question",
    "instruction",
    "correction",
    "directive",
    "meta",
    "unsupported_language",
]

# Pre-compiled regex patterns for intent classification (SEC-002: ReDoS prevention)
# Pre-compilation improves performance (~1.5x faster) and prevents catastrophic backtracking
META_PATTERNS = [
    # Acknowledgments (standalone or short phrases only)
    re.compile(r"^(thanks|thank you)([\s,;!]+(?:for|with) .+)?[\s,;!]*$"),
    re.compile(r"^(ok|good|great|perfect)[\s,;!]*$"),
    re.compile(r"^that's all[\s,;!]*$"),
    re.compile(r"^done[\s,;!]*$"),
    re.compile(r"^finish[\s,;!]*$"),
    # Short conversational meta-requests
    re.compile(r"^summarize (what|everything) (we did|we've done|happened)([\s,;!]*)$"),
    re.compile(r"^are we (done|ready|finished)( yet)?[\s,;!]*$"),
    # Task management
    re.compile(r"^(summarize|explain)([\s,;!]+that)?[\s,;!]*$"),
    re.compile(r"^(revert|rollback)([\s,;!]+it)?[\s,;!]*$"),
    # Session continuation
    re.compile(r"^this session is being continued from a previous conversation"),
    # Command invocation
    re.compile(r"^<command-"),
    # Verification and meta-questions
    re.compile(r"^do we (have|need)"),
    re.compile(r"^do you (have|need)"),
    re.compile(r"^did (?:the |this )?(?:handoff|system|it|that) work"),
    re.compile(r"^is (?:this|that|the) (correct|right|optimal|good|working)"),
    re.compile(r"^are (we|you) (sure|done|ready)"),
    re.compile(r"^can you (verify|check|confirm)"),
    re.compile(r"^check (if|whether|that)"),
    re.compile(r"^verify (that|if|whether)"),
    re.compile(r"^should (?:i|we) "),
    re.compile(r"^would you like"),
    re.compile(r"^base directory for this skill:"),
]

CORRECTION_PATTERNS = [
    # Direct negations of task understanding
    re.compile(r"^no,? (?:the )?task is not about"),
    re.compile(r"^not about teaching"),
    re.compile(r"^the task is not about"),
    # Explicit "wrong task" indicators
    re.compile(r"^that'?s? not what i asked"),
    re.compile(r"^you did the wrong task"),
    # Explicit "wrong" indicators (expanded)
    re.compile(r"^that'?s? (?:wrong|incorrect)"),
    re.compile(r"^(?:that's|it's) wrong"),
    # Explicit "wrong about" indicators
    re.compile(r"^you(?:'?re| are) wrong about"),
    # Explicit "didn't ask for" indicators
    re.compile(r"^i didn'?t ask for"),
    # AI state criticism
    re.compile(
        r"^you(?:('?re| are) (?:losing your mind|making stuff up|hallucinating|confused|misinterpreting)| (?:misunderstood|misinterpreted))"
    ),
    re.compile(r"^stop (?:hallucinating|making stuff up)"),
    # Clarification corrections
    re.compile(r"^that's not (?:what i meant|the task)"),
    re.compile(r"^let me clarify"),
    # Mid-message corrections (expanded to catch more patterns)
    re.compile(r"^wait, (?:that's not|that's wrong|you're|hold on)"),
    re.compile(r"^actually, (?:not that|no -|wrong|fix|instead)"),
    re.compile(r"^actually, \w+"),
    re.compile(r"^hold on,"),
    # Correction marker
    re.compile(r"^correction:"),
    # Fix-related corrections (common pattern: "fix X instead")
    re.compile(r"^(?:actually, )?fix \w+ instead"),
]

# Clarification patterns: messages asking for explanation or meaning
# These indicate the user wants the AI to clarify something rather than perform a task
CLARIFICATION_PATTERNS = [
    # Direct clarification requests
    re.compile(r"^what do you mean"),
    re.compile(r"^what does .* mean"),
    re.compile(r"^could you clarify"),
    re.compile(r"^can you clarify"),
    re.compile(r"^i don'?t understand"),
    re.compile(r"^i doesn'?t understand"),
    re.compile(r"^i can't (?:really | )?understand"),
    re.compile(r"^can you explain"),
    re.compile(r"^could you explain"),
    re.compile(r"^please clarify"),
    re.compile(r"^clarify (?:please | )?(?:what|how)"),
    re.compile(r"^what (?:do you|does it|does that) refer to"),
    re.compile(r"^what (?:are we|is this|do you) talking about"),
    re.compile(r"^i'?m (?:a bit | )?confused"),
    re.compile(r"^that(?:'s| is) (?:not |un)?clear"),
    re.compile(r"^could you (?:please | )?rephrase"),
    re.compile(r"^say that again"),
    re.compile(r"^repeat (?:that|please)"),
    re.compile(r"^what (?:did you|do you) mean by"),
    re.compile(r"^i(?:'m| am) not sure (?:what|how|why)"),
    re.compile(r"^not sure (?:what|how|why)"),
    re.compile(r"^i(?:'m| am) confused about"),
    # Questions seeking explanation (not directive)
    re.compile(r"^why (?:does|is|do|are|would|should)"),
    re.compile(r"^how (?:does|do|is|are|can|should)"),
    re.compile(r"^what (?:is|are|does|do|exactly)"),
    # Clarification about AI's previous statement
    re.compile(r"^when you say"),
    re.compile(r"^you mentioned .*[?]$"),
    re.compile(r"^so .* mean[s]? .*[?]$"),
]

# Directive patterns: imperative verbs that indicate explicit task directives
# These represent substantive changes the user wants the agent to perform
DIRECTIVE_PATTERNS = [
    # Core imperative verbs (single-word command starts)
    re.compile(
        r"^(?:fix|add|remove|delete|create|update|refactor|implement|build|write|edit|change|rename|move|extract|inline|optimize|improve|enhance|clean|simplify|consolidate|deprecate|extract|introduce|merge|split|separate|combine)\s+\S"
    ),
    # "do X" pattern (strong directive signal)
    re.compile(
        r"^do\s+(?:not\s+)?(?:the\s+)?(?:following\s+)?(?:file\s+)?(?:this\s+)?"
    ),
    # Explicit directive markers
    re.compile(r"^make\s+(?:\w+\s+){0,3}(?:work|go|function| happen)"),
    re.compile(r"^ensure\s+\w+"),
    re.compile(r"^ensure\s+\w+\s+\w+\s+\w+"),
    # Imperative with "that" (commanding consequence)
    re.compile(r"^make\s+sure\s+"),
    # Task assignment patterns
    re.compile(r"^go\s+ahead\s+"),
    re.compile(
        r"^please\s+(?:do|add|fix|create|update|implement|remove|delete|change|refactor|build|write|edit|rename|move|extract|inline|optimize|clean|simplify|consolidate)\s+"
    ),
    # Imperative "must" (strong directive)
    re.compile(r"^\w+\s+must\s+(?:be\s+)?(?:done\s+)?(?:to\s+)?(?:the\s+)?(?:\w+\s+)?"),
    # Bare imperative (single word at start of line)
    re.compile(
        r"^(?:fix|add|remove|delete|create|update|refactor|implement|build|write|edit|change|rename|move|extract|inline|optimize|clean|simplify|consolidate|deprecate|extract|introduce|merge|split|separate|combine)\s*[\.:;]?\s*$",
        re.IGNORECASE,
    ),
]

# Meta-discussion patterns (conversations about the system itself)
META_DISCUSSION_PATTERNS = [
    re.compile(r"^so you're (just|going to)"),
    re.compile(r"^i don't (understand|get) (task|step|phase)"),
    re.compile(
        r"^(did|is) (it|this|that|the system) (work|working|optimal|correct|right|good)"
    ),
    re.compile(r"^(are there|do we have) (more|any)"),
    re.compile(r"^(what's|whats) (?:the |an |optimal )?(solution|problem|issue)"),
    re.compile(r"^(are|do) you (hate|like)"),
    re.compile(r"^(should|will) we (continue|proceed)"),
    re.compile(r"^(do|would) you (hate|like)"),
    re.compile(r"^so (what|where)"),
]

# Conversational ending patterns (confirmation markers)
CONVERSATIONAL_ENDINGS_PATTERNS = [
    re.compile(r" (remember|right|ok|okay|correct)\?*$"),
]


def _contains_non_ascii(text: str) -> bool:
    """Check if text contains non-ASCII (non-English) characters.

    This is used to block non-English messages from being silently
    misclassified as "instructions". Non-English text will be
    classified as "unsupported_language" instead.

    Args:
        text: The text to check

    Returns:
        True if text contains non-ASCII characters, False otherwise
    """
    try:
        text.encode("ascii")
        return False
    except UnicodeEncodeError:
        return True


def detect_message_intent(message: str) -> MessageIntent:
    """Detect the intent of a user message.

    Classifies messages into 5 categories:
    - question: User is asking something (ends with ? or starts with question word)
    - instruction: User is requesting action (default)
    - correction: User is correcting previous output
    - meta: User is providing meta-instruction (thanks, summarize, etc.)
    - unsupported_language: Message contains non-ASCII characters

    Args:
        message: The user message to classify

    Returns:
        The detected intent category
    """
    # Type validation: handle non-string inputs (int, list, dict, etc.)
    if not isinstance(message, str):
        return "instruction"  # Safe default for non-string types

    # Handle empty string input
    if not message.strip():
        return "instruction"  # Safe default for empty input

    text = message.strip()

    # BLOCK: Reject non-English messages (contains non-ASCII characters)
    if _contains_non_ascii(text):
        return "unsupported_language"

    # Check for correction messages FIRST (before meta check)
    # Correction patterns are very specific and should take priority
    if is_correction_message(text):
        return "correction"

    # Additional correction pattern for "No, that's not what I asked" format
    # This pattern is common but not covered by is_correction_message
    text_lower = text.lower()
    if re.match(r"^no,? that'?s? not what i asked", text_lower):
        return "correction"

    # Check for question patterns BEFORE meta check
    # Questions ending with '?' should be detected as questions, not meta
    # Note: "when " is NOT a question starter - it's commonly used as temporal marker
    # in instructions like "When you're done, commit"
    question_starters = (
        "is ",
        "are ",
        "do ",
        "does ",
        "did ",
        "can ",
        "could ",
        "would ",
        "should ",
        "will ",
        "won't ",
        "what ",
        "where ",
        "why ",
        "how ",
    )

    # Question contains '?' - detects mid-sentence questions like "What? I don't understand"
    # Note: May match abbreviations (C.I.A.) but these are rare in user messages
    if "?" in text:
        return "question"

    # Question starts with question word (excluding "when" which is often temporal)
    if text_lower.startswith(question_starters):
        return "question"

    # Check for meta-instructions (lowest priority before default)
    if is_meta_instruction(text):
        return "meta"

    # Check for directive patterns (imperative task commands)
    # These are explicit directives like "fix X", "add Y", "refactor Z"
    if is_directive_message(text):
        return "directive"

    # Default: instruction
    return "instruction"


# TypedDict definitions for public API type safety (QUAL-003)
class StructureInfo(TypedDict):
    """TypedDict for detect_structure_type return value.

    Attributes:
        type: The structure type detected (e.g., "analysis_table", "priority_matrix", "comparison")
        search_keys: List of search keys extracted from the content
    """

    type: str
    search_keys: list[str]


class BlockerDef(TypedDict):
    """TypedDict for blocker parameter in extract_user_message_from_blocker.

    Attributes:
        description: Description of the blocker, may contain "User's last question:" prefix
    """

    description: str


class MessageDict(TypedDict):
    """TypedDict for message items in filter_valid_messages and extract_transcript_from_messages.

    Attributes:
        role: Message role (e.g., "user", "assistant", "system")
        content: Message content (string or list of content items)
    """

    role: str
    content: str | list[Any]


class GoalExtractionResult(TypedDict, total=False):
    """TypedDict for extract_last_substantive_user_message return value.

    Provides observability into goal extraction process for debugging and monitoring.

    Attributes:
        goal: Extracted goal message (or "Unknown task")
        message_intent: Detected intent of the message (question, instruction, etc.)
        messages_scanned: Number of user messages scanned
        corrections_skipped: Number of correction messages skipped
        meta_skipped: Number of meta-instructions skipped
        session_boundary_hit: Whether scan stopped at session boundary
        topic_shift_hit: Whether scan stopped at topic shift
        scan_pattern: Description of scan pattern used
    """

    goal: str
    message_intent: MessageIntent
    messages_scanned: int
    corrections_skipped: int
    meta_skipped: int
    session_boundary_hit: bool
    topic_shift_hit: bool
    scan_pattern: str


# Module-level helper functions (extracted from HandoverBuilder static methods)
def extract_topic_from_content(
    content: str, task_name: str = ""
) -> Annotated[str, "max_length=80"]:
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


def _get_table_indicators() -> list[str]:
    """Get table structure indicator patterns.

    Returns:
        List of box drawing, markdown, and ASCII table indicators
    """
    return [
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


def _get_assessment_indicators() -> list[str]:
    """Get value assessment indicator patterns.

    Returns:
        List of assessment and priority matrix keywords
    """
    return [
        "high",
        "medium",
        "low",
        "priority",
        "value",
        "rationale",
        "assessment",
    ]


def _get_comparison_indicators() -> list[str]:
    """Get comparison indicator patterns.

    Returns:
        List of comparison and option keywords
    """
    return [
        "pros",
        "cons",
        "trade-off",
        "versus",
        "vs.",
        "option a",
        "option b",
    ]


def _check_for_table_structure(content: str) -> bool:
    """Check if content contains table structure indicators.

    Args:
        content: Text content to analyze

    Returns:
        True if table indicators found
    """
    table_indicators = _get_table_indicators()
    return any(indicator in content for indicator in table_indicators)


def _check_for_assessment(content_lower: str) -> bool:
    """Check if content contains assessment indicators.

    Args:
        content_lower: Lowercase text content to analyze

    Returns:
        True if 3+ assessment indicators found
    """
    assessment_indicators = _get_assessment_indicators()
    return sum(1 for ind in assessment_indicators if ind in content_lower) >= 3


def _check_for_comparison(content_lower: str) -> bool:
    """Check if content contains comparison indicators.

    Args:
        content_lower: Lowercase text content to analyze

    Returns:
        True if comparison indicators found
    """
    comparison_indicators = _get_comparison_indicators()
    return any(ind in content_lower for ind in comparison_indicators)


def _extract_search_keys(content_lower: str, max_keys: int = 5) -> list[str]:
    """Extract search keys from content.

    Args:
        content_lower: Lowercase text content to analyze
        max_keys: Maximum number of keys to extract

    Returns:
        List of unique, meaningful key terms
    """
    # Extract key terms for searching (skip common words)
    key_terms = [w for w in content_lower.split() if len(w) > 4 and w.isalpha()]

    # Filter to unique, meaningful terms
    common_words = {"this", "that", "with", "from", "been"}
    search_keys: list[str] = []
    seen: set[str] = set()

    for term in key_terms:
        if term not in seen and term not in common_words:
            search_keys.append(term)
            seen.add(term)
            if len(search_keys) >= max_keys:
                break

    return search_keys


def _determine_structure_type(
    has_table: bool,
    has_assessment: bool,
    has_comparison: bool,
    search_keys: list[str],
) -> StructureInfo | None:
    """Determine structure type from detection results.

    Args:
        has_table: Whether table structure detected
        has_assessment: Whether assessment detected
        has_comparison: Whether comparison detected
        search_keys: Extracted search keys

    Returns:
        StructureInfo with "type" and "search_keys", or None if unstructured
    """
    if has_table:
        return StructureInfo(type="analysis_table", search_keys=search_keys)
    elif has_assessment:
        return StructureInfo(type="priority_matrix", search_keys=search_keys)
    elif has_comparison:
        return StructureInfo(type="comparison", search_keys=search_keys)

    return None


def detect_structure_type(content: str) -> StructureInfo | None:
    """Detect structured content format (tables, comparisons, assessments).

    Args:
        content: Text content to analyze

    Returns:
        Dict with "type" and optional "search_keys", or None if unstructured
    """
    content_lower = content.lower()

    # Check for different structure types
    has_table_structure = _check_for_table_structure(content)
    has_assessment = _check_for_assessment(content_lower)
    has_comparison = _check_for_comparison(content_lower)

    # Extract search keys if any structure detected
    search_keys: list[str] = []
    if has_table_structure or has_assessment or has_comparison:
        search_keys = _extract_search_keys(content_lower)

    # Determine and return structure type
    return _determine_structure_type(
        has_table_structure,
        has_assessment,
        has_comparison,
        search_keys,
    )


def is_meta_instruction(message: str) -> bool:
    """Check if a message is a meta-instruction that should be skipped.

    Meta-instructions are conversational filler like "thanks", "summarize", etc.
    that don't represent substantive tasks.

    Args:
        message: Message text to check

    Returns:
        True if message is a meta-instruction, False otherwise
    """
    if not message or not isinstance(message, str):
        return False

    message_lower = message.strip().lower()

    # Use pre-compiled META_PATTERNS (SEC-002: ReDoS fix)
    for pattern in META_PATTERNS:
        if pattern.match(message_lower):
            return True

    return False


def is_meta_discussion(message: str) -> bool:
    """Check if a message is meta-discussion about the system/conversation itself.

    Meta-discussion patterns include:
    - Conversational questions starting with "So you're...", "I don't understand..."
    - Statements about the conversation ("Let's continue", "Did it work?")
    - System/process questions ("Is it optimal?", "Are there more fixes?")

    This differs from is_meta_instruction() which filters simple filler.
    Meta-discussion represents conversation ABOUT the work rather than the work itself.

    Args:
        message: Message text to check

    Returns:
        True if message is meta-discussion, False otherwise
    """
    if not message or not isinstance(message, str):
        return False

    message_lower = message.strip().lower()

    # First check if it's a simple meta-instruction (conversational filler)
    if is_meta_instruction(message):
        return True

    # Meta-discussion question patterns (conversations about the system itself)
    # Use pre-compiled META_DISCUSSION_PATTERNS (SEC-002: ReDoS prevention)
    for pattern in META_DISCUSSION_PATTERNS:
        if pattern.match(message_lower):
            return True

    # Check for questions about the system itself (conversation about the system)
    # This catches longer questions like "Is this handoff system working correctly?"
    system_keywords = ["handoff", "system", "conversation", "extraction", "this"]
    question_keywords = [
        "work",
        "optimal",
        "correct",
        "right",
        "good",
        "broken",
        "working",
    ]

    if any(kw in message_lower for kw in system_keywords):
        if any(kw in message_lower for kw in question_keywords):
            return True

    # Check for conversational confirmation markers at the end
    # These indicate the message is asking for agreement rather than stating requirements
    # Use pre-compiled CONVERSATIONAL_ENDINGS_PATTERNS (SEC-002: ReDoS prevention)
    for pattern in CONVERSATIONAL_ENDINGS_PATTERNS:
        if pattern.search(message_lower):
            return True

    # Messages ending with "?" that are conversational (not requirement questions)
    # Conversational questions are typically short and ask about system/process
    if message_lower.endswith("?"):
        # Short questions about the system/process are conversational
        if len(message) < 100:
            conversational_patterns = [
                "did it",
                "is it",
                "are there",
                "do we",
                "should we",
                "can we",
                "will it",
            ]
            if any(pat in message_lower for pat in conversational_patterns):
                return True

    return False


def is_correction_message(message: str) -> bool:
    """Check if a message is a user correction about previous AI behavior.

    Correction patterns indicate the AI misunderstood something, and the
    message is about what the task ISN'T rather than what it IS.

    This prevents capturing correction messages as the "goal" during handoff,
    which would cause the AI to repeat the same mistake after session restore.

    Examples:
    - "No, the task is not about teaching users"
    - "That's not what I asked"
    - "You did the wrong task"
    - "You're wrong about X"

    Args:
        message: Message text to check

    Returns:
        True if message is a correction, False otherwise
    """
    if not message or not isinstance(message, str):
        return False

    message_lower = message.strip().lower()

    # Use pre-compiled CORRECTION_PATTERNS (SEC-002: ReDoS fix)
    for pattern in CORRECTION_PATTERNS:
        if pattern.search(message_lower):
            logger.debug(
                f"Correction pattern matched: {pattern.pattern[:30]}... in '{message[:50]}...'"
            )
            return True

    return False


def is_clarification_message(message: str) -> bool:
    """Check if a message is a clarification request.

    Clarification patterns indicate the user is asking the AI to explain
    or clarify something rather than perform a task. These include questions
    about meaning, understanding, or explanation.

    This is used by PreCompact to detect when the user's goal is a
    clarification request, so it can extract preceding context.

    Args:
        message: Message text to check

    Returns:
        True if message is a clarification request, False otherwise
    """
    if not message or not isinstance(message, str):
        return False

    message_lower = message.strip().lower()

    # Use pre-compiled CLARIFICATION_PATTERNS (SEC-002: ReDoS fix)
    for pattern in CLARIFICATION_PATTERNS:
        if pattern.search(message_lower):
            logger.debug(
                f"Clarification pattern matched: {pattern.pattern[:30]}... in '{message[:50]}...'"
            )
            return True

    return False


def is_directive_message(message: str) -> bool:
    """Check if a message is a directive indicating explicit task direction.

    Directive patterns indicate the user is commanding the agent to perform
    a specific action, using imperative verbs like "fix", "add", "refactor",
    "create", "update", etc.

    This is used by the AIR Auditor to detect explicit user directives
    that should be tracked against agent actions.

    Args:
        message: Message text to check

    Returns:
        True if message is a directive, False otherwise
    """
    if not message or not isinstance(message, str):
        return False

    message_lower = message.strip().lower()

    # Use pre-compiled DIRECTIVE_PATTERNS
    for pattern in DIRECTIVE_PATTERNS:
        if pattern.match(message_lower):
            logger.debug(
                f"Directive pattern matched: {pattern.pattern[:30]}... in '{message[:50]}...'"
            )
            return True

    return False


def is_same_topic(message1: str, message2: str, threshold: float = 0.2) -> bool:
    """Check if two messages are about the same topic using keyword overlap.

    Uses simple keyword overlap algorithm (pure stdlib, no external dependencies).
    Calculates: intersection / union ratio, returns True if > threshold.
    Uses word-splitting for better partial word matching (e.g., "test" vs "testing").

    Args:
        message1: First message text
        message2: Second message text
        threshold: Minimum overlap ratio (default: 0.2 = 20%)

    Returns:
        True if messages share > threshold keyword overlap, False otherwise
    """
    if not message1 or not message2:
        return False

    # Tokenize both messages by splitting on whitespace and punctuation
    # This handles "test" vs "testing" as separate words
    import re

    # Remove punctuation and split into words
    words1 = set(re.findall(r"\b\w+\b", message1.lower()))
    words2 = set(re.findall(r"\b\w+\b", message2.lower()))

    if not words1 or not words2:
        return False

    # Calculate overlap ratio: intersection / union
    intersection = words1 & words2
    union = words1 | words2

    if not union:
        return False

    overlap_ratio = len(intersection) / len(union)

    return overlap_ratio > threshold


def detect_session_boundary(entry: dict, prev_entry: dict | None) -> bool:
    """Detect if there's a session boundary between two entries.

    Session boundaries occur when:
    - session_chain_id field changes
    - Explicit "new task" indicators in content

    Note: Timestamp gaps are NOT used as session boundaries because:
    - A 1-hour gap could just be a lunch break during the same task
    - session_chain_id is the authoritative source for session changes

    Args:
        entry: Current transcript entry
        prev_entry: Previous transcript entry (None for first entry)

    Returns:
        True if session boundary detected, False otherwise
    """
    if not prev_entry:
        return False

    # Check for session_chain_id change (authoritative session boundary)
    current_session_id = entry.get("session_chain_id")
    prev_session_id = prev_entry.get("session_chain_id")

    if current_session_id and prev_session_id:
        if current_session_id != prev_session_id:
            logger.debug(
                f"Session boundary detected: {prev_session_id} → {current_session_id}"
            )
            return True

    # Check for explicit "new task" indicators
    if entry.get("type") == "user":
        content = entry.get("message", {}).get("content", [])
        if isinstance(content, list):
            for item in content:
                if isinstance(item, str):
                    if re.search(r"\bnew task\b", item, re.IGNORECASE):
                        logger.debug("Session boundary detected: 'new task' marker")
                        return True

    return False


def gather_context_with_boundaries(
    transcript_path: str | Path, max_messages: int = 50
) -> list[dict]:
    """Gather context from transcript, respecting session boundaries and topic shifts.

    Works backwards from transcript end, collecting entries until:
    - Session boundary detected (session_chain_id change or significant timestamp gap)
    - Topic shift detected (keyword overlap < 30%)
    - Max messages reached

    Args:
        transcript_path: Path to transcript JSONL file
        max_messages: Maximum number of messages to collect (default: 50)

    Returns:
        List of transcript entries in reverse order (newest first)
    """

    transcript_path = Path(transcript_path)
    context: list[dict] = []

    if not transcript_path.exists():
        logger.warning(f"Transcript file not found: {transcript_path}")
        return context

    try:
        with open(transcript_path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        logger.error(f"Failed to read transcript: {e}")
        return context

    # Work backwards from the end
    prev_entry = None
    prev_message_text = None
    prev_role = None
    stop_after_this = False

    for line in reversed(lines):
        if len(context) >= max_messages:
            break

        line = line.strip()
        if not line:
            continue

        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        # Extract message text for topic comparison
        # Handle both simple string messages and complex content structures
        current_message_text = ""
        # TEST-001 FIX: Use 'type' field (correct) instead of 'role' (wrong)
        # Claude Code transcripts use 'type': 'user' not 'role': 'user'
        current_role = entry.get("type", "")

        if "message" in entry:
            message = entry["message"]
            if isinstance(message, str):
                current_message_text = message
            elif isinstance(message, dict):
                content = message.get("content", [])
                if isinstance(content, str):
                    current_message_text = content
                elif isinstance(content, list):
                    # Concatenate text content from list
                    text_parts = []
                    for item in content:
                        if isinstance(item, str):
                            text_parts.append(item)
                        elif isinstance(item, dict):
                            text_parts.append(item.get("text", ""))
                    current_message_text = " ".join(text_parts)

        # Check for session boundary
        if prev_entry is not None:
            # Check for session_chain_id change
            current_session_id = entry.get("session_chain_id")
            prev_session_id = prev_entry.get("session_chain_id")

            if current_session_id and prev_session_id:
                if current_session_id != prev_session_id:
                    logger.debug(
                        f"Context gathering stopping: session boundary "
                        f"({prev_session_id} → {current_session_id})"
                    )
                    stop_after_this = True

            # Check for topic shift (only between user messages)
            # Skip short meta-messages like "OK", "Continue", etc.
            if not stop_after_this:
                if (
                    prev_role == "user"
                    and current_role == "user"
                    and prev_message_text
                    and current_message_text
                    and len(current_message_text) > 10
                    and len(prev_message_text) > 10
                ):
                    if not is_same_topic(
                        current_message_text, prev_message_text, threshold=0.2
                    ):
                        logger.debug(
                            f"Context gathering stopping: topic shift "
                            f"('{current_message_text[:50]}...' vs "
                            f"'{prev_message_text[:50]}...')"
                        )
                        stop_after_this = True

        context.append(entry)

        # Stop after adding this entry if boundary was detected
        if stop_after_this:
            break

        prev_entry = entry
        prev_message_text = current_message_text
        prev_role = current_role

    return context


def extract_last_substantive_user_message(
    transcript_path: str | Path,
) -> GoalExtractionResult:
    """Extract last substantive user message, skipping meta-instructions and corrections.

    BUG FIX (2026-03-21): The backward scanning loop had an early return that
    prevented state updates. This caused `previous_message_text` to never update
    from None, breaking topic shift detection. The fix: (1) removed early return
    inside loop, (2) added state update `previous_message_text = message_text` on each
    iteration, (3) return after loop completes to return most recent substantive
    message.

    Scans backwards from transcript end, skipping:
    - Meta-instructions ("thanks", "summarize", "explain", "revert", "rollback")
    - Correction messages ("No, the task is not about...", "That's not what I asked")
    - System continuation markers
    - Continuation summaries ("This session is being continued from a previous conversation")
    - Command invocations ("<command-...")

    Stops at:
    - Session boundary (session_chain_id change)
    - Topic shift (semantic similarity < 30%)

    Returns structured dict with observability data including:
    - goal: Extracted goal message (or "Unknown task")
    - messages_scanned: Number of user messages scanned
    - corrections_skipped: Number of correction messages skipped
    - meta_skipped: Number of meta-instructions skipped
    - session_boundary_hit: Whether scan stopped at session boundary
    - topic_shift_hit: Whether scan stopped at topic shift

    Args:
        transcript_path: Path to transcript JSONL file

    Returns:
        GoalExtractionResult with goal and observability metadata
    """
    # Initialize observability counters
    messages_scanned = 0
    corrections_skipped = 0
    meta_skipped = 0
    session_boundary_hit = False
    topic_shift_hit = False

    try:
        parser = TranscriptParser(transcript_path)
        entries = parser._get_parsed_entries()

        if not entries:
            logger.warning("No transcript entries found")
            return {
                "goal": "Unknown task",
                "message_intent": "instruction",  # Default for unknown task
                "messages_scanned": 0,
                "corrections_skipped": 0,
                "meta_skipped": 0,
                "session_boundary_hit": False,
                "topic_shift_hit": False,
                "scan_pattern": "no_entries",
            }

        # Scan backwards from end to find most recent substantive message
        last_session_chain_id = None
        previous_message_text = None

        for entry in reversed(entries):
            # Check for session boundary (session_chain_id change)
            current_chain_id = entry.get("session_chain_id")
            if (
                current_chain_id
                and last_session_chain_id
                and current_chain_id != last_session_chain_id
            ):
                logger.info("Session boundary detected - stopping scan")
                session_boundary_hit = True
                break
            if current_chain_id:
                last_session_chain_id = current_chain_id

            # Only process user messages
            if entry.get("type") != "user":
                continue

            messages_scanned += 1
            message_text = parser._extract_text_from_entry(entry).strip()
            message_text = message_text.strip()

            # Skip empty or too-short messages
            if len(message_text) < 10:
                continue

            # Skip meta-instructions
            if is_meta_instruction(message_text):
                logger.debug(f"Skipping meta-instruction: {message_text[:50]}...")
                meta_skipped += 1
                continue

            # NEW: Skip correction messages - continue scanning for actual task
            if is_correction_message(message_text):
                logger.debug(f"Skipping correction message: {message_text[:50]}...")
                corrections_skipped += 1
                continue

            # Check for topic shift (if we have a previous message to compare)
            if previous_message_text:
                if not is_same_topic(
                    message_text, previous_message_text, threshold=0.3
                ):
                    logger.info(
                        f"Topic shift detected - stopping scan (prev: {previous_message_text[:50]}..., curr: {message_text[:50]}...)"
                    )
                    topic_shift_hit = True
                    break

            # Update previous message for next iteration's topic comparison
            previous_message_text = message_text
            logger.info(
                f"Stored substantive message for topic comparison: {message_text[:100]}{'...' if len(message_text) > 100 else ''}"
            )

        # Return the most recent substantive message found during scan
        if previous_message_text:
            message_intent = detect_message_intent(previous_message_text)
            logger.info(
                f"Goal extraction observability: scanned={messages_scanned}, "
                f"corrections_skipped={corrections_skipped}, meta_skipped={meta_skipped}, "
                f"session_boundary={session_boundary_hit}, topic_shift={topic_shift_hit}, "
                f"intent={message_intent}"
            )
            return {
                "goal": previous_message_text,
                "message_intent": message_intent,
                "messages_scanned": messages_scanned,
                "corrections_skipped": corrections_skipped,
                "meta_skipped": meta_skipped,
                "session_boundary_hit": session_boundary_hit,
                "topic_shift_hit": topic_shift_hit,
                "scan_pattern": "found_substantive",
            }

        # No substantive message found
        logger.warning("No substantive user message found in transcript")
        return {
            "goal": "Unknown task",
            "message_intent": "instruction",  # Default for not found
            "messages_scanned": messages_scanned,
            "corrections_skipped": corrections_skipped,
            "meta_skipped": meta_skipped,
            "session_boundary_hit": session_boundary_hit,
            "topic_shift_hit": topic_shift_hit,
            "scan_pattern": "not_found",
        }

    except FileNotFoundError:
        logger.error(f"Transcript file not found: {transcript_path}")
        return {
            "goal": "Unknown task",
            "message_intent": "instruction",  # Default for file not found
            "messages_scanned": messages_scanned,
            "corrections_skipped": corrections_skipped,
            "meta_skipped": meta_skipped,
            "session_boundary_hit": False,
            "topic_shift_hit": False,
            "scan_pattern": "file_not_found",
        }
    except Exception as e:
        logger.error(f"Error extracting last substantive message: {e}")
        return {
            "goal": "Unknown task",
            "message_intent": "instruction",  # Default for error
            "messages_scanned": messages_scanned,
            "corrections_skipped": corrections_skipped,
            "meta_skipped": meta_skipped,
            "session_boundary_hit": False,
            "topic_shift_hit": False,
            "scan_pattern": "error",
        }


def extract_preceding_message(transcript_path: str | Path, goal: str) -> str | None:
    """Extract the message that immediately preceded a clarification request.

    When a user sends a clarification message (e.g., "what do you mean?"),
    this function finds the message that the user is asking for clarification about.
    This is typically the AI's response immediately before the user's clarification.

    Args:
        transcript_path: Path to transcript JSONL file
        goal: The clarification message text

    Returns:
        The preceding message text, or None if not found
    """
    transcript_path = Path(transcript_path)

    if not transcript_path.exists():
        logger.warning(f"Transcript file not found: {transcript_path}")
        return None

    try:
        parser = TranscriptParser(transcript_path)
        entries = parser._get_parsed_entries()
    except Exception as e:
        logger.error(f"Failed to parse transcript: {e}")
        return None

    goal_lower = goal.strip().lower()
    prev_message_text: str | None = None

    # Scan through transcript entries
    for entry in entries:
        # Extract message text from entry
        message_text = ""
        if "message" in entry:
            message = entry["message"]
            if isinstance(message, str):
                message_text = message
            elif isinstance(message, dict):
                content = message.get("content", [])
                if isinstance(content, str):
                    message_text = content
                elif isinstance(content, list):
                    text_parts = []
                    for item in content:
                        if isinstance(item, str):
                            text_parts.append(item)
                        elif isinstance(item, dict):
                            text_parts.append(item.get("text", ""))
                    message_text = " ".join(text_parts)

        message_text_lower = message_text.strip().lower()

        # If this entry matches the goal, return the previous message
        if message_text_lower == goal_lower:
            logger.debug(
                f"Found goal message, returning preceding: "
                f"'{prev_message_text[:50]}...' if prev else None"
            )
            return prev_message_text

        # Update prev_message_text for next iteration
        if message_text.strip():
            prev_message_text = message_text.strip()

    logger.debug(f"Goal message not found in transcript: '{goal[:50]}...'")
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
            logger.debug(
                f"[TranscriptLines] Could not read transcript for length calculation: {e}"
            )
            self._length = 0
            return 0

    def __len__(self) -> int:
        """Return total number of lines.

        Returns:
            Total line count.
        """
        return self._ensure_length()

    @overload
    def __getitem__(self, key: int) -> str: ...

    @overload
    def __getitem__(self, key: slice) -> list[str]: ...

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
            logger.warning(
                f"[TranscriptLines] Could not read range {start}:{stop}: {e}"
            )
            return []

        # Cache recent lines if this is a tail access
        if start >= length - 100:
            self._cache = result[-min(len(result), 100) :]

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
                yield from f
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
    # Maximum file size in bytes (50MB) - prevents OOM from large files (QUAL-006)
    # Increased from 10MB to 50MB to handle multi-hour sessions with tool-heavy workflows
    _MAX_FILE_SIZE = 50 * 1024 * 1024
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

    @staticmethod
    def _build_user_message_description(
        message: str, max_length: int = 200
    ) -> dict[str, Any]:
        """Build a user message description dict.

        Args:
            message: The user message text
            max_length: Maximum length for the description (default: 200)

        Returns:
            Dictionary with description, severity, and source
        """
        truncated = message[:max_length]
        ellipsis = "..." if len(message) > max_length else ""
        return {
            "description": f"User's last question: {truncated}{ellipsis}",
            "severity": "info",
            "source": "transcript",
        }

    @staticmethod
    def _is_substantial_user_message(text: str, min_length: int = 15) -> bool:
        """Check if text is a substantial user message (not meta tags).

        Args:
            text: The text to check
            min_length: Minimum content length (default: 15)

        Returns:
            True if text is a substantial user message, False otherwise
        """
        if not isinstance(text, str):
            return False

        text = text.strip()
        if len(text) < min_length:
            return False

        # Skip meta tags and system messages
        if text.startswith("<"):
            return False
        if text.startswith("This session is being continued"):
            return False
        if text.startswith("Stop hook feedback"):
            return False

        return True

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
            return

        try:
            with open(self.transcript_path, encoding="utf-8") as f:
                yield from f
        except (OSError, UnicodeDecodeError) as e:
            logger.warning(f"[TranscriptParser] Could not iterate transcript: {e}")
            return

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
                logger.info(
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
                logger.info(
                    f"[TranscriptParser] Warning: Reached maximum entry count ({self._MAX_ENTRIES}). "
                    f"Stopping parsing early to prevent hang (QUAL-006)."
                )
                break

            try:
                entry = json.loads(line)
                # Only add dict entries - skip numbers, strings, arrays
                if isinstance(entry, dict):
                    entries.append(entry)
                    entry_count += 1
                else:
                    logger.debug(
                        f"[TranscriptParser] Skipping non-dict JSON entry at line {entry_count}: {type(entry).__name__}"
                    )
            except json.JSONDecodeError as e:
                logger.debug(
                    f"[TranscriptParser] Skipping invalid JSON entry at line {entry_count}: {e}"
                )
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
        content_parts: list[str] = []

        def append_text(value: str) -> None:
            value = value.strip()
            if not value:
                return
            if (
                value.startswith("<")
                or value.startswith("This session is being continued")
                or value.startswith("Stop hook feedback")
            ):
                return
            content_parts.append(value)

        if isinstance(content, list):
            # Skip tool_result entries - they're not actual user questions
            # When content is a list with only tool_result items, the user is just
            # responding to a tool call, not providing a substantive task
            if len(content) > 0:
                first_item = content[0]
                if (
                    isinstance(first_item, dict)
                    and first_item.get("type") == "tool_result"
                ):
                    return ""

            # Handle list content (most common case)
            for item in content:
                if isinstance(item, str):
                    append_text(item)
                elif isinstance(item, dict):
                    item_type = item.get("type")
                    if item_type == "text" and isinstance(item.get("text"), str):
                        append_text(item["text"])
                    elif isinstance(item.get("content"), str):
                        append_text(item["content"])
        elif isinstance(content, str):
            # Handle string content (less common)
            append_text(content)

        return " ".join(content_parts).strip()

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
                    content_text = self._extract_text_from_entry(entry).strip()
                    if self._is_substantial_user_message(
                        content_text, self._MIN_CONTENT_LENGTH
                    ):
                        return self._build_user_message_description(content_text)
        except Exception as e:
            logger.error(f"[TranscriptParser] Could not read transcript: {e}")

        return None

    def extract_modifications(
        self, limit: int = _MAX_MODIFICATIONS
    ) -> list[dict[str, Any]]:
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
            logger.error(f"[TranscriptParser] Could not extract modifications: {e}")

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
                            "description": (
                                f"Open discussion: {msg[:200]}{'...' if len(msg) > 200 else ''}"
                            ),
                            "context_type": "open_discussion",
                            "original_message": msg[:500],
                        }

            # If no explicit patterns, check if last message was a question
            if recent_user_messages:
                last_msg = recent_user_messages[-1]
                if "?" in last_msg or any(
                    q in last_msg.lower()
                    for q in ["why", "how", "what", "when", "where", "which"]
                ):
                    return {
                        "description": (
                            f"User's last question: {last_msg[:200]}"
                            f"{'...' if len(last_msg) > 200 else ''}"
                        ),
                        "context_type": "question",
                        "original_message": last_msg[:500],
                    }

            return None

        except Exception as e:
            logger.error(
                f"[TranscriptParser] Could not extract conversation context: {e}"
            )
            return None

    def extract_session_decisions(
        self, task_name: str = "session"
    ) -> list[dict[str, Any]]:
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

                    from core.config import utcnow_iso

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
                            decision_entry["search_keys"] = structure_info[
                                "search_keys"
                            ][:5]

                    decisions.append(decision_entry)

                    if len(decisions) >= 7:  # Cap at 7 session decisions
                        break

        except Exception as e:
            logger.error(f"[TranscriptParser] Could not extract session decisions: {e}")

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
                            pattern_desc = content_lower[
                                pattern_start : pattern_start + 200
                            ]
                            patterns.append(pattern_desc.strip())
                            break

                if len(patterns) >= 5:  # Cap at 5 session patterns
                    break

        except Exception as e:
            logger.error(f"[TranscriptParser] Could not extract session patterns: {e}")

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
            logger.error(
                f"[TranscriptParser] Could not extract controversial decisions: {e}"
            )

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
                    if any(
                        img_tool in tool_name.lower()
                        for img_tool in [
                            "analyze_image",
                            "diagnose_error",
                            "extract_text",
                            "ui_to_artifact",
                            "screenshot",
                            "image",
                        ]
                    ):
                        # Get tool input/output for context
                        tool_input = entry.get("input", {})
                        tool_result = entry.get("result", {})

                        # Extract image path/prompt if available
                        image_source = (
                            tool_input.get("image_source")
                            or tool_input.get("imageSource")
                            or tool_input.get("file_path")
                        )
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
                            for next_entry in entries[
                                abs_idx + 1 : min(abs_idx + 5, len(entries))
                            ]:
                                if next_entry.get("type") == "user":
                                    user_response = self._extract_text_from_entry(
                                        next_entry
                                    )[:200]
                                    break

                        from core.config import utcnow_iso

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
                    visual_keywords = [
                        "screenshot",
                        "image",
                        "picture",
                        "see the",
                        "as shown",
                        "visual",
                        "ui mockup",
                    ]
                    if any(keyword in content_text for keyword in visual_keywords):
                        # Get full text for context
                        full_text = self._extract_text_from_entry(entry)
                        from core.config import utcnow_iso

                        return {
                            "description": f"User referenced visual content: {full_text[:200]}",
                            "type": "visual_reference",
                            "timestamp": entry.get("timestamp", utcnow_iso()),
                        }

        except Exception as e:
            logger.error(f"[TranscriptParser] Could not extract visual context: {e}")

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
                    user_message = self._extract_text_from_entry(entry).strip()
                    if len(user_message) > self._MIN_CONTENT_LENGTH:
                        return user_message
        except Exception as e:
            logger.error(f"[TranscriptParser] Could not extract last user message: {e}")

        return None

    def get_transcript_timestamp(self) -> str | None:
        """Extract timestamp from the last user message in transcript.

        Returns:
            ISO 8601 timestamp string from last user message, or None if:
            - Transcript unavailable
            - No user messages found
            - Timestamp field missing
        """
        entries = self._get_parsed_entries()
        if not entries:
            return None

        try:
            # Read backwards to find the last user message with timestamp
            for i in range(len(entries) - 1, -1, -1):
                entry = entries[i]
                if entry.get("type") == "user":
                    # Extract timestamp field if present
                    timestamp: str | None = entry.get("timestamp")
                    if timestamp and isinstance(timestamp, str):
                        return timestamp
                    # If no timestamp on this user message, continue searching
                    # (older user messages might have timestamps)
        except Exception as e:
            logger.error(f"[TranscriptParser] Could not extract timestamp: {e}")

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
            logger.warning(f"[TranscriptParser] Could not get transcript size: {e}")
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
            - Operations include: edit, test, read, investigation, command, skill
            - Investigation ops: review, analysis, debug tasks using Read/Grep/Glob tools
        """
        entries = self._get_parsed_entries()
        if not entries:
            return []

        pending_ops = []

        # Build set of completed tool IDs for completion detection
        # In the transcript, tool results appear as entries with type="tool" and the
        # same id as the corresponding tool_use entry
        completed_tool_ids: set[str] = set()
        for entry in entries:
            if entry.get("type") == "tool":
                tool_id = entry.get("id", "")
                if tool_id:
                    completed_tool_ids.add(tool_id)

        # First pass: Detect tool_use events inside assistant message content
        # Real transcript structure: {"type": "assistant", "message": {"content": [{"type": "tool_use", ...}]}}
        for i, entry in enumerate(entries):
            entry_type = entry.get("type", "")

            if entry_type != "assistant":
                continue

            # Extract content items from nested message structure
            msg_obj = entry.get("message", {})
            if not isinstance(msg_obj, dict):
                continue
            content_items = msg_obj.get("content", [])
            if not isinstance(content_items, list):
                continue

            for item in content_items:
                if not isinstance(item, dict):
                    continue
                if item.get("type") != "tool_use":
                    continue

                tool_name = item.get("name", "")
                input_data = item.get("input", {})
                tool_id = item.get("id", "")

                # Determine completion state by checking for corresponding tool result
                tool_state = "completed" if tool_id in completed_tool_ids else "in_progress"

                # Extract target from tool input
                target = "unknown"
                if tool_name == "Read":
                    target = input_data.get("file_path", "unknown")
                    op_type = "read"
                elif tool_name in ("Grep", "Glob"):
                    # Investigation tools
                    if tool_name == "Grep":
                        pattern = input_data.get("pattern", "")
                        target = f"search: {pattern[:50]}" if pattern else "grep search"
                    else:  # Glob
                        pattern = input_data.get("pattern", "")
                        target = f"files: {pattern[:50]}" if pattern else "glob search"
                    op_type = "investigation"
                elif tool_name == "Edit":
                    target = input_data.get("file_path", "unknown")
                    op_type = "edit"
                elif tool_name == "Bash":
                    command = input_data.get("command", "")
                    target = command[:80] if command else "bash command"
                    # Classify bash commands
                    if any(
                        word in command.lower()
                        for word in ["test", "pytest", "unittest"]
                    ):
                        op_type = "test"
                    else:
                        op_type = "command"
                elif tool_name == "Skill":
                    skill = input_data.get("skill", "")
                    target = f"skill: {skill}" if skill else "skill invocation"
                    op_type = "skill"
                else:
                    # Unknown tool - skip
                    continue

                pending_ops.append(
                    {
                        "type": op_type,
                        "target": target,
                        "state": tool_state,
                        "details": {"tool": tool_name, "input": str(input_data)[:200]},
                    }
                )

                # Limit to prevent excessive pending operations
                if len(pending_ops) >= 5:
                    break

            if len(pending_ops) >= 5:
                break

        # Second pass: Fallback to keyword detection in assistant text (if no tools found)
        if not pending_ops:
            for entry in entries:
                entry_type = entry.get("type", "")

                if entry_type == "assistant":
                    # Handle both message.content format and direct content field
                    msg_obj = entry.get("message", {})
                    if isinstance(msg_obj, dict) and msg_obj.get("content"):
                        content = msg_obj.get("content", "")
                    else:
                        # Direct content field (actual transcript format)
                        content = entry.get("content", "")

                    # Convert content to string before calling .lower()
                    # Content can be str | list[Any] per MessageDict TypedDict
                    if isinstance(content, list):
                        # Join list content items (text blocks)
                        content = " ".join(
                            item for item in content if isinstance(item, str)
                        )
                    elif not isinstance(content, str):
                        content = str(content) if content else ""

                    content = content.lower()

                    # Enhanced keyword detection including review/analysis patterns
                    # Operation keywords
                    operation_keywords = {
                        "edit": [
                            "editing",
                            "editing file",
                            "modify",
                            "write",
                            "change",
                        ],
                        "test": ["running test", "test", "pytest", "unittest"],
                        "investigation": [
                            "review",
                            "analyze",
                            "investigate",
                            "examine",
                            "search",
                            "check",
                            "debug",
                        ],
                        "command": ["executing", "processing", "run"],
                    }

                    detected_type = None
                    for op_type, keywords in operation_keywords.items():
                        if any(keyword in content for keyword in keywords):
                            detected_type = op_type
                            break

                    if detected_type:
                        # Try to extract target from context
                        target = "unknown"
                        if "file" in content:
                            # Simple file path extraction
                            words = content.split()
                            for word in words:
                                if "." in word and "/" in word:
                                    target = word.strip('".')
                                    break

                        pending_ops.append(
                            {
                                "type": detected_type,
                                "target": target,
                                "state": "in_progress",
                                "details": {"context": content[:200]},
                            }
                        )

                        # Limit to prevent excessive pending operations
                        if len(pending_ops) >= 5:
                            break

        return pending_ops

    def extract_skill_invocations(self) -> list[dict[str, Any]]:
        """Extract Skill tool invocations from transcript.

        Parses transcript for Skill tool_use entries and extracts:
        - skill_name: Name of the skill invoked (e.g., "package", "research")
        - args: Arguments passed to the skill
        - timestamp: When the skill was invoked
        - context: Brief description of what the skill was doing

        Returns:
            List of skill invocation dicts with skill_name, args, timestamp, context
        """
        skill_invocations: list[dict[str, Any]] = []

        entries = self._get_parsed_entries()
        if not entries:
            return skill_invocations

        try:
            # Scan transcript for Skill tool_use entries
            for entry in entries:
                if entry.get("type") == "tool_use" and entry.get("name") == "Skill":
                    input_data = entry.get("input", {})
                    if not input_data:
                        continue

                    skill_name = input_data.get("skill")
                    args = input_data.get("args", "")
                    timestamp = entry.get("timestamp", "")

                    # Only add if we have the skill name
                    if skill_name:
                        # Build context from surrounding conversation
                        context = self._extract_skill_context(entry, entries)

                        skill_invocations.append(
                            {
                                "skill_name": skill_name,
                                "args": args[:200] if args else "",  # Limit args length
                                "timestamp": timestamp,
                                "context": context,
                            }
                        )

        except Exception as e:
            logger.error(f"[TranscriptParser] Could not extract skill invocations: {e}")

        return skill_invocations

    def _extract_skill_context(self, skill_entry: dict, all_entries: list[dict]) -> str:
        """Extract context for a skill invocation from surrounding conversation.

        Args:
            skill_entry: The tool_use entry for the Skill invocation
            all_entries: All transcript entries to search for context

        Returns:
            Context description string
        """
        try:
            # Find the position of the skill entry
            skill_index = -1
            for i, entry in enumerate(all_entries):
                if entry == skill_entry:
                    skill_index = i
                    break

            if skill_index == -1:
                return ""

            # Look backward for the user message that triggered this skill
            for i in range(skill_index - 1, max(-1, skill_index - 10), -1):
                entry = all_entries[i]
                if entry.get("type") == "user":
                    content_text = self._extract_text_from_entry(entry)
                    if content_text:
                        # Return first 150 chars as context
                        return content_text[:150].strip()

        except Exception as e:
            logger.warning(f"[TranscriptParser] Could not extract skill context: {e}")

        return ""

    def extract_last_skill_output(self, max_length: int = 500) -> dict[str, Any] | None:
        """Extract the assistant's output after the most recent Skill invocation.

        When a user invokes a skill (e.g., /gto), the transcript contains:
        1. User message with skill invocation
        2. Skill tool_use entry
        3. Assistant's response (the skill output)

        This method extracts #3 (the assistant's response after the skill).

        Args:
            max_length: Maximum length of the output text to return

        Returns:
            Dict with skill_name, output text, and timestamp, or None if not found
        """
        entries = self._get_parsed_entries()
        if not entries:
            return None

        try:
            # Find the most recent Skill tool_use entry
            last_skill_index = -1
            skill_name = None

            for i in range(len(entries) - 1, -1, -1):
                entry = entries[i]
                if entry.get("type") == "tool_use" and entry.get("name") == "Skill":
                    input_data = entry.get("input", {})
                    skill_name = input_data.get("skill", "unknown")
                    last_skill_index = i
                    break

            if last_skill_index == -1:
                return None

            # Look for the assistant's response after the skill invocation
            for i in range(last_skill_index + 1, len(entries)):
                entry = entries[i]
                if entry.get("type") == "assistant":
                    output_text = self._extract_text_from_entry(entry).strip()
                    if output_text and len(output_text) >= 20:
                        return {
                            "skill_name": skill_name,
                            "output": output_text[:max_length],
                            "timestamp": entry.get("timestamp", ""),
                            "full_output_available": len(output_text) > max_length,
                        }

            return None

        except Exception as e:
            logger.warning(f"[TranscriptParser] Could not extract skill output: {e}")
            return None


if __name__ == "__main__":
    # Direct test block for manual testing
    import sys

    # Usage: python transcript.py <path_to_transcript.json>
    if len(sys.argv) > 1:
        test_path = sys.argv[1]
        parser = TranscriptParser(test_path)

        logger.info("=== Testing TranscriptLines ===")
        lines = TranscriptLines(test_path)
        logger.info(f"Total lines: {len(lines)}")
        if len(lines) > 0:
            logger.info(f"First line: {lines[0][:100]}")
        if len(lines) > 1:
            logger.info(f"Last line: {lines[-1][:100]}")

        logger.info("\n=== Testing TranscriptParser ===")
        blocker = parser.extract_current_blocker()
        logger.info(f"Current blocker: {blocker}")

        mods = parser.extract_modifications()
        logger.info(f"Modifications: {len(mods)} found")

        decisions = parser.extract_session_decisions()
        logger.info(f"Session decisions: {len(decisions)} found")

        patterns = parser.extract_session_patterns()
        logger.info(f"Session patterns: {len(patterns)} found")

        controversial = parser.extract_controversial_decisions()
        logger.info(f"Controversial decisions: {len(controversial)} found")
    else:
        logger.info("Usage: python transcript.py <path_to_transcript.json>")


def extract_user_message_from_blocker(blocker: BlockerDef | str | None) -> str | None:
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


def filter_valid_messages(messages: list[MessageDict]) -> list[MessageDict]:
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


def extract_transcript_from_messages(messages: list[MessageDict]) -> str:
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

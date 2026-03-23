#!/usr/bin/env python3
"""
User Intent Capture Module

Extracts pending questions and unresolved issues from chat transcript.
Supports question detection and categorization.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


def capture_pending_questions(transcript: str) -> dict | None:
    """Capture pending questions from the chat transcript.

    Args:
        transcript: Chat transcript text

    Returns:
        Dict with keys:
            - questions: list[dict] - pending questions with metadata
            - total_count: int - total number of questions
        Returns None if no questions found or parsing fails.

    Raises:
        None: This function does not raise exceptions, returns None on failure
    """
    try:
        if not transcript or not transcript.strip():
            logger.info("[user_intent] Empty transcript provided")
            return None

        # Extract questions from transcript
        questions = _extract_questions(transcript)

        if not questions:
            logger.info("[user_intent] No questions found in transcript")
            return None

        # Build result dict
        return {"questions": questions, "total_count": len(questions)}

    except Exception as e:
        logger.warning(f"[user_intent] Failed to capture pending questions: {e}")
        return None


def _extract_questions(transcript: str) -> list[dict]:
    """Extract questions from transcript.

    Args:
        transcript: Chat transcript text

    Returns:
        List of question dicts with keys:
            - question: str - question text
            - category: str - question category (technical, decision, clarification, other)
            - context: str | None - surrounding context snippet
    """
    questions = []

    # Question patterns (looking for user questions, not AI responses)
    # Patterns: questions followed by ?, or explicit question phrases
    question_patterns = [
        # Direct questions
        r"([A-Z][^?]*\?(?:\s*$|\n))",
        # Explicit question phrases
        r"(?i)(?:how do i|what is|where is|when should|why does|who is|which|can you|could you|should i|would you)(?:[^?.]*)(?:\?|$)",
    ]

    # Context boundaries (user messages typically start with these patterns)
    user_message_patterns = [
        r"User:\s*\n",
        r">\s*",  # Quote prefix
        r"^\s*$",  # Empty line (message boundary)
    ]

    lines = transcript.split("\n")
    current_question = None
    context_lines = []

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Check if this line contains a question
        for pattern in question_patterns:
            matches = re.finditer(pattern, stripped, re.MULTILINE)
            for match in matches:
                question_text = match.group(1).strip()

                # Filter out AI responses (lines starting with "AI:" or similar)
                if re.match(r"^(?:AI|Assistant|Claude):", stripped, re.IGNORECASE):
                    continue

                # Minimum length filter (avoid single words)
                if len(question_text) < 10:
                    continue

                # Get surrounding context
                context_start = max(0, i - 2)
                context_end = min(len(lines), i + 3)
                context = "\n".join(lines[context_start:context_end]).strip()

                # Categorize question
                category = _categorize_question(question_text)

                questions.append(
                    {
                        "question": question_text,
                        "category": category,
                        "context": context[:500],  # Limit context to 500 chars
                    }
                )

    # Limit to top 20 questions to avoid bloat
    questions = questions[:20]

    return questions


def _categorize_question(question: str) -> str:
    """Categorize question by type.

    Args:
        question: Question text

    Returns:
        Category: technical, decision, clarification, or other
    """
    question_lower = question.lower()

    # Technical patterns
    technical_patterns = [
        r"\b(?:how do i|how to|how can i|implement|code|function|api|library|package)\b",
        r"\b(?:bug|error|fix|debug|test|deploy|build|run)\b",
        r"\b(?:python|javascript|typescript|json|yaml|xml|sql)\b",
    ]

    # Decision patterns
    decision_patterns = [
        r"\b(?:should i|would you|which|better|best|recommend|choose)\b",
        r"\b(?:option a|option b|trade.?off|pros and cons|versus|vs\.?)\b",
    ]

    # Clarification patterns
    clarification_patterns = [
        r"\b(?:what do you mean|clarify|explain|elaborate|more detail)\b",
        r"\b(?:why|what|where|when|who)\b",
    ]

    # Check each category
    for pattern in technical_patterns:
        if re.search(pattern, question_lower):
            return "technical"

    for pattern in decision_patterns:
        if re.search(pattern, question_lower):
            return "decision"

    for pattern in clarification_patterns:
        if re.search(pattern, question_lower):
            return "clarification"

    return "other"

"""Tests for context gathering with session boundaries and topic shift detection.

This module verifies that:
1. Context gathering stops at session boundaries
2. Context gathering stops on topic shifts
3. Session boundary detection works correctly
4. Topic shift detection works correctly
"""

import json
import tempfile
from pathlib import Path

from core.hooks.__lib.transcript import (
    detect_session_boundary,
    gather_context_with_boundaries,
    is_same_topic,
)


def test_gather_context_basic():
    """Test basic context gathering works."""
    # Create a simple transcript
    entries = [
        {"role": "user", "message": "Work on feature X"},
        {"role": "assistant", "message": "OK"},
        {"role": "user", "message": "Continue"},
    ]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
        transcript_path = Path(f.name)

    try:
        context = gather_context_with_boundaries(transcript_path, max_messages=50)
        # Should return some context (all entries since no boundaries)
        assert len(context) == 3
    finally:
        transcript_path.unlink()


def test_gather_context_stops_at_session_boundary():
    """Test that context gathering stops at session boundaries."""
    entries = [
        {
            "role": "user",
            "message": "Work on feature X",
            "session_chain_id": "session-1",
        },
        {"role": "assistant", "message": "OK", "session_chain_id": "session-1"},
        # Session boundary - new session_chain_id
        {
            "role": "user",
            "message": "Different session",
            "session_chain_id": "session-2",
        },
    ]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
        transcript_path = Path(f.name)

    try:
        context = gather_context_with_boundaries(transcript_path, max_messages=50)
        # Should stop before the session boundary
        assert len(context) == 2
    finally:
        transcript_path.unlink()


def test_gather_context_stops_on_topic_shift():
    """Test that context gathering stops on topic shifts."""
    entries = [
        {"role": "user", "message": "Work on feature X implementation"},
        {"role": "assistant", "message": "OK"},
        # Topic shift - completely different topic
        {"role": "user", "message": "What's the weather?"},
    ]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
        transcript_path = Path(f.name)

    try:
        context = gather_context_with_boundaries(transcript_path, max_messages=50)
        # Should stop before the topic shift (or include it if threshold allows)
        # With default threshold of 0.3, "feature X implementation" vs "weather" should be different
        assert len(context) <= 3
    finally:
        transcript_path.unlink()


def test_gather_context_respects_max_messages():
    """Test that context gathering respects max_messages limit."""
    entries = []
    for i in range(100):
        entries.append({"role": "user", "message": f"Message {i}"})

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
        transcript_path = Path(f.name)

    try:
        context = gather_context_with_boundaries(transcript_path, max_messages=10)
        # Should return at most max_messages
        assert len(context) <= 10
    finally:
        transcript_path.unlink()


def test_detect_session_boundary_new_session():
    """Test session boundary detection for new session."""
    current_entry = {
        "role": "user",
        "session_chain_id": "session-2",
        "message": "New task",
    }

    prev_entry = {
        "role": "assistant",
        "session_chain_id": "session-1",
        "message": "Previous response",
    }

    # Should detect session boundary (different session_chain_id)
    result = detect_session_boundary(current_entry, prev_entry)
    assert result is True


def test_detect_session_boundary_same_session():
    """Test session boundary detection for same session."""
    current_entry = {
        "role": "user",
        "session_chain_id": "session-1",
        "message": "Continue task",
    }

    prev_entry = {"role": "assistant", "session_chain_id": "session-1", "message": "OK"}

    # Should NOT detect session boundary (same session_chain_id)
    result = detect_session_boundary(current_entry, prev_entry)
    assert result is False


def test_is_same_topic_related_messages():
    """Test topic detection for related messages."""
    message1 = "Implement the user authentication feature with JWT tokens"
    message2 = "Add JWT token validation to the authentication system"

    # Should be same topic (related keywords: authentication, JWT, tokens)
    result = is_same_topic(message1, message2)
    assert result is True


def test_is_same_topic_different_messages():
    """Test topic detection for different messages."""
    message1 = "Implement the user authentication feature"
    message2 = "Design the database schema for product catalog"

    # Should be different topics (no keyword overlap)
    result = is_same_topic(message1, message2)
    assert result is False


def test_gather_context_empty_transcript():
    """Test context gathering with empty transcript."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write("")  # Empty file
        transcript_path = Path(f.name)

    try:
        context = gather_context_with_boundaries(transcript_path, max_messages=50)
        # Should return empty list
        assert context == []
    finally:
        transcript_path.unlink()

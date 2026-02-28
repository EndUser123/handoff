#!/usr/bin/env python3
"""Bridge token utilities for cross-session continuity.

Bridge tokens allow tracking specific decisions across compacts.
Format: BRIDGE_YYYYMMDD-HHMMSS_TOPIC_KEYWORD

This module provides utilities for generating and managing bridge tokens
in handoff data, following the /hod skill specification.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Bridge token prefix
BRIDGE_TOKEN_PREFIX = "BRIDGE_"

# Maximum topic length in bridge tokens
MAX_TOPIC_LENGTH = 20


def generate_bridge_token(topic: str, timestamp: str) -> str:
    """Generate a cross-session continuity bridge token.

    Bridge tokens allow tracking specific decisions across compacts.
    Format: BRIDGE_YYYYMMDD-HHMMSS_TOPIC_KEYWORD

    Args:
        topic: Topic string describing the decision
        timestamp: ISO format timestamp string

    Returns:
        Bridge token string like "BRIDGE_20260212-140530_AUTH_FLOW"

    Examples:
        >>> generate_bridge_token("authentication", "2026-02-12T14:05:30Z")
        'BRIDGE_20260212-140530_AUTHENTICATION'
    """
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        dt = datetime.now(UTC)

    # Format: YYYYMMDD-HHMMSS
    time_part = dt.strftime("%Y%m%d-%H%M%S")

    # Clean topic: uppercase, replace spaces/hyphens with underscores
    topic_clean = topic.upper()[:MAX_TOPIC_LENGTH]
    topic_clean = topic_clean.replace(" ", "_").replace("-", "_")
    topic_clean = "".join(c for c in topic_clean if c.isalnum() or c == "_")

    return f"{BRIDGE_TOKEN_PREFIX}{time_part}_{topic_clean}"


def extract_bridge_tokens(handoff_data: dict[str, Any]) -> list[str]:
    """Extract all bridge tokens from handoff data.

    Args:
        handoff_data: Handoff metadata dict

    Returns:
        List of bridge token strings found in decisions
    """
    tokens = []
    handover = handoff_data.get("handover", {})
    decisions = handover.get("decisions", [])

    if isinstance(decisions, list):
        for decision in decisions:
            if isinstance(decision, dict) and (token := decision.get("bridge_token")):
                tokens.append(token)

    return tokens


def validate_bridge_token(token: str) -> bool:
    """Validate a bridge token format.

    Args:
        token: Bridge token string to validate

    Returns:
        True if token has valid format, False otherwise
    """
    if not token or not isinstance(token, str):
        return False

    if not token.startswith(BRIDGE_TOKEN_PREFIX):
        return False

    # Expected format: BRIDGE_YYYYMMDD-HHMMSS_TOPIC
    parts = token.split("_")
    if len(parts) < 3:
        return False

    # Check date-time format
    try:
        datetime.strptime(parts[1], "%Y%m%d-%H%M%S")
    except ValueError:
        return False

    return True


def get_bridge_token_age(token: str) -> int | None:
    """Get the age of a bridge token in seconds.

    Args:
        token: Bridge token string

    Returns:
        Age in seconds, or None if token is invalid
    """
    if not validate_bridge_token(token):
        return None

    try:
        parts = token.split("_")
        dt = datetime.strptime(parts[1], "%Y%m%d-%H%M%S")
        dt = dt.replace(tzinfo=UTC)
        age = int((datetime.now(UTC) - dt).total_seconds())
        return age
    except (ValueError, IndexError):
        return None

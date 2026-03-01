"""Handover data builder for handoff captures.

This module provides the HandoverBuilder class which generates handover data
from session context including decisions, patterns, and objectives.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..PreCompact_handoff_capture import TranscriptParser

from handoff.hooks.__lib.transcript import (
    detect_structure_type,
    extract_topic_from_content,
)


class HandoverBuilder:
    """Build handover data from session context.

    Handles generation of handover data including:
    - Session decisions from transcript
    - Session patterns from transcript
    - Controversial decisions (verbatim quotes)
    - Session objectives from files
    - Topic extraction and structure detection

    Note: extract_topic_from_content and detect_structure_type are imported
    from transcript module to avoid duplication.
    """

    # Use module-level functions from transcript module
    extract_topic_from_content = extract_topic_from_content
    detect_structure_type = detect_structure_type

    def __init__(self, project_root: Path, transcript_parser: TranscriptParser):
        """Initialize handover builder.

        Args:
            project_root: Path to the project root directory
            transcript_parser: TranscriptParser instance for extracting session data
        """
        self.project_root = project_root
        self.parser = transcript_parser

    def build(self, task_name: str) -> dict[str, Any]:
        """Generate handover data from session and CKS context.

        Extracts:
        - Session decisions: Decisions made during THIS SESSION (from transcript)
        - Session patterns: Patterns discovered during THIS SESSION (from transcript)
        - Controversial decisions: Backtracking/reconsideration (verbatim quotes)
        - Objectives: Session goals from files

        Args:
            task_name: Name of the current task

        Returns:
            Handover dict with decisions, patterns, objectives
        """
        handover: dict[str, list[str] | list[dict[str, Any]]] = {
            "decisions": [],
            "patterns_learned": [],
            "controversial_decisions": [],
            "session_objectives": [],
        }

        try:
            # PRIORITY 1: Extract SESSION-SPECIFIC decisions (from transcript)
            session_decisions = self.parser.extract_session_decisions(task_name)
            if session_decisions:
                handover["decisions"] = session_decisions
                logger.info(f"[HandoverBuilder] Found {len(session_decisions)} session decisions")

            # PRIORITY 2: Extract SESSION-SPECIFIC patterns (from transcript)
            session_patterns = self.parser.extract_session_patterns()
            if session_patterns:
                handover["patterns_learned"] = session_patterns
                logger.info(f"[HandoverBuilder] Found {len(session_patterns)} session patterns")

            # PRIORITY 3: Extract CONTROVERSIAL decisions (verbatim quotes)
            controversial_decisions = self.parser.extract_controversial_decisions()
            if controversial_decisions:
                handover["controversial_decisions"] = controversial_decisions
                logger.info(
                    f"[HandoverBuilder] Found {len(controversial_decisions)} controversial decisions"
                )

            # Extract session objectives if available
            objectives_file = self.project_root / ".claude" / "objectives.txt"
            if objectives_file.exists():
                for line in objectives_file.read_text().split("\n")[:5]:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        # Store as string for consistency with other fields
                        handover["session_objectives"].append(line[:100])

        except Exception as e:
            logger.error(f"[HandoverBuilder] Handover generation failed: {e}")

        return handover

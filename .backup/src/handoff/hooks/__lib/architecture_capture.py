#!/usr/bin/env python3
"""
Architectural Context Capture Module

Extracts architectural assumptions and constraints from ADR docs.
Supports common ADR locations and formats.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def capture_architectural_context(project_root: Path) -> dict | None:
    """Capture architectural context from the project.

    Args:
        project_root: Path to the project root directory

    Returns:
        Dict with keys:
            - assumptions: list[str] - architectural assumptions
            - constraints: list[str] - design constraints
            - adr_files: list[str] - paths to ADR files found
        Returns None if no ADRs found or parsing fails.

    Raises:
        subprocess.TimeoutExpired: If file discovery exceeds 2s timeout
    """
    try:
        # Find ADR files first
        adr_files = _find_adr_files(project_root)
        if not adr_files:
            logger.info(f"[architecture_capture] No ADR files found in {project_root}")
            return None

        # Extract assumptions and constraints
        assumptions, constraints = _parse_adr_files(project_root, adr_files)

        if not assumptions and not constraints:
            logger.info("[architecture_capture] No assumptions/constraints found in ADRs")
            return None

        # Build result dict
        return {
            "assumptions": assumptions,
            "constraints": constraints,
            "adr_files": adr_files
        }

    except Exception as e:
        logger.warning(f"[architecture_capture] Failed to capture architectural context: {e}")
        return None


def _find_adr_files(project_root: Path) -> list[str]:
    """Find ADR files in the project.

    Args:
        project_root: Path to the project root directory

    Returns:
        List of ADR file paths relative to project_root.
        Returns empty list if no ADRs found.
    """
    adr_files = []

    # Common ADR directories and patterns
    adr_patterns = [
        "doc/adr/*.md",
        "docs/adr/*.md",
        "docs/adr/**/*.md",
        "docs/architecture/*.md",
        "docs/architecture-decisions/*.md",
        "adr/*.md",
        ".adr/*.md",
        "decision-records/*.md",
        "docs/decisions/*.md",
    ]

    try:
        # Use glob to find ADR files
        for pattern in adr_patterns:
            full_path = project_root / pattern
            matches = list(full_path.parent.glob(pattern.split('/')[-1]))
            for match in matches:
                if match.is_file() and match.suffix == '.md':
                    # Get relative path
                    rel_path = str(match.relative_to(project_root))
                    adr_files.append(rel_path)

        # Remove duplicates and sort
        adr_files = sorted(set(adr_files))

        # Limit to top 20 ADR files to avoid bloat
        if len(adr_files) > 20:
            adr_files = adr_files[:20]

    except (OSError, ValueError) as e:
        logger.warning(f"[architecture_capture] ADR file discovery failed: {e}")

    return adr_files


def _parse_adr_files(project_root: Path, adr_files: list[str]) -> tuple[list[str], list[str]]:
    """Parse assumptions and constraints from ADR files.

    Args:
        project_root: Path to the project root directory
        adr_files: List of ADR file paths

    Returns:
        Tuple of (assumptions list, constraints list)
    """
    assumptions = []
    constraints = []

    # Patterns to extract assumptions
    assumption_patterns = [
        r'(?i)(?:we\s+assume|assumption|assumptions?:)\s*[:\-]?\s*(.+?)(?:\.|$)',
        r'(?i)(?:given\s+that|assuming)\s+[:\-]?\s*(.+?)(?:\.|$)',
    ]

    # Patterns to extract constraints
    constraint_patterns = [
        r'(?i)(?:constraint|constraints?:)\s*[:\-]?\s*(.+?)(?:\.|$)',
        r'(?i)(?:must\s+not?|cannot|unable\s+to)\s+[:\-]?\s*(.+?)(?:\.|$)',
        r'(?i)(?:limited\s+by|restricted\s+to)\s+[:\-]?\s*(.+?)(?:\.|$)',
    ]

    for adr_file in adr_files[:10]:  # Limit to first 10 ADRs
        adr_path = project_root / adr_file
        if not adr_path.exists():
            continue

        try:
            with open(adr_path, encoding='utf-8', errors='ignore') as f:
                content = f.read()

            # Extract assumptions
            for pattern in assumption_patterns:
                matches = re.findall(pattern, content, re.MULTILINE)
                for match in matches:
                    # Clean up the match
                    assumption = _clean_extracted_text(match)
                    if assumption and len(assumption) > 10:  # Minimum length filter
                        assumptions.append(assumption)

            # Extract constraints
            for pattern in constraint_patterns:
                matches = re.findall(pattern, content, re.MULTILINE)
                for match in matches:
                    # Clean up the match
                    constraint = _clean_extracted_text(match)
                    if constraint and len(constraint) > 10:  # Minimum length filter
                        constraints.append(constraint)

        except (OSError, UnicodeDecodeError) as e:
            logger.warning(f"[architecture_capture] Failed to read ADR file {adr_file}: {e}")
            continue

    # Limit results to avoid bloat
    assumptions = assumptions[:20]
    constraints = constraints[:20]

    return assumptions, constraints


def _clean_extracted_text(text: str) -> str:
    """Clean extracted text by removing extra whitespace and markdown.

    Args:
        text: Raw extracted text

    Returns:
        Cleaned text string
    """
    # Remove markdown formatting
    text = re.sub(r'[*_`#]', '', text)
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    # Strip leading/trailing whitespace
    text = text.strip()
    return text

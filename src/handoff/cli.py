#!/usr/bin/env python3
"""
HOD - Enhanced Session Continuity and Handover System

CLI wrapper for the handoff package. Provides manual invocation modes
while leveraging automatic PreCompact hooks.

This module provides the /hod skill functionality as a package CLI entry point.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Import handoff package components
try:
    from handoff.hooks.__lib.bridge_tokens import (
        BRIDGE_TOKEN_PREFIX,
        extract_bridge_tokens,
        generate_bridge_token,
    )
    from handoff.hooks.__lib.handoff_store import (
        HandoffStore,
        calculate_quality_score,
        enrich_handoff_with_bridge_tokens,
        get_quality_rating,
    )
    from handoff.hooks.__lib.handover import HandoverBuilder
    from handoff.hooks.__lib.transcript import TranscriptParser
except ImportError as e:
    print(f"Error: handoff package dependencies not available: {e}", file=sys.stderr)
    print("This is part of the handoff package. Ensure installation is correct.", file=sys.stderr)
    sys.exit(1)


def expand_bridge_token(decision: dict[str, Any]) -> str:
    """Expand a bridge token into a human-readable context string.

    For external LLM handoffs, replaces compact tokens with full context
    including timestamp, topic, and decision text.

    Args:
        decision: Decision dict with bridge_token, timestamp, topic, decision

    Returns:
        Expanded context string
    """
    token = decision.get("bridge_token", "")
    if not token:
        return decision.get("decision", "")

    # Parse token: BRIDGE_YYYYMMDD-HHMMSS_TOPIC
    parts = token.split("_")
    if len(parts) < 3:
        return decision.get("decision", "")

    try:
        # Extract timestamp from token
        dt = datetime.strptime(parts[1], "%Y%m%d-%H%M%S")
        dt = dt.replace(tzinfo=UTC)
        formatted_time = dt.strftime("%Y-%m-%d at %H:%M")

        # Extract topic
        topic = decision.get("topic", "Unknown")

        # Get decision text (full, not truncated)
        decision_text = decision.get("decision", "")

        return f"Decision made on {formatted_time} ({topic}):\n\n{decision_text}\n\n[Reference: {token}]"
    except (ValueError, IndexError):
        return decision.get("decision", "")


def expand_all_bridge_tokens(handoff_data: dict[str, Any]) -> dict[str, Any]:
    """Replace bridge tokens with expanded context in handoff data.

    Creates a version suitable for external LLMs that don't have
    access to local session history.

    Args:
        handoff_data: Original handoff data

    Returns:
        Handoff data with expanded bridge token context
    """
    # Create a copy to avoid mutating original
    expanded = handoff_data.copy()

    if "handover" not in expanded:
        return expanded

    handover = expanded["handover"].copy()
    if "decisions" not in handover:
        expanded["handover"] = handover
        return expanded

    # Expand each decision
    expanded_decisions = []
    for decision in handover["decisions"]:
        expanded_decision = decision.copy()

        if "bridge_token" in decision:
            # Add expanded context field
            expanded_decision["expanded_context"] = expand_bridge_token(decision)

        expanded_decisions.append(expanded_decision)

    handover["decisions"] = expanded_decisions
    expanded["handover"] = handover

    return expanded


def format_llm_prompt(handoff_data: dict[str, Any], expand_tokens: bool = True) -> str:
    """Format handoff data as an LLM-ready prompt for pasting into another LLM.

    Args:
        handoff_data: Handoff data dictionary
        expand_tokens: Whether to expand bridge tokens with full context (default: True)

    Returns:
        LLM-ready prompt string
    """
    # Expand bridge tokens by default for external LLMs
    if expand_tokens:
        handoff_data = expand_all_bridge_tokens(handoff_data)

    bridge_tokens = extract_bridge_tokens(handoff_data)

    lines = [
        "# Session Handoff from Claude Code",
        "",
        "You are receiving context from another LLM session. Below is the complete handoff data.",
        "",
        "## Quick Summary",
    ]

    # Basic info
    lines.append(f"- **Session**: {handoff_data.get('session_id', 'Unknown')}")
    lines.append(f"- **Timestamp**: {handoff_data.get('timestamp', 'Unknown')}")
    lines.append(f"- **Quality Score**: {handoff_data.get('quality_score', 0):.2f}/1.00 ({handoff_data.get('quality_rating', 'Unknown')})")

    # Blocker
    if blocker := handoff_data.get('blocker'):
        lines.append(f"- **Current Blocker**: {blocker.get('description', 'None')[:100]}...")

    # Bridge tokens
    if bridge_tokens:
        lines.append(f"- **Bridge Tokens**: {', '.join(bridge_tokens)}")

    lines.append("")

    # Last work
    if modifications := handoff_data.get('modifications'):
        lines.append("## Recent Work")
        for mod in modifications[-5:]:
            if file_path := mod.get('file'):
                lines.append(f"- Modified: `{file_path}`")
        lines.append("")

    # Next steps
    if next_steps := handoff_data.get('next_steps'):
        lines.append("## Next Steps")
        for i, step in enumerate(next_steps[:5], 1):
            lines.append(f"{i}. {step}")
        lines.append("")

    # Key decisions with expanded context
    if handover := handoff_data.get('handover', {}):
        if decisions := handover.get('decisions', []):
            lines.append("## Key Decisions")
            for decision in decisions[:5]:
                topic = decision.get('topic', 'Unknown')

                # Use expanded context if available, otherwise use truncated decision
                if expand_tokens and (expanded := decision.get('expanded_context')):
                    lines.append(f"### {topic}")
                    lines.append(expanded)
                else:
                    bridge_token = decision.get('bridge_token', '')
                    decision_text = decision.get('decision', '')[:150]
                    lines.append(f"### {topic}")
                    if bridge_token:
                        lines.append(f"**Bridge Token**: `{bridge_token}`")
                    lines.append(f"{decision_text}...")
                lines.append("")

    # Full JSON data
    lines.append("---")
    lines.append("")
    lines.append("## Complete Handoff JSON")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(handoff_data, indent=2, default=str))
    lines.append("```")
    lines.append("")

    # Instructions for receiving LLM
    lines.append("## Instructions for Continuing")
    lines.append("")
    lines.append("1. Review the quick summary above")
    lines.append("2. Check bridge tokens - respect decisions marked with them")
    lines.append("3. Note the quality score - if low, ask what needs documentation")
    lines.append("4. Continue based on next_steps or user's new request")

    return "\n".join(lines)


def detect_terminal_id() -> str:
    """Detect terminal ID for session isolation."""
    # Try environment variables first
    if terminal_id := os.environ.get("CLAUDE_TERMINAL_ID"):
        return terminal_id

    # Try session ID
    if session_id := os.environ.get("CLAUDE_SESSION_ID"):
        return session_id

    # Fallback to PID-based
    return f"term_{os.getpid()}"


def find_transcript_path(project_root: Path) -> str | None:
    """Find the most recent session-specific transcript.

    Args:
        project_root: Project root directory

    Returns:
        Path to transcript file, or None if not found
    """
    project_conversations_dir = os.path.expanduser("~/.claude/projects/P--/")
    if not os.path.exists(project_conversations_dir):
        return None

    import glob
    session_files = glob.glob(os.path.join(project_conversations_dir, "*.jsonl"))
    if not session_files:
        return None

    # Sort by modification time, get most recent
    session_files.sort(key=lambda f: os.path.getmtime(f), reverse=True)

    # Skip obviously wrong files
    for f in session_files[:5]:
        size_mb = os.path.getsize(f) / (1024 * 1024)
        if size_mb > 50 or "subagent" in f.lower():
            continue
        return f

    return None


def generate_handoff(
    project_root: Path,
    mode: str = "detailed",
) -> dict[str, Any]:
    """Generate handoff document.

    Args:
        project_root: Project root directory
        mode: Output mode - "summary", "detailed", or "quality"

    Returns:
        Handoff data dictionary
    """
    terminal_id = detect_terminal_id()
    transcript_path = find_transcript_path(project_root)

    # Initialize components
    parser = TranscriptParser(transcript_path=transcript_path)
    handover_builder = HandoverBuilder(
        project_root=project_root, transcript_parser=parser
    )
    handoff_store = HandoffStore(
        project_root=project_root, terminal_id=terminal_id
    )

    # Generate task name from timestamp
    task_name = f"manual_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"

    # Extract data using parser
    blocker = parser.extract_current_blocker()
    modifications = parser.extract_modifications()
    open_context = parser.extract_open_conversation_context()

    # Extract next steps from next-steps file
    next_steps_file = project_root / ".claude" / "next-steps.txt"
    if next_steps_file.exists():
        next_steps = [
            line.strip()
            for line in next_steps_file.read_text().split("\n")
            if line.strip() and not line.startswith("#")
        ][:5]
    else:
        next_steps = []

    # Extract progress from progress.txt
    progress_file = project_root / ".claude" / "progress.txt"
    if progress_file.exists():
        try:
            progress_pct = int(progress_file.read_text().strip().rstrip("%"))
        except ValueError:
            progress_pct = 0
    else:
        progress_pct = 0

    # Build handover data
    handover = handover_builder.build(task_name)

    # Build handoff data
    handoff_data = handoff_store.build_handoff_data(
        task_name=task_name,
        progress_pct=progress_pct,
        blocker=blocker,
        files_modified=[m.get("file", "") for m in modifications if m.get("file")],
        next_steps=next_steps,
        handover=handover,
        modifications=modifications,
        add_bridge_tokens=True,
        calculate_quality=True,
    )

    # Add open conversation context
    if open_context:
        handoff_data["open_conversation_context"] = open_context

    # Add git branch
    try:
        import subprocess
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            cwd=str(project_root),
            timeout=5,
            env={
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
            },
        )
        if result.returncode == 0:
            handoff_data["git_branch"] = result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        handoff_data["git_branch"] = None

    # Add transcript path
    if transcript_path:
        handoff_data["transcript_path"] = transcript_path

    return handoff_data


def format_handoff_markdown(handoff_data: dict[str, Any], mode: str = "detailed", expand_tokens: bool = True) -> str:
    """Format handoff data as markdown document.

    Args:
        handoff_data: Handoff data dictionary
        mode: Output mode - "summary", "detailed", or "quality"
        expand_tokens: Whether to use expanded_context for decisions (default: True)

    Returns:
        Markdown formatted handoff document
    """
    lines = []

    # Extract common data
    quality_score = handoff_data.get("quality_score", 0)
    quality_rating = handoff_data.get("quality_rating", "Unknown")
    blocker = handoff_data.get("blocker")
    handover = handoff_data.get("handover", {})
    modifications = handoff_data.get("modifications", [])
    next_steps = handoff_data.get("next_steps", [])
    files_modified = handoff_data.get("files_modified", [])
    git_branch = handoff_data.get("git_branch")
    progress = handoff_data.get("progress_pct", 0)

    # Header
    lines.append("# Session Handoff Document")
    lines.append("")

    # Session Metadata
    lines.append("## Session Metadata")
    lines.append(f"- **Quality Score**: {quality_score:.2f}/1.00 ({quality_rating})")
    lines.append(f"- **Timestamp**: {handoff_data.get('timestamp', 'Unknown')}")
    lines.append(f"- **Session ID**: {handoff_data.get('session_id', 'Unknown')}")
    lines.append(f"- **Task Name**: {handoff_data.get('task_name', 'Unknown')}")

    if git_branch:
        lines.append(f"- **Git Branch**: {git_branch}")

    lines.append(f"- **Progress**: {progress}%")
    lines.append("")

    if mode == "quality":
        # Quality breakdown
        lines.append("## Quality Score Breakdown")
        lines.append("")
        lines.append("| Component | Weight | Score | Contribution |")
        lines.append("|-----------|--------|-------|--------------|")
        lines.append(f"| Completion Tracking | 30% | - | {quality_score * 0.30 / 0.30 * 0.30:.2f} |")
        lines.append(f"| Action-Outcome Correlation | 25% | - | {quality_score * 0.25 / 0.25 * 0.25:.2f} |")
        lines.append(f"| Decision Documentation | 20% | - | {quality_score * 0.20 / 0.20 * 0.20:.2f} |")
        lines.append(f"| Issue Resolution | 15% | - | {quality_score * 0.15 / 0.15 * 0.15:.2f} |")
        lines.append(f"| Knowledge Contribution | 10% | - | {quality_score * 0.10 / 0.10 * 0.10:.2f} |")
        lines.append("")
        lines.append(f"**Total Score**: {quality_score:.2f}/1.00")
        lines.append("")

    if mode == "summary":
        # Summary mode - brief overview
        lines.append("## Quick Summary")
        lines.append("")

        blocker = handoff_data.get("blocker")
        if blocker:
            lines.append(f"**Current Blocker**: {blocker.get('description', 'None')}")
        else:
            lines.append("**Current Blocker**: None")

        next_steps = handoff_data.get("next_steps", [])
        if next_steps:
            lines.append("")
            lines.append("**Next Steps**:")
            for step in next_steps[:3]:
                lines.append(f"- {step}")

        return "\n".join(lines)

    # Detailed mode (default)
    lines.append("## Original Request")
    if handover.get("decisions"):
        first_decision = handover["decisions"][0]
        lines.append(f"**User Request**: {first_decision.get('direct_quote', '')[:200]}...")
    else:
        lines.append("**User Request**: Not captured")
    lines.append("")

    # Session Objectives
    lines.append("## Session Objectives")
    if blocker:
        lines.append(f"🟡 **Blocked**: {blocker.get('description', 'Unknown issue')}")
    else:
        lines.append("🟢 **No active blocker**")
    lines.append("")

    # Final Actions (modifications)
    lines.append("## Final Actions Taken")
    if modifications:
        for mod in modifications[-5:]:  # Last 5
            file_path = mod.get("file", "unknown")
            lines.append(f"✅ Modified: `{file_path}`")
    else:
        lines.append("No modifications captured in this session")
    lines.append("")

    # Outcomes (from quality perspective)
    lines.append("## Outcomes")
    if quality_score >= 0.9:
        lines.append(f"📈 **Excellent session quality** ({quality_score:.2f})")
    elif quality_score >= 0.7:
        lines.append(f"📈 **Good session quality** ({quality_score:.2f})")
    elif quality_score >= 0.5:
        lines.append(f"📊 **Acceptable session quality** ({quality_score:.2f})")
    else:
        lines.append(f"⚠️ **Session quality needs improvement** ({quality_score:.2f})")
    lines.append("")

    # Active Work At Handoff
    lines.append("## Active Work At Handoff")
    if next_steps:
        for i, step in enumerate(next_steps[:3], 1):
            lines.append(f"{i}. {step}")
    else:
        lines.append("No explicit next steps recorded")
    lines.append("")

    # Working Decisions (with expanded bridge token context)
    lines.append("## Working Decisions (Critical for Continuity)")
    decisions = handover.get("decisions", [])
    if decisions:
        for decision in decisions[:7]:
            topic = decision.get("topic", "Unknown")
            bridge_token = decision.get("bridge_token", "")

            lines.append(f"🧠 **{topic}**")
            if bridge_token:
                lines.append(f"   - **Bridge Token**: `{bridge_token}`")

            # Use expanded context if available and enabled
            if expand_tokens and (expanded := decision.get("expanded_context")):
                lines.append(f"   - **Decision**: {expanded}")
            else:
                decision_text = decision.get("decision", "")[:100]
                lines.append(f"   - **Decision**: {decision_text}...")
            lines.append("")
    else:
        lines.append("No decisions captured in this session")
        lines.append("")

    # Current Tasks
    lines.append("## Current Tasks")
    if files_modified:
        lines.append(f"📋 **Modified Files** ({len(files_modified)}):")
        for f in files_modified[:10]:
            lines.append(f"   - `{f}`")
    else:
        lines.append("No files modified in this session")
    lines.append("")

    # Known Issues
    lines.append("## Known Issues")
    if blocker:
        lines.append(f"⚠️ **{blocker.get('description', 'Unknown issue')}")
        lines.append(f"   - **Severity**: {blocker.get('severity', 'unknown')}")
        lines.append(f"   - **Source**: {blocker.get('source', 'unknown')}")
    else:
        lines.append("No known issues at handoff")
    lines.append("")

    # Knowledge Contributions
    lines.append("## Knowledge Contributions")
    patterns = handover.get("patterns_learned", [])
    if patterns:
        for pattern in patterns[:5]:
            lines.append(f"💡 {pattern[:100]}...")
    else:
        lines.append("No patterns explicitly captured")
    lines.append("")

    # Next Immediate Action
    lines.append("## Next Immediate Action")
    if next_steps:
        lines.append(f"1. {next_steps[0]}")
    else:
        lines.append("No explicit next steps defined")
    lines.append("")

    # Continuation Instructions
    lines.append("## Continuation Instructions")
    lines.append("1. Review bridge tokens for cross-session decision continuity")
    lines.append("2. Check quality score - maintain >0.7 for good session hygiene")
    lines.append("3. Address any known issues before proceeding")
    lines.append("")

    return "\n".join(lines)


def main():
    """Main entry point for handoff CLI."""
    import argparse

    parser = argparse.ArgumentParser(
        description="HOD - Session Handoff Documentation",
        epilog="Part of the handoff package. Generates comprehensive handoff documentation."
    )
    parser.add_argument(
        "mode",
        nargs="?",
        default="detailed",
        choices=["summary", "detailed", "quality"],
        help="Output mode (default: detailed)",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Show old handoffs that would be deleted (dry-run)",
    )
    parser.add_argument(
        "--cleanup-force",
        action="store_true",
        help="Actually delete old handoffs",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Format handoff as LLM-ready prompt for pasting into another LLM",
    )
    parser.add_argument(
        "--clipboard",
        action="store_true",
        help="Copy handoff to clipboard (Windows only, requires --llm)",
    )
    parser.add_argument(
        "--no-expand-tokens",
        action="store_true",
        help="Disable bridge token expansion (tokens are expanded by default for external LLMs)",
    )

    args = parser.parse_args()

    project_root = Path.cwd()

    # Handle cleanup modes
    if args.cleanup or args.cleanup_force:
        try:
            from handoff.config import CLEANUP_DAYS
        except ImportError:
            print("Warning: CLEANUP_DAYS not found in config, using default 90", file=sys.stderr)
            CLEANUP_DAYS = 90

        task_tracker_dir = project_root / ".claude" / "state" / "task_tracker"
        if not task_tracker_dir.exists():
            print("No task tracker directory found")
            return 0

        cutoff_time = datetime.now(UTC).timestamp() - (CLEANUP_DAYS * 86400)
        to_delete = []

        for task_file in task_tracker_dir.glob("*_tasks.json"):
            try:
                mtime = task_file.stat().st_mtime
                if mtime < cutoff_time:
                    to_delete.append(task_file)
            except OSError:
                continue

        if args.cleanup:
            print(f"Handoff cleanup (dry-run, retention={CLEANUP_DAYS} days):")
            print(f"Would delete {len(to_delete)} old handoff files:")
            for f in to_delete:
                print(f"  - {f.name} ({datetime.fromtimestamp(f.stat().st_mtime).strftime('%Y-%m-%d')})")
            print("\nUse --cleanup-force to actually delete")
        elif args.cleanup_force:
            for f in to_delete:
                try:
                    f.unlink()
                    print(f"Deleted: {f.name}")
                except OSError as e:
                    print(f"Failed to delete {f.name}: {e}")
            print(f"\nDeleted {len(to_delete)} handoff files")
        return 0

    # Generate handoff
    try:
        handoff_data = generate_handoff(project_root, mode=args.mode)
    except Exception as e:
        print(f"Error generating handoff: {e}", file=sys.stderr)
        return 1

    # Handle LLM mode
    if args.llm:
        output = format_llm_prompt(handoff_data)
        if args.clipboard:
            try:
                import subprocess
                subprocess.run(['clip'], input=output.encode(), check=True, shell=True)
                bridge_tokens = extract_bridge_tokens(handoff_data)
                print("✅ Handoff copied to clipboard")
                print(f"   Quality Score: {handoff_data.get('quality_score', 0):.2f}")
                print(f"   Bridge Tokens: {bridge_tokens if bridge_tokens else 'None'}")
            except (ImportError, OSError, subprocess.CalledProcessError):
                print("Failed to copy to clipboard. Output below:")
                print()
                print(output)
        else:
            print(output)
        return 0

    # Expand bridge tokens by default for /hod (external LLM use)
    # Can be disabled with --no-expand-tokens flag
    expand_tokens = not args.no_expand_tokens
    if expand_tokens:
        handoff_data = expand_all_bridge_tokens(handoff_data)

    # Regular output modes
    if args.format == "json":
        print(json.dumps(handoff_data, indent=2, default=str))
    else:
        print(format_handoff_markdown(handoff_data, mode=args.mode, expand_tokens=expand_tokens))

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)

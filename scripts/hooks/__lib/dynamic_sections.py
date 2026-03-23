#!/usr/bin/env python3
"""Dynamic section generation for handoff documents.

This module provides intelligent section inclusion based on session content,
rather than using fixed templates. Sections are included only when relevant.
"""

from __future__ import annotations

from typing import Any


def has_problem(session_data: dict[str, Any]) -> bool:
    """Check if session involves problem-solving (errors, debugging, blockers)."""
    # Check for errors, exceptions, failures
    if session_data.get("has_errors"):
        return True

    # Check for debugging keywords in goal
    goal = session_data.get("goal", "").lower()
    debug_keywords = [
        "fix",
        "debug",
        "error",
        "fail",
        "crash",
        "bug",
        "broken",
        "issue",
    ]
    if any(keyword in goal for keyword in debug_keywords):
        return True

    # Check for blockers in issues
    issues = session_data.get("known_issues", [])
    for issue in issues:
        if issue.get("severity") in ["critical", "high"]:
            return True

    return False


def has_actions(session_data: dict[str, Any]) -> bool:
    """Check if session has concrete actions (file changes, tool execution)."""
    # Check for file modifications
    if session_data.get("active_files"):
        return True

    # Check for final actions taken
    actions = session_data.get("final_actions", [])
    if actions:
        return True

    return False


def has_decisions(session_data: dict[str, Any]) -> bool:
    """Check if session has recorded decisions."""
    decisions = session_data.get("decision_register", [])
    return len(decisions) > 0


def has_tasks(session_data: dict[str, Any]) -> bool:
    """Check if session has pending or in-progress tasks."""
    tasks = session_data.get("tasks_snapshot", [])
    if not tasks:
        return False

    # Check for any non-completed tasks
    for task in tasks:
        if task.get("status") not in ["completed", "done", "resolved"]:
            return True

    return False


def has_learning(session_data: dict[str, Any]) -> bool:
    """Check if session produced reusable insights or patterns."""
    knowledge = session_data.get("knowledge_contributions", [])
    return len(knowledge) > 0


def build_context_section(session_data: dict[str, Any]) -> str:
    """Build the context section (always included)."""
    lines = []
    lines.append("## Context")
    lines.append(f"**Date:** {session_data.get('created_at', 'Unknown')}")
    lines.append(f"**Session ID:** {session_data.get('session_id', 'Unknown')}")
    lines.append(
        f"**Initial intent:** {session_data.get('goal', 'No recorded intent')}"
    )
    return "\n".join(lines)


def build_problem_section(session_data: dict[str, Any]) -> str:
    """Build the problem/situation section."""
    lines = []
    lines.append("## Problem / Situation")

    # Try to extract problem from goal
    goal = session_data.get("goal", "")
    if goal:
        lines.append(f"**Initial task:** {goal}")

    # Check for known issues
    issues = session_data.get("known_issues", [])
    if issues:
        lines.append("**Issues encountered:**")
        for issue in issues:
            severity = issue.get("severity", "unknown")
            desc = issue.get("description", "Unknown issue")
            lines.append(f"- [{severity.upper()}] {desc}")
    else:
        lines.append("**Issues:** None (routine work)")

    return "\n".join(lines)


def build_analysis_section(session_data: dict[str, Any]) -> str:
    """Build the analysis section (root cause, options, rationale)."""
    lines = []
    lines.append("## Analysis")

    # Extract from decisions
    decisions = session_data.get("decision_register", [])
    if decisions:
        lines.append("**Key decisions:**")
        for decision in decisions[:5]:  # Limit to 5 decisions
            kind = decision.get("kind", "unknown")
            summary = decision.get("summary", "")
            rationale = decision.get("rationale", "")

            lines.append(f"- **{kind.upper()}:** {summary}")
            if rationale:
                lines.append(f"  Rationale: {rationale[:200]}...")
    else:
        lines.append("**Key decisions:** No formal decisions recorded")

    return "\n".join(lines)


def build_solution_section(session_data: dict[str, Any]) -> str:
    """Build the solution/outcome section."""
    lines = []
    lines.append("## Solution / Outcome")

    # Check for outcomes
    outcomes = session_data.get("outcomes", [])
    if outcomes:
        lines.append("**Results:**")
        for outcome in outcomes[:5]:
            status = outcome.get("status", "unknown")
            description = outcome.get("description", "Unknown outcome")
            lines.append(f"- [{status}] {description}")
    else:
        lines.append("**Results:** No specific outcomes recorded")

    # Check for active work
    active_work = session_data.get("active_work_at_handoff")
    if active_work:
        lines.append(
            f"**Active work:** {active_work.get('description', 'No active work')}"
        )

    # Files changed
    active_files = session_data.get("active_files", [])
    if active_files:
        lines.append("**Files modified:**")
        for file_path in active_files[:10]:
            lines.append(f"- {file_path}")

    return "\n".join(lines)


def build_lessons_section(session_data: dict[str, Any]) -> str:
    """Build the AAR/lessons section."""
    lines = []
    lines.append("## AAR / Lessons")

    # Knowledge contributions
    knowledge = session_data.get("knowledge_contributions", [])
    if knowledge:
        lines.append("**What worked:**")
        for item in knowledge[:5]:
            insight = item.get("insight", "")
            lines.append(f"- {insight}")

    # What could be improved (check for blockers or issues)
    issues = session_data.get("known_issues", [])
    unresolved_issues = [
        i for i in issues if i.get("severity") not in ["resolved", "fixed"]
    ]
    if unresolved_issues:
        lines.append("**What didn't work:**")
        for issue in unresolved_issues[:3]:
            desc = issue.get("description", "Unknown issue")
            lines.append(f"- {desc}")
    else:
        lines.append("**What didn't work:** No significant issues")

    return "\n".join(lines)


def build_actions_section(session_data: dict[str, Any]) -> str:
    """Build the actions section (for routine work)."""
    lines = []
    lines.append("## Actions Taken")

    # Final actions
    actions = session_data.get("final_actions", [])
    if actions:
        for action in actions[:10]:
            priority = action.get("priority", "unknown")
            description = action.get("description", "Unknown action")
            lines.append(f"- **[{priority.upper()}]** {description}")
    else:
        lines.append("No formal actions recorded")

    return "\n".join(lines)


def build_decisions_section(session_data: dict[str, Any]) -> str:
    """Build the decisions section (for cross-session continuity)."""
    lines = []
    lines.append("## Working Decisions")

    decisions = session_data.get("decision_register", [])
    if decisions:
        for decision in decisions[:10]:
            kind = decision.get("kind", "unknown")
            summary = decision.get("summary", "")
            bridge = decision.get("bridge_token", "N/A")

            lines.append(f"**[{kind.upper()}]** {summary}")
            lines.append(f"  Bridge Token: `{bridge}`")
            if decision.get("rationale"):
                lines.append(f"  Rationale: {decision['rationale'][:150]}...")
            lines.append("")
    else:
        lines.append("No formal decisions recorded")

    return "\n".join(lines)


def build_tasks_section(session_data: dict[str, Any]) -> str:
    """Build the tasks section (for pending work)."""
    lines = []
    lines.append("## Current Tasks")

    tasks = session_data.get("tasks_snapshot", [])
    if tasks:
        pending_tasks = [
            t for t in tasks if t.get("status") not in ["completed", "done"]
        ]

        if pending_tasks:
            for task in pending_tasks[:10]:
                status = task.get("status", "unknown")
                description = task.get("description", "Unknown task")
                lines.append(f"- **[{status}]** {description}")
        else:
            lines.append("All tasks completed")
    else:
        lines.append("No tasks tracked")

    return "\n".join(lines)


def generate_handoff_content(session_data: dict[str, Any]) -> str:
    """Generate handoff content with dynamic section inclusion.

    This is the main entry point that replaces fixed templates with
    intelligent section selection based on what actually happened.
    """
    sections = []

    # Always include context
    sections.append(build_context_section(session_data))
    sections.append("")  # Blank line

    # Conditionally include sections based on session content
    if has_problem(session_data):
        sections.append(build_problem_section(session_data))
        sections.append(build_analysis_section(session_data))
        sections.append(build_solution_section(session_data))
        sections.append(build_lessons_section(session_data))

    if has_actions(session_data):
        sections.append(build_actions_section(session_data))

    if has_decisions(session_data):
        sections.append(build_decisions_section(session_data))

    if has_tasks(session_data):
        sections.append(build_tasks_section(session_data))

    return "\n\n".join(sections)


def calculate_quality_score_dynamic(session_data: dict[str, Any]) -> float:
    """Calculate quality score based on dynamic section presence.

    Maps quality metrics to whatever sections are present:
    - If Analysis exists → score Decision Documentation
    - If Lessons exists → score Knowledge Contribution
    - If Actions exist → score Completion Tracking
    - If Solution exists → score Action-Outcome Correlation
    - If no issues → score Issue Resolution
    """
    score = 0.0
    weights = {
        "analysis": 0.25,  # Decision Documentation
        "lessons": 0.10,  # Knowledge Contribution
        "actions": 0.30,  # Completion Tracking
        "solution": 0.25,  # Action-Outcome Correlation
        "no_issues": 0.10,  # Issue Resolution
    }

    # Decision Documentation
    if has_problem(session_data):
        score += weights["analysis"]

    # Knowledge Contribution
    if has_learning(session_data):
        score += weights["lessons"]

    # Completion Tracking
    if has_actions(session_data):
        score += weights["actions"]

    # Action-Outcome Correlation
    if has_problem(session_data) and has_actions(session_data):
        score += weights["solution"]

    # Issue Resolution (no critical/high issues)
    issues = session_data.get("known_issues", [])
    if not any(i.get("severity") in ["critical", "high"] for i in issues):
        score += weights["no_issues"]

    return min(score, 1.0)

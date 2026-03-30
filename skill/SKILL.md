---
name: handoff
version: "1.0.0"
status: "stable"
description: Research-backed handover documentation system using handoff package
category: documentation
triggers:
  - /handoff
aliases:
  - /handoff

suggest:
  - /restore
  - /session-handoff
---

# Handoff - Enhanced Session Continuity and Handover System

Research-backed handover documentation system for seamless LLM session continuity across compacts. **Automatic capture via PreCompact hooks, manual operations available via `python -m scripts.cli`.**

## Purpose

Generate comprehensive handover documentation that ensures **100% work continuity** across Claude Code sessions, compacts, and agent transitions.

## Architecture

### Implementation
- **Package**: `handoff` at `P:/packages/handoff`
- **Hooks**: PreCompact handoff capture (automatic)
- **Skill**: Claude Code skill integration via `skill/SKILL.md`
- **Storage**: `P:/.claude/state/task_tracker/`

### Hook-Only Architecture

| Feature | Implementation | Trigger |
|---------|---------------|---------|
| Automatic capture | PreCompact hook | Before /compact |
| Handoff storage | JSON files | Automatic |
| Quality scoring | Built-in algorithm | Automatic |

**No manual CLI needed** - handoff capture is fully automated.

## Your Workflow

Before compact/handover:
1. `/handoff detailed` - Document current work
2. Log critical decisions with ADRs (Architecture Decision Records)
3. Define next session objectives
4. `/handoff quality` - Assess completeness

After compact/handover:
1. `/handoff load` - Restore previous context
2. Review decisions for continuity
3. Check quality score
4. Continue with prioritized objectives

**Critical Rule**: "Active Work At Handoff" vs "Current Tasks"
- **Active Work At Handoff**: ONLY work done in THIS session (files modified, tools executed)
- **Current Tasks**: Pending/in_progress tasks from TaskList (may include work from previous sessions)
- When creating handover: Verify session work before adding to "Active Work"

## Validation Rules

### Quality Scoring Algorithm
- 30% Completion Tracking
- 25% Action-Outcome Correlation
- 20% Decision Documentation
- 15% Issue Resolution
- 10% Knowledge Contribution

## Research Foundation

- **500+ files analyzed** for handover and continuity patterns
- **Industry best practices** from AI agent handover frameworks
- **Multi-vector architecture** for optimal context preservation
- **Quality metrics** based on completion tracking and decision documentation

## Quick Start

```bash
# Install the handoff package
pip install -e P:/packages/handoff

# That's it! Handoff capture is fully automatic:
# - PreCompact hooks capture session state before /compact
# - Quality scoring is computed automatically
# - No manual invocation needed
```

## References

| File | Contents |
|------|----------|
| `references/quality-scoring.md` | Quality scoring weights, ratings, and breakdown |
| `references/core-features.md` | Work context structure, automated detection, scoring algorithm |
| `references/usage-patterns.md` | Automatic capture, manual CLI, session continuity workflow |
| `references/handover-template.md` | Full handover document template with examples |
| `references/retention-policy.md` | 90-day retention, auto-cleanup, data storage paths |

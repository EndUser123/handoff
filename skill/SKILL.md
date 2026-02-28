---
name: hod
description: Research-backed handover documentation system using handoff package
category: documentation
triggers:
  - /hod
aliases:
  - /hod

suggest:
  - /restore
  - /session-handoff
---

# HOD - Enhanced Session Continuity and Handover System

Research-backed handover documentation system for seamless LLM session continuity across compacts. **Now implemented as a CLI wrapper using the handoff package.**

## Purpose

Generate comprehensive handover documentation that ensures **100% work continuity** across Claude Code sessions, compacts, and agent transitions.

## Architecture

### Implementation
- **Package**: `handoff` at `P:/packages/handoff`
- **Hooks**: PreCompact handoff capture (automatic)
- **Skill**: Claude Code skill integration via `skill/SKILL.md`
- **Storage**: `P:/.claude/state/task_tracker/`

### Hook-Only Architecture

The handoff package uses automatic capture via PreCompact hooks:

| Feature | Implementation | Trigger |
|---------|---------------|---------|
| Automatic capture | PreCompact hook | Before /compact |
| Handoff storage | JSON files | Automatic |
| Quality scoring | Built-in algorithm | Automatic |
| Bridge tokens | Embedded in decisions | Automatic |

**No manual CLI needed** - handoff capture is fully automated.

## Your Workflow

Before compact/handover:
1. `/hod detailed` - Document current work
2. Log critical decisions with bridge tokens
3. Define next session objectives
4. `/hod quality` - Assess completeness

After compact/handover:
1. `/hod load` - Restore previous context
2. Review bridge tokens for continuity
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
# - Bridge tokens are embedded in decisions
# - No manual invocation needed
```

## Bridge Token Expansion

For external LLM handoffs (the primary use case for `/hod`), bridge tokens are **automatically expanded** with full context:

```
Token: BRIDGE_20260212-202702_HANDOFF
Expanded: Decision made on 2026-02-12 at 20:27 (handoff):

          Reconciled /hod skill with handoff package, adding quality scoring...

          [Reference: BRIDGE_20260212-202702_HANDOFF]
```

This makes handoffs self-contained for platforms that don't have access to local session history (ChatGPT, Claude.ai, etc.).

## Quality Scoring

The handoff package now implements the /hod quality scoring algorithm:

| Component | Weight | Description |
|-----------|--------|-------------|
| Completion Tracking | 30% | Resolved issues vs total modifications |
| Action-Outcome Correlation | 25% | Blocker presence indicates incomplete work |
| Decision Documentation | 20% | Number of decisions captured (target: 3+) |
| Issue Resolution | 15% | Absence of blocker indicates resolution |
| Knowledge Contribution | 10% | Patterns learned captured (target: 2+) |

**Quality Ratings**:
- **0.9-1.0**: Excellent - Comprehensive documentation
- **0.7-0.8**: Good - Well-documented with minor gaps
- **0.5-0.6**: Acceptable - Basic documentation with gaps
- **<0.5**: Needs Improvement

## Bridge Tokens

Bridge tokens enable cross-session continuity for decisions:

```
Format: BRIDGE_YYYYMMDD-HHMMSS_TOPIC_KEYWORD
Example: BRIDGE_20260212-140530_AUTH_FLOW
```

Tokens are automatically added to all decisions in handoff data, allowing you to:
- Track specific decisions across compacts
- Reference decisions by stable identifier
- Maintain continuity in multi-session workflows

## Retention Policy

Handoff documents are retained for **90 days** by default (configurable via `HANDOFF_RETENTION_DAYS` env var).

After 90 days, handoffs are candidates for cleanup because:
- Context is stale for session-bridging purposes
- Relevant decisions should be captured in CKS/patterns
- Storage efficiency for long-running projects

## Auto-Cleanup

```bash
# Check what would be deleted
handoff --cleanup

# Actually delete old handoffs
handoff --cleanup-force

# Custom retention period
export HANDOFF_RETENTION_DAYS=30
```

## Core Features

### Work Context Structure

**Session Metadata**: Session ID, quality score (0-1), duration, working directory, bridge tokens

**Core Components**:
- **Final Actions**: What was completed with evidence and priority
- **Outcomes**: Success/partial/failed outcomes with status tracking
- **Active Work**: Current work in progress with priority ranking
- **Working Decisions**: Key decisions with bridge tokens for continuity
- **Tasks Snapshot**: Task status with priority and effort estimation
- **Known Issues**: Problems with resolution hints and priority
- **Open Questions**: Clarification needs with categorization

**Enhanced Context**:
- **Session Objectives**: Primary goals with priority and status
- **Knowledge Contributions**: Insights and patterns learned
- **Bridge Tokens**: Cross-session continuity tokens
- **Quality Metrics**: Session effectiveness scoring

### Automated Context Detection
- **Git Status Analysis**: Detect active work from git changes
- **Recent File Activity**: Identify modified files in last hour
- **Project Fingerprinting**: Quick project analysis
- **Session State Validation**: Verify context consistency

### Quality Scoring Algorithm
- **30%** Completion Tracking
- **25%** Action-Outcome Correlation
- **20%** Decision Documentation
- **15%** Issue Resolution
- **10%** Knowledge Contribution

## Usage Patterns

### Automatic Handoff Capture

```bash
# Handoff is captured automatically before /compact
# Just run /compact normally - no extra steps needed
```

### Manual Handoff Generation (Debugging)

```bash
# For debugging or manual handoff generation:
python -m handoff.cli            # Generate detailed handoff
python -m handoff.cli summary    # Quick context summary
python -m handoff.cli quality    # Show quality metrics
python -m handoff.cli --cleanup  # Show old handoffs (dry-run)
```

**Auto-cleanup behavior**:
- Handover documents older than 90 days are candidates for deletion
- Dry-run mode shows what would be deleted without actually deleting
- Use `--force` to actually delete files
- Customize retention via `HOD_RETENTION_DAYS` environment variable

**Rationale**: Handover documents are session-bridging artifacts, not permanent records. After 90 days, context is stale and relevant decisions should be captured in CKS/patterns.

## Handover Document Template

```markdown
# Session Handover Document

## Session Metadata
- **Session ID**: session_20251115_143022
- **Quality Score**: 0.85/1.00
- **Timestamp**: 2025-11-15T14:30:22Z
- **Duration**: 2h 15m
- **Working Directory**: /path/to/project

## Original Request
**User Request**: "I'm getting super frustrated with stupid coding mistakes"
**Trigger**: User asked for research document from 6 external repos
**Context**: Wanted implementable options, not theory

## Session Objectives
🟢 **Complete task X** (completed, high)
🟡 **Document findings** (postponed, medium)

## Final Actions Taken
✅ **Action A** (high priority)
✅ **Action B** (high priority)

## Outcomes
📈 **Success outcome** (success)
📈 **Another success** (success)

## Active Work At Handoff
🔄 **Currently Working On**: Auto-skill activation implementation
   - Status: Implemented, tested, enabled
   - Files Modified: UserPromptSubmit_skill_router.py, UserPromptSubmit_router.py, settings.json
   - Next: Monitor for effectiveness

**CRITICAL**: "Active Work At Handoff" MUST only include work done in THIS session.
- Include ONLY if: files created/modified, tools executed, evidence of progress
- Do NOT copy from previous handovers or TaskList without verification
- If no active work in this session, state: "No active work in this session"

## Working Decisions (Critical for Continuity)
🧠 **Decision**: Use approach X over Y
   - **Bridge Token**: DECISION_20251115-143022
   - **Rationale**: Reason here
   - **Impact**: High

## Current Tasks
📋 **#611**: Task description (in_progress, high)
📋 **#612**: Task description (pending, high)

## Known Issues
⚠️ **ISSUE-1**: Description (observed, medium)
⚠️ **ISSUE-2**: Description (observed, low)

## Open Questions
❓ **Question**: Question text? (high, technical)

## Knowledge Contributions
💡 **Insight**: Session continuity requires decision preservation (pattern)

## Next Immediate Action
1. Review research document at `P:/docs/research/coding-mistake-prevention-research.md`
2. Test auto-skill with "debug this" prompt
3. Decide on build verification priority

## Continuation Instructions
1. **Priority Actions**: Address high-priority tasks first
2. **Critical Decisions**: Respect bridge-tokened decisions
3. **Quality Target**: Maintain >0.8 session quality score
```

## Quality Metrics

### Session Quality Score (0-1)
- **0.9-1.0**: Excellent - Comprehensive documentation
- **0.7-0.8**: Good - Well-documented with minor gaps
- **0.5-0.6**: Acceptable - Basic documentation with gaps
- **<0.5**: Needs Improvement

### Quality Breakdown
- Task Completion
- Decision Documentation
- Action-Outcome Link
- Knowledge Capture
- Issue Resolution

## Session Continuity Workflow

### Before Compact/Handover
1. `/hod detailed` - Document current work
2. Log critical decisions with bridge tokens
3. Define next session objectives
4. `/hod quality` - Assess completeness

### After Compact/Handover
1. `/hod load` - Restore previous context
2. Review bridge tokens for continuity
3. Check quality score
4. Continue with prioritized objectives

## Data Storage

- **Session State**: `__csf/.staging/claude_session.json`
- **Work Context**: `__csf/.staging/work_context.json`
- **Handover Documents**: `__csf/.staging/handovers/`
- **Quality Metrics**: `__csf/.staging/quality_metrics.json`

### Auto-Cleanup Policy

**Handover documents older than 90 days are automatically deleted.**

**Rationale**: Handover documents are session-bridging artifacts, not permanent records. After 90 days, the context is stale and relevant decisions should be captured in CKS/patterns.

**Cleanup options**:
```bash
# Manual cleanup of old handovers
handoff --cleanup          # Show what would be deleted
handoff --cleanup-force    # Delete files older than 90 days

# Custom retention period
export HANDOFF_RETENTION_DAYS=30  # Default: 90
```

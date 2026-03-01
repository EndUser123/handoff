# ADR 001: Research-Backed Handoff Documentation

**Status:** Accepted
**Date:** 2026-03-01
**Context:** handoff package session continuation system

## Context

When handing off between AI sessions, we needed to decide what information to capture:

1. **Minimal state**: Just session ID and timestamp
2. **Conversation summary**: High-level overview
3. **Research-backed handoff**: Full context with sources, citations, and traceability

## Decision

We chose **research-backed handoff documentation** with comprehensive context capture.

### Rationale

AI interactions involve:
- **Multi-step reasoning** - Need to preserve logical flow
- **Research artifacts** - Sources, findings, data need handoff
- **Task state** - What's done, what's pending, what's blocked
- **User corrections** - Learning from mistakes is critical

A simple session ID is insufficient for meaningful continuity.

### Implementation

```python
@dataclass
class Handoff:
    id: str
    timestamp: datetime
    session_id: str

    # TL;DR section
    quick_reference: QuickReference

    # Full context
    conversation_summary: Summary
    task_state: TaskState
    research_artifacts: List[Artifact]

    # Provenance
    transcript_path: str  # Link to full conversation

    # Evidence
    metadata: Dict[str, Any]
```

### Key Features

#### 1. Quick Reference (TL;DR)
```markdown
## Quick Reference

- **Session ID**: abc123
- **Timestamp**: 2026-03-01
- **Transcript**: /path/to/transcript.md
- **Active Tasks**: 3 (Fix X, Implement Y, Review Z)
- **Next Steps**: [prioritized list]
```

#### 2. Citation-Backed Claims
Every assertion in the handoff cites the source:

```markdown
## Key Decisions

- **Use PostgreSQL over MongoDB** (Source: transcript line 245)
  - Reasoning: Need ACID compliance for financial transactions
  - User correction: "Actually, we need transactions, not just ACID"
```

#### 3. Task State Tracking
- ✅ Completed tasks with proof
- 🔄 In-progress tasks with status
- ⏳ Pending tasks with dependencies
- 🚫 Blocked tasks with blockers

## Trade-offs

### Pros
- **Full context restoration** - Can resume without re-reading entire transcript
- **Evidence-based** - Every claim is verifiable
- **Learning capture** - User corrections preserved
- **Audit trail** - Can trace decisions back to source

### Cons
- **Larger handoff size** - ~5-15KB vs ~500B for minimal
- **Generation time** - 2-5 seconds to analyze transcript
- **Storage overhead** - Need to persist handoffs
- **Maintenance** - Handoff format may evolve

## Mitigations

- **Compression**: Handoffs compress to ~30% with gzip
- **Caching**: Cache handoffs for 24h to avoid regeneration
- **Incremental updates**: Only regenerate when transcript changes
- **Format versioning**: Handoff schema includes version for migration

## Related Decisions

- ADR 002: Filesystem vs Database Storage (pending)
- ADR 003: Handoff Expiration Policy (pending)

## References

- [The Psychology of Handoffs](https://hci.stanford.edu/papers/handoffs.pdf)
- [Session State Management Patterns](https://martinfowler.com/eaaDev/SessionState.html)

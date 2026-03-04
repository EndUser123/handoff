# Handoff Context Enrichment - Session Type Detection

**Created**: 2026-03-04
**Status**: Planning
**Focus**: Session type detection using message content + file patterns

## Overview

Add intelligent session type detection to categorize work sessions (debug, feature, refactor, test, docs) by analyzing BOTH last user message content AND file modification patterns. This enriches handoff context for better AI understanding of session intent.

## Architecture

### Components

1. **SessionTypeDetector** (new module)
   - Location: `src/handoff/session_type_detector.py`
   - Methods:
     - `detect_session_type(last_message: str, active_files: list[str]) -> str`
     - `_analyze_message_content(message: str) -> dict[str, int]`
     - `_analyze_file_patterns(files: list[str]) -> dict[str, int]`
     - `_combine_signals(message_scores: dict, file_scores: dict) -> str`

2. **Integration Points**
   - PreCompact: Capture session type in state file
   - SessionStart: Display session type in restoration prompt

### Session Types

| Type | Description | Message Keywords | File Patterns |
|------|-------------|------------------|---------------|
| `debug` | Bug fixing | "fix", "bug", "error", "broken", "fails", "crash" | Test files, error logs |
| `feature` | New features | "add", "implement", "create", "build" | Source files, new modules |
| `refactor` | Code cleanup | "refactor", "clean up", "simplify", "optimize" | Existing source files |
| `test` | Testing work | "test", "verify", "coverage", "assert" | Test files, pytest configs |
| `docs` | Documentation | "document", "readme", "comment", "explain" | MD files, docstrings |
| `mixed` | Multiple types | Mixed signals | Mixed patterns |

## Data Flow

```
PreCompact Hook:
  1. Extract last_user_message from transcript
  2. Extract active_files from recent modifications
  3. Call SessionTypeDetector.detect_session_type()
  4. Write session_type to state file

SessionStart Hook:
  1. Read session_type from state file
  2. Display in restoration prompt: "Session Type: 🐛 debug"
```

## Error Handling

- Missing/empty data → Return "unknown" session type
- Conflicting signals → Return "mixed" session type
- File not accessible → Log warning, continue without file analysis

## Test Strategy

### Unit Tests
- Test message keyword detection for each session type
- Test file pattern detection for each session type
- Test signal combination (agreement, conflict, missing data)
- Test edge cases (empty strings, no files, unknown patterns)

### Integration Tests
- Test PreCompact writes session_type to state file
- Test SessionStart reads and displays session_type
- Test full capture → restore flow

### Edge Cases
- No active files (message-only detection)
- No user message (file-only detection)
- Neither available (return "unknown")

## Standards Compliance

**Python 2025+ Standards**:
- Use `type: ignore` only where necessary
- Prefer `dict[str, Any]` over `Dict`
- Use `pathlib.Path` for file operations
- Comprehensive docstrings
- Ruff formatting

## Implementation Plan

### Task 1: Create SessionTypeDetector Module
- File: `src/handoff/session_type_detector.py`
- TDD approach: Write tests first, implement detector logic

### Task 2: Integrate into PreCompact Hook
- Modify: `PreCompact_handoff_capture.py`
- Add session_type to state file

### Task 3: Integrate into SessionStart Hook
- Modify: `SessionStart_handoff_restore.py`
- Display session_type in restoration prompt

### Task 4: Documentation
- Update README.md with session type feature
- Add examples of session type detection

## Ramifications

**Breaking Changes**: None (additive feature)

**Backwards Compatibility**: Old state files without session_type will default to "unknown"

**Performance**: Negligible impact (simple keyword matching)

**Migration**: None required (optional field)

## Success Criteria

- [ ] Session type detector correctly identifies 5+ session types
- [ ] Integration tests pass (capture → restore flow)
- [ ] Documentation updated
- [ ] No regressions in existing tests

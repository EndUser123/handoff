# Implementation Plan: UCI Handoff V2 Fixes

**Date**: 2026-03-16
**Status**: In Progress
**Reference**: UCI Review - 21 findings (2 CRITICAL, 7 HIGH, 10 MEDIUM, 4 LOW)

---

## Overview

Comprehensive fixes for handoff V2 integrity issues identified by Unified Code Inspection. Focus areas: performance optimization (eliminate double I/O), security hardening (path traversal prevention), and logic corrections (checksum validation).

**Root Cause Cascade**:
1. PreCompact hook reads wrong transcript_path → builds handoff with test data
2. save_handoff() fails silently or writes invalid checksum → file corrupted
3. SessionStart can't find valid handoff → falls back to wrong session

---

## Architecture

**Affected Components**:
- `scripts/hooks/__lib/handoff_files.py` - File storage with checksum verification
- `scripts/hooks/__lib/handoff_v2.py` - Core library with checksum computation
- `scripts/hooks/SessionStart_handoff_restore.py` - Restore hook with checksum validation
- `scripts/hooks/PreCompact_handoff_capture.py` - Capture hook with transcript validation

**Key Changes**:
1. Eliminate double file I/O (compute checksum from in-memory payload)
2. Fix TOCTOU race condition (verify checksum before releasing FileLock)
3. Add path traversal protection (verify path is within project root)
4. Fix inverted test detection logic
5. Extract shared checksum validation function
6. Add comprehensive test coverage

---

## Data Flow

```
Current (Buggy):
  PreCompact → save_handoff() → write file → release lock → read back → verify checksum
                                                         ↑ TOCTOU window

Fixed:
  PreCompact → compute checksum in-memory → write file → verify checksum before release
```

---

## Error Handling

**Checksum Mismatch**: Delete corrupt file, log error, return False
**Path Traversal Attempt**: Reject with HandoffValidationError
**Missing Checksum Field**: Reject restore (inverted from current allow-through)
**Test Transcript**: Warn but continue (current inverted logic rejects valid)

---

## Test Strategy

**Unit Tests**:
- Test checksum computation from in-memory payload
- Test checksum verification within FileLock context
- Test path traversal rejection
- Test missing checksum rejection
- Test inverted test detection fix

**Integration Tests**:
- Test end-to-end capture → save → restore flow
- Test concurrent write scenarios (multi-terminal)
- Test corrupt handoff rejection

---

## Standards Compliance

**Python 3.12+ Standards**:
- Type hints on all function signatures
- `with` statements for resource management
- Explicit exception handling with specific exception types

**Handoff V2 Standards**:
- SHA-256 checksum integrity
- Atomic file writes with FileLock
- Deep copy normalization for checksum computation

---

## Ramifications

**Breaking Changes**: None (internal implementation only)

**Performance Impact**:
- Positive: Eliminates 3-13ms double I/O overhead per save
- Positive: Eliminates 5-10ms deepcopy overhead via deferred computation
- Net: 8-23ms performance improvement per handoff save

**Compatibility**: Fully backward compatible (file format unchanged)

---

## Implementation Tasks

### Priority 1: Before Merge (CRITICAL + HIGH)

#### PERF-001: Eliminate Double File I/O (5 min)
**File**: `scripts/hooks/__lib/handoff_files.py`
**Action**: Compute checksum from in-memory payload before write, not from read-back
**Lines**: 132-151
**Change**:
```python
# BEFORE: Write → read back → verify
atomic_write_with_retry(temp_path, self.handoff_file)
# Then read and verify...

# AFTER: Compute checksum → write → verify from in-memory
expected_checksum = payload.get("checksum")
with open(temp_path, "w", encoding="utf-8") as handle:
    handle.write(serialized)
# Verify temp file content before atomic move
with open(temp_path, encoding="utf-8") as verify_handle:
    written_payload = json.load(verify_handle)
actual_checksum = compute_checksum(written_payload)
if actual_checksum != expected_checksum:
    temp_path.unlink()  # Clean up corrupt temp file
    return False
# Only then do atomic move
atomic_write_with_retry(temp_path, self.handoff_file)
```
**Acceptance**: Checksum verified from temp file before atomic move

#### LOGIC-002: Fix Missing Checksum Bypass (2 min)
**File**: `scripts/hooks/SessionStart_handoff_restore.py`
**Action**: Invert condition to reject missing checksums
**Lines**: 144-163
**Change**:
```python
# BEFORE: if stored_checksum: (allows None through)
if stored_checksum:
    computed_checksum = compute_checksum(raw_payload)
    if computed_checksum != stored_checksum:
        # reject...

# AFTER: Require checksum field
stored_checksum = raw_payload.get("checksum")
if not stored_checksum:
    print(json.dumps(_build_output(
        "No safe current handoff found - missing checksum field",
        build_no_snapshot_hint("checksum field missing - data may be incomplete")
    ), indent=2))
    sys.exit(0)
computed_checksum = compute_checksum(raw_payload)
if computed_checksum != stored_checksum:
    # reject...
```
**Acceptance**: Missing checksum field causes rejection

#### SEC-001: Add Path Traversal Protection (5 min)
**File**: `scripts/hooks/__lib/handoff_v2.py`
**Action**: Verify transcript_path is within project root before accepting
**Lines**: 223-234 (validate_envelope function)
**Change**:
```python
# Add path boundary check
from pathlib import Path

project_root = Path.cwd().resolve()
transcript_file = Path(transcript_path).resolve()

try:
    transcript_file.relative_to(project_root)
except ValueError:
    raise HandoffValidationError(
        f"resume_snapshot.transcript_path must be within project root: {transcript_path}"
    )

# Existing existence check
if not transcript_file.exists():
    raise HandoffValidationError(
        f"resume_snapshot.transcript_path file does not exist: {transcript_path}"
    )
```
**Acceptance**: Paths outside project root are rejected

#### LOGIC-003: Fix Inverted Test Detection (3 min)
**File**: `scripts/hooks/PreCompact_handoff_capture.py`
**Action**: Fix inverted condition in test transcript warning
**Lines**: 452-467
**Change**:
```python
# BEFORE (inverted):
if "test" in transcript_file.name.lower() and transcript_file.name != transcript_path:
    # This condition is backwards - name != path is always true

# AFTER:
if "test" in transcript_file.name.lower():
    logger.warning(
        "[PreCompact V2] Test transcript detected: %s - this may indicate wrong transcript_path",
        transcript_file.name,
    )
    # Continue anyway (warning only)
```
**Acceptance**: Test transcripts trigger warning with correct logic

#### QUAL-004: Add Checksum Verification Tests (15 min)
**File**: `packages/handoff/tests/test_handoff_files.py`
**Action**: Add tests for checksum verification scenarios
**Tests**:
```python
def test_checksum_verified_from_temp_file_before_move():
    """Verify checksum is checked before atomic move (PERF-001)"""
    # Create payload with invalid checksum
    payload = {"checksum": "invalid", ...}
    storage.save_handoff(payload)
    # Should return False without writing final file

def test_missing_checksum_rejected_on_restore():
    """Verify missing checksum field causes rejection (LOGIC-002)"""
    raw_payload = {"resume_snapshot": {...}}  # No checksum field
    decision = evaluate_for_restore(raw_payload, terminal_id="test")
    assert not decision.ok
    assert "missing checksum" in decision.reason

def test_path_traversal_rejected():
    """Verify paths outside project root are rejected (SEC-001)"""
    snapshot = build_resume_snapshot(
        ...,
        transcript_path="../../../etc/passwd"
    )
    with pytest.raises(HandoffValidationError):
        validate_envelope({"resume_snapshot": snapshot, ...})
```
**Acceptance**: All tests pass

### Priority 2: Follow-Up (MEDIUM Priority)

#### QUAL-001: Extract Checksum Validation to Shared Function (10 min)
**File**: `scripts/hooks/__lib/handoff_v2.py`
**Action**: Create `verify_checksum_integrity()` function
**Change**:
```python
def verify_checksum_integrity(
    payload: dict[str, Any],
    expected_checksum: str | None,
    error_context: str
) -> None:
    """Verify payload checksum matches expected value.

    Args:
        payload: Handoff envelope to verify
        expected_checksum: Expected checksum value (required)
        error_context: Context string for error messages

    Raises:
        HandoffValidationError: If checksum mismatch or missing
    """
    if not expected_checksum:
        raise HandoffValidationError(
            f"{error_context}: Checksum field is required"
        )
    actual = compute_checksum(payload)
    if actual != expected_checksum:
        raise HandoffValidationError(
            f"{error_context}: Checksum mismatch (expected={expected_checksum}, actual={actual})"
        )
```
**Usage**: Replace duplicated validation code in both files
**Acceptance**: Single source of truth for checksum validation

#### PERF-004: Defer Checksum Computation (8 min)
**File**: `scripts/hooks/__lib/handoff_files.py`
**Action**: Compute checksum only after basic validation passes
**Lines**: 59-68 (save_handoff function)
**Change**:
```python
def save_handoff(self, payload: dict[str, Any]) -> bool:
    """Validate and persist the V2 payload."""
    try:
        # Basic structure validation first (fast)
        _require_fields(payload, ["resume_snapshot", "decision_register", "evidence_index"])

        # Only then compute checksum (expensive)
        checksum = compute_checksum(payload)
        payload["checksum"] = checksum

        # Continue with save...
```
**Acceptance**: Checksum computed only for valid payloads

#### SEC-002: Sanitize Error Messages (5 min)
**File**: `scripts/hooks/__lib/handoff_v2.py`
**Action**: Remove file paths from error messages
**Change**:
```python
# BEFORE (leaks path):
raise HandoffValidationError(f"transcript_path file does not exist: {transcript_path}")

# AFTER (sanitized):
raise HandoffValidationError("transcript_path file does not exist")
```
**Acceptance**: Error messages don't leak internal paths

#### QUAL-002: Standardize Log Levels (3 min)
**File**: `scripts/hooks/SessionStart_handoff_restore.py`
**Action**: Change checksum mismatch to ERROR level
**Lines**: 148-152
**Change**:
```python
# BEFORE: logger.warning(...)
# AFTER: logger.error(...)
logger.error(
    "[SessionStart V2] Checksum mismatch: expected=%s, computed=%s",
    stored_checksum,
    computed_checksum,
)
```
**Acceptance**: Consistent ERROR level for checksum failures

#### QUAL-003: Improve Function Cohesion (12 min)
**File**: `scripts/hooks/__lib/handoff_files.py`
**Action**: Extract checksum verification to separate method
**Change**:
```python
def _verify_temp_file_checksum(self, temp_path: Path, expected_checksum: str) -> bool:
    """Verify checksum of temp file before atomic move.

    Args:
        temp_path: Path to temp file containing written data
        expected_checksum: Expected checksum value

    Returns:
        True if checksum matches, False otherwise
    """
    try:
        with open(temp_path, encoding="utf-8") as handle:
            payload = json.load(handle)
        actual = compute_checksum(payload)
        return actual == expected_checksum
    except (json.JSONDecodeError, OSError):
        return False
```
**Acceptance**: Single responsibility per function

#### PERF-002: Optimize Checksum Computation (deferred)
**Note**: Deferred due to complexity (requires in-place normalization vs deepcopy)
**Action**: Consider zero-copy normalization approach
**Estimated**: 30 min (LOWER PRIORITY)

### Priority 3: Nice to Have (LOW Priority)

#### QUAL-005: Strengthen Test Warning (2 min)
**File**: `scripts/hooks/PreCompact_handoff_capture.py`
**Action**: Change test warning level from WARNING to ERROR
**Acceptance**: Test transcripts trigger ERROR level log

#### QUAL-006: Consistent Variable Naming (5 min)
**File**: Multiple files
**Action**: Standardize variable naming (raw_payload vs payload vs handoff_data)
**Acceptance**: Consistent naming across codebase

#### QUAL-007: Add Error Context (8 min)
**File**: `scripts/hooks/__lib/handoff_files.py`
**Action**: Add more context to error messages (file path, operation)
**Acceptance**: Error messages include sufficient context for debugging

#### LOGIC-004: Document Stale Checksum Behavior (3 min)
**File**: `scripts/hooks/__lib/handoff_v2.py`
**Action**: Add docstring explaining checksum staleness handling
**Acceptance**: Clear documentation of checksum lifecycle

---

## Pre-Mortem Analysis

### Failure Mode 1: Checksum Verification Inside Lock Still Has Race
**Root Cause**: FileLock scope too narrow (doesn't cover directory read)
**Prevention**: Ensure FileLock covers entire directory, not just file
**Test**: Multi-terminal concurrent write test

### Failure Mode 2: Path Traversal via Symlink
**Root Cause**: `resolve()` follows symlinks, allowing escape
**Prevention**: Check both resolved path AND reject if symlink target outside root
**Test**: Add symlink test case

### Failure Mode 3: Checksum Computation Performance Regression
**Root Cause**: In-place normalization slower than expected
**Prevention**: Benchmark before/after, cache checksum if called multiple times
**Test**: Performance baseline test (verify <10ms for typical payload)

---

## Observability

**Metrics to Track**:
- Checksum mismatch rate (should be ~0% after fixes)
- Path traversal rejection rate (should be 0% in normal operation)
- Handoff save latency (target: <20ms for typical payload)

**Alert Thresholds**:
- Checksum mismatch > 1% → Investigate storage layer
- Save latency > 50ms → Investigate checksum computation
- Path traversal rejection > 0 → Investigate security incident

---

## Verification Checklist

- [ ] All Priority 1 tasks implemented and tested
- [ ] All unit tests pass
- [ ] Integration tests pass (multi-terminal scenario)
- [ ] Performance baseline verified (<20ms save latency)
- [ ] Security tests pass (path traversal, symlinks)
- [ ] Error messages sanitized (no path leaks)
- [ ] Log levels consistent (ERROR for checksum failures)
- [ ] Code review passed (cross-team review if needed)

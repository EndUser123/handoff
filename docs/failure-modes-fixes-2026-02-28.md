# Failure Modes Fixes - 2026-02-28

## Summary

Implemented fixes for **7 verified issues** across the handoff system. During code review and tracing, discovered and fixed **2 additional critical bugs** in the implementation.

## Original Fixes (7 Issues)

### P0 - Critical

#### Issue #2 & #3: Transcript Missing/Empty Fallback
**Problem:** When transcript was missing or empty, system fell back to potentially stale data from hook_input, active_command file, or blocker.description.

**Fix:** Skip handoff capture entirely when transcript is unavailable, with clear warning messages.

**File:** `src/handoff/hooks/PreCompact_handoff_capture.py:1057-1096`

```python
# Check if transcript is missing or empty
if not transcript_path.exists():
    print("[PreCompact] WARNING: Transcript file missing - cannot capture authentic context")
    transcript_unavailable = True
elif file_size == 0:
    print("[PreCompact] WARNING: Transcript file is empty - skipping handoff capture")
    transcript_unavailable = True

# Skip handoff capture if transcript unavailable
if transcript_unavailable:
    print("[PreCompact] Handoff capture skipped - transcript required for authentic context")
    return True
```

### P1 - High Priority

#### Issue #4: Task File Corruption
**Problem:** Corrupted task files (invalid JSON) were logged at DEBUG level (invisible) and not cleaned up.

**Fix:** Log at ERROR level and automatically delete corrupted files.

**File:** `src/handoff/hooks/SessionStart_handoff_restore.py:592-605, 622-631`

```python
except (json.JSONDecodeError, OSError) as e:
    logger.error(f"[SessionStart] CORRUPTED task file {task_file_path}: {e}")
    try:
        task_file_path.unlink(missing_ok=True)
        logger.info(f"[SessionStart] Deleted corrupted task file: {task_file_path}")
    except OSError:
        pass
```

#### Issue #6: Concurrent Compaction Race Condition
**Problem:** Two terminals could overwrite each other's task files during simultaneous compaction.

**Fix:** File locking with exclusive lock file creation and stale lock detection.

**File:** `src/handoff/hooks/__lib/handoff_store.py:684-755`

**Additional Bug Found:** Lock cleanup would delete another process's lock file if lock acquisition failed.

**Fix:** Only unlink lock file if we successfully acquired it:

```python
finally:
    if lock_acquired and lock_fd is not None:
        try:
            os.close(lock_fd)
        except OSError:
            pass
        try:
            lock_file_path.unlink(missing_ok=True)
        except OSError:
            pass
```

### P2 - Medium Priority

#### Issue #7: First User Message Extraction
**Problem:** Only checked first 20 lines of transcript, missing first user message if it appeared later.

**Fix:** Use TranscriptParser to scan entire transcript.

**File:** `src/handoff/hooks/PreCompact_handoff_capture.py:772-798`

#### Issue #8: Checksum Silent Failure
**Problem:** Checksum errors logged at DEBUG level (invisible), users not notified.

**Fix:** Log at ERROR level and print user-visible messages.

**File:** `src/handoff/hooks/SessionStart_handoff_restore.py:747-755`

```python
if not is_valid:
    logger.error(f"[SessionStart] Checksum verification failed: {error}")
    print("[SessionStart] Warning: Handoff data corrupted, skipping restoration")
    print(f"[SessionStart] Error: {error}")
    return 0
```

#### Issue #9: Cleanup Failure Retry
**Problem:** Active_session cleanup failures were silently ignored, leading to duplicate restoration.

**Fix:** Mark tasks for cleanup retry with timestamp.

**File:** `src/handoff/hooks/SessionStart_handoff_restore.py:672-697`

**Additional Bug Found:** File descriptor reuse in retry logic.

**Fix:** Create new temp file in except block:

```python
except OSError as replace_error:
    # Mark task for cleanup retry
    if "tasks" in task_data:
        for task_name in ("active_session", "continue_session"):
            if task_name in task_data["tasks"]:
                task_data["tasks"][task_name]["_cleanup_failed"] = True

    # Create NEW temp file (fd was already consumed)
    fd_retry, temp_path_retry = tempfile.mkstemp(suffix=".tmp", dir=str(task_file_path.parent))
    try:
        with os.fdopen(fd_retry, "w", encoding="utf-8") as f:
            json.dump(task_data, f, indent=2)
        os.replace(temp_path_retry, str(task_file_path))
    finally:
        try:
            os.close(fd_retry)
        except OSError:
            pass
```

## Additional Bugs Found During Review

### Bug #1: Lock File Cleanup Race Condition
**Severity:** P1 - Critical
**Location:** `handoff_store.py:753`

**Problem:** If lock acquisition failed (timeout), the finally block would still try to unlink the lock file, potentially deleting another process's active lock.

**Impact:** Could cause race condition where two terminals both think they have the lock.

**Fix:** Only unlink lock file if `lock_acquired` is True.

### Bug #2: File Descriptor Reuse
**Severity:** P1 - High
**Location:** `SessionStart_handoff_restore.py:685`

**Problem:** File descriptor `fd` was consumed by first `os.fdopen()` call, then reused in except block for retry write.

**Impact:** Would cause OSError when trying to write cleanup retry markers.

**Fix:** Create new temp file with new file descriptor in except block.

## Test Results

All tests pass:
- ✅ 10/10 failure modes tests
- ✅ 33/33 handoff integration tests
- ✅ No regressions in existing tests

## Files Modified

1. `src/handoff/hooks/PreCompact_handoff_capture.py` - Issues #2, #3, #7
2. `src/handoff/hooks/SessionStart_handoff_restore.py` - Issues #4, #8, #9
3. `src/handoff/hooks/__lib/handoff_store.py` - Issue #6 + lock cleanup bug
4. `CHANGELOG.md` - Documentation
5. `docs/failure-mode-analysis.md` - Status update

## Verification

- ✅ Syntax validation (ast.parse) on all modified files
- ✅ All existing tests pass
- ✅ New failure modes tests pass
- ✅ Code traced and verified for logic correctness
- ✅ Edge cases identified and fixed

## Conclusion

**9 total issues fixed:**
- 7 issues from original failure mode analysis
- 2 additional bugs found during code review

The handoff system is now more robust against edge cases, concurrent access, and failure scenarios.

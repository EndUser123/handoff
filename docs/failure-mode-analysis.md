# Handoff System Failure Mode Analysis

**Date:** 2026-02-28
**Status:** ✅ **FIXES IMPLEMENTED** (2026-02-28)

## Summary of Fixes

All verified issues have been fixed:
- ✅ **Issue #2 & #3** (P0): Skip handoff when transcript missing/empty
- ✅ **Issue #4** (P1): Auto-delete corrupted task files with ERROR logging
- ✅ **Issue #6** (P1): File locking prevents concurrent overwrites
- ✅ **Issue #7** (P2): Fixed first message extraction (was 20-line limit)
- ✅ **Issue #8** (P2): Checksum errors now visible to users
- ✅ **Issue #9** (P2): Cleanup retry mechanism with task marking

**False alarms** (NOT actual problems):
- ❌ **Issue #1**: Multiple compaction cycles - `get_current_task()` always checks current sources with 5-minute freshness
- ❌ **Issue #5**: Terminal ID instability - PID validation + parent PID matching prevents reuse

## Executive Summary

After fixing the priority system bug (stale `last_user_message` from cached files), this document identifies **9 additional failure modes** that could cause incorrect handoff capture or restoration.

## Critical Issues (P0 - High Impact, Likely to Occur)

### 1. **Multiple Compaction Cycles Without Cleanup**

**Severity:** P0 - Critical
**Likelihood:** High - Occurs with frequent compactions

**Problem:**
If a session compacts multiple times without the user doing any work, the `active_session` task may contain stale data from an earlier cycle.

**Scenario:**
```
1. User works on task A → Compaction #1 → active_session created with task A data
2. User resumes, does nothing → Compaction #2 → active_session updated with SAME task A data
3. User switches to task B → Compaction #3 → active_session STILL has task A data
4. User resumes → Gets wrong task A context instead of current task B
```

**Root Cause:**
The `active_session` task is **reused across multiple compaction cycles** without checking if the actual work context has changed.

**Evidence:**
```python
# PreCompact_handoff_capture.py:1102
self.handoff_store.create_continue_session_task(
    task_name, task_id, handoff_metadata
)
```
This **overwrites** the existing `active_session` task, but the task_name might be stale from a previous cycle.

**Detection:**
- Look for `saved_at` timestamp that doesn't match recent activity
- Check if `task_name` matches recent file modifications or tool usage

**Fix:**
Before creating `active_session`, verify that `task_name` reflects current context:
- Check recent tool usage (last 10 tool calls)
- Verify recent file modifications match the task
- If mismatch, use `TaskIdentityManager` to recover actual current task

---

### 2. **Transcript File Missing or Unreadable**

**Severity:** P0 - Critical
**Likelihood:** Medium - Filesystem issues, permissions

**Problem:**
If `transcript_path` is missing or unreadable, `extract_last_user_message()` returns `None`, causing fallback to potentially stale cached data.

**Scenario:**
```
1. Transcript file deleted/corrupted before compaction
2. TranscriptParser.extract_last_user_message() returns None
3. Falls back to hook_input → active_command file → blocker
4. All fallbacks return stale data from earlier in session
```

**Evidence:**
```python
# transcript.py:524-526
if not self.transcript_path or not Path(self.transcript_path).exists():
    self._parsed_entries_cache = []
    return self._parsed_entries_cache  # Empty list!
```

**Detection:**
- Check if transcript file exists and is readable
- Validate file size is reasonable (> 0 bytes)
- Verify JSON parsing succeeds

**Fix:**
Add explicit validation:
```python
if not self.transcript_path:
    logger.error("[PreCompact] No transcript_path available - cannot capture authentic context")
    return  # Abort capture, don't use stale fallbacks
```

---

### 3. **Empty Transcript (No User Messages)**

**Severity:** P0 - Critical
**Likelihood:** Low - Edge case, but possible

**Problem:**
If transcript contains no user messages, `extract_last_user_message()` returns `None`, falling back to stale data.

**Scenario:**
```
1. New session with only system messages
2. No actual user input yet
3. Compaction triggered
4. extract_last_user_message() returns None
5. Falls back to stale data from previous session
```

**Evidence:**
```python
# transcript.py:1132-1138
for i in range(len(entries) - 1, -1, -1):
    entry = entries[i]
    if entry.get("type") == "user":
        msg_obj = entry.get("message", {})
        # ... content extraction ...
        # If loop completes without finding user message, returns None
```

**Detection:**
- Check if `extract_last_user_message()` returns None
- Verify transcript has at least one user message

**Fix:**
```python
last_user_message = self.parser.extract_last_user_message()
if not last_user_message:
    logger.warning("[PreCompact] No user messages found in transcript - skipping handoff capture")
    return  # Don't capture handoff for empty session
```

---

## High Issues (P1 - Medium Impact, Possible)

### 4. **Task File Corruption (Invalid JSON)**

**Severity:** P1 - High
**Likelihood:** Medium - Concurrent writes, crashes

**Problem:**
If task file contains invalid JSON, handoff restore fails silently and no context is restored.

**Scenario:**
```
1. PreCompact writing task file
2. System crash/power loss mid-write
3. Task file contains partial JSON (invalid)
4. SessionStart tries to restore
5. JSONDecodeError caught, task silently skipped
```

**Evidence:**
```python
# SessionStart_handoff_restore.py:592-593
except (json.JSONDecodeError, OSError) as e:
    logger.debug(f"[SessionStart] Could not load handoff from task file: {e}")
    # Continues to next task file - NO ERROR REPORTED TO USER
```

**Detection:**
- Try to parse task file JSON before using it
- Validate JSON structure on write
- Checksum validation (already exists) should catch this

**Fix:**
```python
except (json.JSONDecodeError, OSError) as e:
    logger.error(f"[SessionStart] CORRUPTED task file {task_file_path}: {e}")
    # Delete corrupted file to prevent future failures
    try:
        task_file.unlink()
        logger.info(f"[SessionStart] Deleted corrupted task file: {task_file_path}")
    except OSError:
        pass
```

---

### 5. **Terminal ID Instability**

**Severity:** P1 - High
**Likelihood:** Medium - PID reuse, terminal restart

**Problem:**
If `terminal_id` changes between sessions (e.g., PID reused), handoff may be loaded from wrong terminal or fail to find `active_session`.

**Scenario:**
```
1. Session 1 in terminal_123 (PID 123) creates active_session
2. Terminal closed, PID 123 freed
3. Session 2 starts, gets PID 123 → terminal_123
4. Loads handoff from Session 1 (wrong context!)
```

**Evidence:**
```python
# PreCompact_handoff_capture.py:87-88
def detect_terminal_id() -> str:
    return f"term_{os.getpid()}"  # PID can be reused!
```

**Detection:**
- Check `saved_at` timestamp in handoff
- Verify handoff session matches current session
- Cross-check with session file timestamps

**Fix:**
Add session binding validation:
```python
# In SessionStart restore, verify session age
handoff_saved_at = handoff_data.get("saved_at")
from datetime import datetime, timedelta
saved_time = datetime.fromisoformat(handoff_saved_at)
if datetime.now(UTC) - saved_time > timedelta(hours=1):
    logger.warning(f"[SessionStart] Ignoring stale handoff from {saved_time}")
    return 0  # Skip restoration
```

---

### 6. **Race Condition: Concurrent Compaction**

**Severity:** P1 - Medium
**Likelihood:** Low - Requires multi-terminal setup

**Problem:**
If two terminals compact simultaneously, both may try to write to the same task file, causing data loss or corruption.

**Scenario:**
```
1. Terminal A writes active_session to task file
2. Terminal B writes active_session to SAME task file (overwrites!)
3. Terminal A's handoff lost
```

**Evidence:**
```python
# handoff_store.py:690
json.dump(task_data, f, indent=2)
atomic_write_with_retry(temp_path, task_file_path)
# Atomic write prevents partial writes, BUT doesn't prevent
# two terminals from overwriting each other
```

**Detection:**
- Check for multiple terminals with same task file
- Verify file modification times change frequently

**Fix:**
Add file locking:
```python
import fcntl  # Unix
# or use file lock on Windows
lock_file = task_file_path.with_suffix('.lock')
try:
    with open(lock_file, 'x') as f:  # Exclusive creation
        # Write task file
finally:
    lock_file.unlink(missing_ok=True)
```

---

## Medium Issues (P2 - Low Impact, Unlikely)

### 7. **First User Message Extraction Issues**

**Severity:** P2 - Medium
**Likelihood:** Low - Edge case in new sessions

**Problem:**
`first_user_request` extraction reads only first 20 lines, which may miss the actual first message if transcript has system messages first.

**Scenario:**
```
1. Transcript starts with 25 lines of system context
2. First user message is at line 26
3. Extraction only checks lines 0-19
4. Returns wrong system message as "first user request"
```

**Evidence:**
```python
# PreCompact_handoff_capture.py:777
for i in range(min(20, len(lines))):  # Only 20 lines!
```

**Detection:**
- Verify extracted `first_user_request` doesn't start with system markers
- Check if `type == "user"` filter is applied

**Fix:**
Use TranscriptParser instead of raw line scanning:
```python
# Use same logic as extract_last_user_message, but forward direction
entries = self.parser._get_parsed_entries()
for entry in entries:
    if entry.get("type") == "user":
        # Extract content...
        break
```

---

### 8. **Checksum Mismatch Silent Failure**

**Severity:** P2 - Medium
**Likelihood:** Low - Handoff data corruption

**Problem:**
If checksum verification fails, the error is logged but handoff is silently skipped, leaving user with no context.

**Scenario:**
```
1. Handoff captured with checksum
2. File corrupted (bit rot, disk error)
3. Checksum verification fails
4. Error logged at DEBUG level (not visible)
5. User gets no restoration context
```

**Evidence:**
```python
# SessionStart_handoff_restore.py:715-718
is_valid, error = _verify_handoff_checksum(handoff_data)
if not is_valid:
    # NOTE: Checksum failures are silent - don't spam on every session
    return 0  # Silent failure!
```

**Fix:**
```python
if not is_valid:
    logger.error(f"[SessionStart] Checksum verification failed: {error}")
    print(f"[SessionStart] Warning: Handoff data corrupted, skipping restoration")
    print(f"[SessionStart] Error: {error}")
    # Still return 0 to allow session start, but inform user
```

---

### 9. **Active Session Cleanup Failure**

**Severity:** P2 - Medium
**Likelihood:** Low - Filesystem issues

**Problem:**
If cleanup of `active_session` fails after restoration, the same handoff may be restored again in next session.

**Scenario:**
```
1. SessionStart restores handoff
2. Tries to delete active_session task
3. Filesystem error (permission, lock)
4. Task not deleted
5. Next session start restores SAME handoff again (duplicate)
```

**Evidence:**
```python
# SessionStart_handoff_restore.py:659-660
except OSError as replace_error:
    logger.debug(f"[SessionStart] Could not replace task file: {replace_error}")
    # Task not cleaned up - will be restored again!
```

**Fix:**
```python
except OSError as replace_error:
    logger.error(f"[SessionStart] Failed to clean up active_session: {replace_error}")
    # Mark task for cleanup with timestamp
    task_data["_cleanup_failed"] = True
    task_data["_cleanup_attempted_at"] = utcnow_iso()
    # Write back the marked task
    # Next SessionStart will retry cleanup
```

---

## Summary Table

| Issue | Severity | Likelihood | Impact | Detection Difficulty |
|-------|----------|------------|--------|---------------------|
| 1. Multiple Compaction Cycles | P0 | High | Wrong task context | Medium |
| 2. Transcript Missing | P0 | Medium | Stale fallback data | Easy |
| 3. Empty Transcript | P0 | Low | Stale fallback data | Easy |
| 4. Task File Corruption | P1 | Medium | No restoration | Easy |
| 5. Terminal ID Instability | P1 | Medium | Wrong terminal context | Medium |
| 6. Concurrent Compaction | P1 | Low | Data loss/corruption | Hard |
| 7. First Message Extraction | P2 | Low | Wrong first message | Easy |
| 8. Checksum Mismatch | P2 | Low | Silent restoration failure | Easy |
| 9. Cleanup Failure | P2 | Low | Duplicate restoration | Medium |

---

## Recommended Actions

### Immediate (P0 Issues)
1. **Fix Issue #1:** Validate task_name matches current context before creating active_session
2. **Fix Issue #2:** Add explicit transcript validation before capture
3. **Fix Issue #3:** Skip handoff capture for empty transcripts

### Short-term (P1 Issues)
4. **Fix Issue #4:** Add corrupted task file cleanup
5. **Fix Issue #5:** Add session age validation in SessionStart
6. **Fix Issue #6:** Add file locking for task file writes

### Long-term (P2 Issues)
7. **Fix Issue #7:** Use TranscriptParser for first_user_request
8. **Fix Issue #8:** Improve checksum error visibility
9. **Fix Issue #9:** Add retry mechanism for cleanup failures

---

## Testing Recommendations

For each issue, create test scenarios:

1. **Multiple compactions:** Create test that compacts 3x with different tasks
2. **Missing transcript:** Delete transcript file before compaction
3. **Empty transcript:** Create transcript with only system messages
4. **Corrupted task file:** Inject invalid JSON into task file
5. **Terminal ID reuse:** Simulate PID reuse scenario
6. **Concurrent writes:** Multi-threaded compaction test
7. **First message extraction:** Transcript with 25+ lines of context
8. **Checksum failure:** Manually corrupt handoff checksum
9. **Cleanup failure:** Mock filesystem error during cleanup

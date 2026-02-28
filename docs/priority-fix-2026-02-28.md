# Handoff Priority System Fix - 2026-02-28

## Problem

The handoff system was capturing **stale `last_user_message`** from cached files instead of the actual last user message from the transcript.

### Example of the Bug

**User's actual last command:**
```
"read https://mcpmarket.com/ko/tools/skills/skill-auto-updater and https://github.com/BayramAnnakov/claude-reflect"
```

**What handoff captured (WRONG):**
```
"yes, create the script"  // From earlier in conversation
```

**Result:** After compaction/restoration, the LLM would work on the wrong task because the handoff contained stale data.

## Root Cause

The `PreCompact_handoff_capture.py` hook used this priority system (WRONG):

```python
# OLD (WRONG) Priority:
1. active_command file (can be stale)
2. blocker.description (can be from earlier)
3. hook_input (can be stale)
4. TranscriptParser (CORRECT but never reached!)
```

The problem: **Options 1-3 all succeed** but return stale data from earlier in the conversation. The TranscriptParser (Option 4) would return the correct data but is **never reached** because earlier options already succeeded.

## Solution

**Reversed the priority order** to make TranscriptParser (source of truth) the first option:

```python
# NEW (CORRECT) Priority:
1. TranscriptParser (scans actual transcript - most reliable)
2. hook_input (current context)
3. active_command file (can be stale)
4. blocker.description (fallback)
```

## Why This Works

1. **TranscriptParser scans the actual transcript** - Returns the REAL last user message
2. **Fallbacks preserved** - If transcript parsing fails, falls back to hook_input, then cached files
3. **No stale data** - Transcript is always fresh, not affected by earlier conversation state

## Code Changes

**File:** `P:/packages/handoff/src/handoff/hooks/PreCompact_handoff_capture.py`

**Lines:** 1050-1096

**Change:** Reordered the 4 priority options to put TranscriptParser first

## Testing

Created comprehensive tests in `tests/test_precompact_priority_fix.py`:

1. ✅ `test_priority_order_is_correct` - Verifies TranscriptParser is Option 1
2. ✅ `test_transcript_parser_called_first` - Verifies TranscriptParser is called before active_command file
3. ✅ `test_fallback_logic_is_preserved` - Verifies fallback guards are in place
4. ✅ `test_comment_is_updated` - Verifies comments reflect new priority
5. ✅ All existing tests still pass (13 integration tests)

## Impact

**Before Fix:**
- Handoff could contain stale `original_user_request`
- After restoration, LLM works on wrong task
- User confusion: "That's not what I asked you to do"

**After Fix:**
- Handoff always contains authentic last user message from transcript
- After restoration, LLM has correct context
- Seamless handoff across compaction events

## Related Issues

This fix resolves the core issue where the handoff system was demonstrating incorrect restoration in the chat transcript provided by the user.

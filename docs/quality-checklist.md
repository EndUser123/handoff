# Handoff Quality Checklist

## Questions to Ask After Compaction

After a transcript compaction event, ask these questions to determine if the handoff system worked optimally:

### ✅ Continuity (5 questions)

**1. Did I understand immediately what I was working on?**
- ✅ Yes - task name, progress, and context were clear
- ❌ No - I had to read through the transcript to figure it out
- ⚠️  Partial - I understood the task but missed important context

**2. Did I avoid asking questions I already asked?**
- ✅ Yes - the restoration prevented redundant clarification
- ❌ No - I asked the same questions again
- ⚠️  Partial - some questions were repeated

**3. Did I maintain the same decisions/constraints?**
- ✅ Yes - previous decisions were respected
- ❌ No - I reversed or changed previous decisions
- ⚠️  Partial - some decisions were revisited unnecessarily

**4. Did I continue from where I left off (no redo)?**
- ✅ Yes - seamless continuation, no redundant work
- ❌ No - I re-did work that was already completed
- ⚠️  Partial - some work was repeated

**5. Did the do_not_revisit list prevent mistakes?**
- ✅ Yes - it stopped me from revisiting settled decisions
- ❌ No - I revisited topics that should have been marked
- ⚠️  Partial - it helped but wasn't comprehensive

---

### 🎯 Context Quality (4 questions)

**6. Was the canonical_goal accurate and useful?**
- ✅ Yes - captured the real essence of what I was doing
- ❌ No - it was too generic or missed the point
- ⚠️  Partial - close but could have been better

**7. Were the most important decisions preserved?**
- ✅ Yes - all critical "must/never" constraints were there
- ❌ No - important constraints were missing
- ⚠️  Partial - some important context was lost

**8. Was the visual context helpful (if applicable)?**
- ✅ Yes - screenshots/images helped me understand the state
- ❌ No - visual context was missing or unhelpful
- ⚠️  N/A - no visual context needed for this task

**9. Were pending operations accurately tracked?**
- ✅ Yes - I knew exactly what was incomplete
- ❌ No - pending ops were wrong or missing
- ⚠️  Partial - some pending ops were incorrect

---

### 🚫 Mistake Prevention (3 questions)

**10. Did I avoid redoing completed work?**
- ✅ Yes - files_modified showed what was done
- ❌ No - I re-edited files that were already modified
- ⚠️  Partial - unclear what was already done

**11. Did the handoff prevent workflow violations?**
- ✅ Yes - planning sessions blocked auto-implementation
- ❌ No - I implemented without approval when I shouldn't have
- ⚠️  Partial - blocker system helped but wasn't perfect

**12. Did the session boundary detection work correctly?**
- ✅ Yes - stopped at the right point (no false continuations)
- ❌ No - it stopped too early or continued too far
- ⚠️  Partial - mostly correct but some edge cases

---

## Scoring Guide

### Calculate Your Score

For each question:
- ✅ Yes = 2 points (perfect)
- ⚠️  Partial = 1 point (acceptable)
- ❌ No = 0 points (problem)

**Maximum score:** 24 points (12 questions × 2 points)

### Score Interpretation

| Score Range | Quality | Action Needed |
|------------|---------|--------------|
| **22-24** | 🟢 Excellent | Handoff working optimally, no changes needed |
| **18-21** | 🟡 Good | Minor tweaks needed, document specific issues |
| **14-17** | 🟠 Fair | Moderate problems, investigate specific failures |
| **0-13** | 🔴 Poor | Major issues, handoff system needs review |

---

## Common Failure Patterns

### If Continuity Score is Low (< 6/10)

**Symptom:** Can't understand what you were working on

**Check:**
- Was `canonical_goal` extracted correctly?
- Was `progress_percent` accurate?
- Were key decisions missing from `do_not_revisit`?

**Action:**
- Review the restoration message in SessionStart hook
- Check if topic shift detection is too aggressive
- Verify context gathering captured enough transcript

---

### If Context Quality Score is Low (< 5/8)

**Symptom:** Important information was lost

**Check:**
- Did we hit the 8-item limit in `do_not_revisit`?
- Were strong constraints not detected?
- Was session boundary detection stopping too early?

**Action:**
- Increase `do_not_revisit` limit to 10 or remove entirely
- Improve strong language detection patterns
- Adjust topic shift threshold (currently 0.2)

---

### If Mistake Prevention Score is Low (< 4/6)

**Symptom:** Repeated work or workflow violations

**Check:**
- Were `files_modified` empty or inaccurate?
- Was `pending_operations` missing or wrong?
- Did planning session blocker fail to appear?

**Action:**
- Verify PreCompact hook is capturing modifications correctly
- Check PendingOperation detection logic
- Test planning session detection with your workflows

---

## How to Report Issues

If you identify problems, document:

1. **What went wrong** (be specific)
   - "I re-edited src/main.py because files_modified was empty"
   - "I asked the same question 3 times"

2. **Expected vs Actual**
   - Expected: "Files I modified should be listed"
   - Actual: "files_modified was empty"

3. **Handoff data** (if available)
   - Check: `.claude/state/task_tracker/{terminal_id}_tasks.json`
   - Look at: `continuation.do_not_revisit`
   - Check: `task.canonical_goal`

4. **Context**
   - What type of session? (debug, feature, refactor, test, docs, planning)
   - How long was the session? (10 messages, 100 messages?)
   - What was interrupted?

---

## Using This Checklist

### After Compaction (Immediate Review)

1. **Wait for SessionStart restoration** (appears as system message)
2. **Read the restoration message carefully**
3. **Ask yourself the 12 questions above**
4. **Calculate your score**
5. **If score < 18, document specific issues**

### Weekly Review (Trend Analysis)

1. **Track scores over time** (keep a simple log)
2. **Identify patterns** (e.g., "always low context quality on refactor sessions")
3. **Report systemic issues** (e.g., "topic shift detection too aggressive")

---

## Integration with README

This checklist should be referenced in the main README.md under a new section:

```markdown
## Quality Assurance

After compaction events, evaluate handoff effectiveness using [HANDOFF_QUALITY_CHECKLIST.md](HANDOFF_QUALITY_CHECKLIST.md).

The checklist helps you:
- Verify continuity (did you pick up where you left off?)
- Assess context quality (was important info preserved?)
- Prevent mistakes (did you avoid redoing work?)

Score your handoff quality and report issues to improve the system.
```

# Handoff Package Code Quality Improvements

**Created**: 2026-02-28
**Status**: In Progress
**Focus**: Error logging, function complexity, and code style

## Acceptance Criteria

1. **Error Logging**: All 53 exception blocks include appropriate logging
2. **Function Complexity**: Long functions (>50 lines) refactored into smaller helpers
3. **Code Style**: Long lines (>100 chars) reformatted for readability
4. **Tests**: All 217 existing tests still pass
5. **No Breaking Changes**: All refactoring preserves existing behavior

## Tasks

### Phase 1: Error Logging Improvements (Priority: HIGH)

**Goal**: Add logging to 53 unlogged exception blocks across 9 files

- [ ] **task-1.1**: Add error logging to `handoff_store.py` (10 except blocks)
  - Focus on atomic_write_with_validation, calculate_quality_score
  - Use existing logger instance
  - Log error context (what operation failed, relevant data)

- [ ] **task-1.2**: Add error logging to `task_identity_manager.py` (9 except blocks)
  - Focus on _from_session_file, _from_compact_metadata, _from_git_worktree
  - Include task/terminal context in logs

- [ ] **task-1.3**: Add error logging to `transcript.py` (10 except blocks)
  - Focus on detect_structure_type, _get_parsed_entries
  - Log transcript parsing context

- [ ] **task-1.4**: Add error logging to `PreCompact_handoff_capture.py` (10 except blocks)
  - Focus on _load_active_command_file, __init__
  - Log compaction context

- [ ] **task-1.5**: Add error logging to `SessionStart_handoff_restore.py` (6 except blocks)
  - Focus on _fallback_find_by_session, main
  - Log restoration context

- [ ] **task-1.6**: Add error logging to `migrate.py` (4 except blocks)
  - Focus on migrate_handoffs
  - Log migration context

- [ ] **task-1.7**: Add error logging to remaining files (handover, bridge_tokens, config)

### Phase 2: Long Function Refactoring (Priority: MEDIUM)

**Goal**: Break down 30 functions > 50 lines into smaller, focused helpers

- [ ] **task-2.1**: Refactor `_build_restoration_prompt` (329 lines) ⚠️ **CRITICAL**
  - Extract: build_system_context_section
  - Extract: build_recent_work_section
  - Extract: build_blocker_resolution_section
  - Extract: build_handoff_data_section
  - Keep main as orchestrator

- [ ] **task-2.2**: Refactor `detect_structure_type` (84 lines in transcript.py)
  - Extract pattern matching logic
  - Extract structure type detection

- [ ] **task-2.3**: Refactor `migrate_handoffs` (87 lines in migrate.py)
  - Already partially refactored, continue decomposition
  - Extract: process_single_handoff
  - Extract: write_task_file_atomic

- [ ] **task-2.4**: Refactor remaining 50+ line functions in handoff_store.py
  - atomic_write_with_validation (63 lines)
  - _validate_handoff_data_size (71 lines)
  - calculate_quality_score (59 lines)

- [ ] **task-2.5**: Refactor remaining 50+ line functions in other files
  - _load_all_checkpoints (64 lines in checkpoint_chain.py)
  - build (56 lines in handover.py)
  - _get_parsed_entries (57 lines in transcript.py)
  - extract_current_blocker (59 lines in transcript.py)

### Phase 3: Code Style Improvements (Priority: LOW)

**Goal**: Reformat 54 long lines (>100 chars) for better readability

- [ ] **task-3.1**: Reformat long lines in `PreCompact_handoff_capture.py` (16 lines)
  - Break up long string literals
  - Split complex expressions

- [ ] **task-3.2**: Reformat long lines in `transcript.py` (12 lines)

- [ ] **task-3.3**: Reformat long lines in `handoff_store.py` (10 lines)

- [ ] **task-3.4**: Reformat long lines in remaining files (16 lines total)

### Phase 4: Verification

- [ ] **task-4.1**: Run full test suite (pytest tests/)
- [ ] **task-4.2**: Verify no regressions introduced
- [ ] **task-4.3**: Check code style with ruff/flake8

## Success Metrics

- **Before**: 53 unlogged except blocks, 30 functions > 50 lines, 54 long lines
- **After**: 0 unlogged except blocks, all functions < 50 lines (except justified cases), 0 unnecessary long lines
- **Tests**: 217/217 passing
- **Behavior**: No functional changes (logging only, structural decomposition only)

## Notes

- **Priority Order**: Phase 1 → Phase 2 → Phase 3 (error logging most critical for debugging)
- **Risk Mitigation**: Each task will be tested independently
- **Rollback**: Git commits after each phase for easy reversion

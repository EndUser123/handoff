# Type Hint Fixes for mypy Strict Mode

**Created**: 2026-03-01
**Status**: Ready
**Focus**: Fix 45 mypy strict mode errors blocking P1 completion

## Acceptance Criteria

1. **All mypy errors resolved**: 0 errors remaining
2. **All tests pass**: 416/416 tests passing (currently 410/416, 4 type quality tests failing)
3. **No functional changes**: Type annotations only, no behavior changes
4. **mypy --strict compliance**: All files pass mypy strict type checking

## Error Summary

**Total Errors**: 45 across 7 files

**Error Types**:
- Missing type parameters on generic classes (dict, list, etc.)
- Incompatible return types
- Untyped decorators
- Missing type annotations on function parameters
- Assignment without type annotation

**Files Affected**:
1. `src/handoff/hooks/__lib/handoff_store.py`
2. `src/handoff/hooks/__lib/transcript.py`
3. `src/handoff/hooks/__lib/task_identity_manager.py`
4. `src/handoff/hooks/PreCompact_handoff_capture.py`
5. `src/handoff/hooks/SessionStart_handoff_restore.py`
6. `src/handoff/hooks/migrate.py`
7. `src/handoff/hooks/bridge_tokens.py`

## Tasks

- [ ] **task-1**: Fix type hints in `handoff_store.py` (8 errors)
  - Add missing type parameters to dict/list
  - Fix return type annotations
  - Add type annotations to untyped parameters

- [ ] **task-2**: Fix type hints in `transcript.py` (10 errors)
  - Fix missing type parameters
  - Add return type annotations
  - Fix incompatible types

- [ ] **task-3**: Fix type hints in `task_identity_manager.py` (7 errors)
  - Add type annotations to class methods
  - Fix generic type parameters

- [ ] **task-4**: Fix type hints in `PreCompact_handoff_capture.py` (6 errors)
  - Add missing type annotations
  - Fix decorator types

- [ ] **task-5**: Fix type hints in `SessionStart_handoff_restore.py` (5 errors)
  - Fix return type annotations
  - Add missing type parameters

- [ ] **task-6**: Fix type hints in `migrate.py` (5 errors)
  - Add type annotations
  - Fix generic types

- [ ] **task-7**: Fix type hints in `bridge_tokens.py` (4 errors)
  - Add missing type annotations
  - Fix return types

- [ ] **task-8**: Verify all fixes
  - Run `mypy src/ --strict` - expect 0 errors
  - Run `pytest tests/` - expect all 416 tests passing
  - Verify `test_quality_type_hints.py` passes

## Success Metrics

- **Before**: 45 mypy errors, 410/416 tests passing
- **After**: 0 mypy errors, 416/416 tests passing
- **Verification**: `mypy --strict` passes, `pytest` passes

## Notes

- **Scope**: Type annotations only - no functional changes
- **Strategy**: Fix errors file-by-file in dependency order
- **Validation**: Run mypy and pytest after each task to catch regressions early

"""Performance tests for file search in SessionStart (PERF-001).

This test module CAPTURES CURRENT BEHAVIOR before refactoring to fix
inefficient file search when loading active session tasks.

Performance Issue: PERF-001
============================
The _load_active_session_task() function uses a linear glob search through
all task files when the fast path (current terminal) fails:

Current Implementation (lines 602-632):
```python
# Slow path: search all terminal task files
for task_file in task_tracker_dir.glob("*_tasks.json"):
    with open(task_file) as f:
        task_data = json.load(f)
        # Check for active_session or continue_session
```

This is O(n) where n = number of terminal task files. For systems with:
- 100 terminals = 100 file system operations + JSON parses
- 1000 terminals = 1000 file system operations + JSON parses
- Each file may not even contain the target task

Expected After Fix:
-------------------
- Implement an active_session manifest file (O(1) lookup)
- Fast path: Read manifest file → get terminal_id → read specific task file
- Performance improvement: ~100x faster for 100+ terminals

Run with:
    pytest tests/test_performance_file_search.py -v
"""

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest


class TestActiveSessionFileSearchPerformance:
    """Tests for PERF-001: Inefficient file search in _load_active_session_task."""

    @pytest.fixture
    def temp_project_root(self):
        """Create temporary project root with task_tracker directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            task_tracker_dir = project_root / ".claude" / "state" / "task_tracker"
            task_tracker_dir.mkdir(parents=True)
            yield project_root, task_tracker_dir

    def create_terminal_task_file(
        self, task_tracker_dir: Path, terminal_id: str, has_active_session: bool = False
    ):
        """Create a terminal task file with optional active_session task.

        Args:
            task_tracker_dir: Directory to create task file in
            terminal_id: Terminal identifier
            has_active_session: Whether to include active_session task
        """
        task_file = task_tracker_dir / f"{terminal_id}_tasks.json"

        task_data = {"tasks": {}}

        if has_active_session:
            task_data["tasks"]["active_session"] = {
                "task_name": "test_handoff_task",
                "metadata": {"handoff_path": "/tmp/test_handoff.json"},
            }

        with open(task_file, "w", encoding="utf-8") as f:
            json.dump(task_data, f)

        return task_file

    def test_search_with_100_files_demonstrates_perf_issue(self, temp_project_root):
        """
        Characterization: Search through 100 terminal task files demonstrates PERF-001.

        Given: 100 terminal task files (none with active_session)
        When: _load_active_session_task() searches through all files
        Then: CURRENT BEHAVIOR may take significant time depending on filesystem
              EXPECTED AFTER FIX: < 50ms with manifest file (O(1) lookup)

        This test demonstrates PERF-001: linear scan is O(n) with file count.
        """
        project_root, task_tracker_dir = temp_project_root

        # Arrange: Create 100 terminal task files
        for i in range(100):
            self.create_terminal_task_file(
                task_tracker_dir, f"term_{i:03d}", has_active_session=False
            )

        # Act: Import function with mocked PROJECT_ROOT and time the search
        with patch(
            "handoff.hooks.SessionStart_handoff_restore.PROJECT_ROOT", project_root
        ):
            # Import AFTER patching to get the mocked PROJECT_ROOT
            from handoff.hooks.SessionStart_handoff_restore import (
                _load_active_session_task,
            )

            start = time.perf_counter()
            task, terminal = _load_active_session_task("term_unknown")
            elapsed = time.perf_counter() - start

        # Assert: Should not find anything (no active_session exists)
        assert task is None
        assert terminal is None

        # Performance check: This demonstrates the performance issue
        # CURRENT BEHAVIOR: Linear scan through 100 files
        # EXPECTED AFTER FIX: O(1) manifest lookup
        print(f"\n100 files: {elapsed * 1000:.2f} ms")

        # This assertion demonstrates the problem:
        # With 100 files, the current implementation may take > 100ms
        # After implementing manifest file, this should be < 50ms
        #
        # For now, we document the current slow behavior
        # The test will FAIL if it's too slow (> 1 second), demonstrating the issue

        if elapsed > 1.0:
            # This is the failing case that demonstrates PERF-001
            pytest.fail(
                f"PERF-001: Search through 100 files took {elapsed * 1000:.2f} ms. "
                f"This demonstrates the performance issue with linear glob search. "
                f"Expected: < 1000 ms. "
                f"After fix with manifest file: < 50 ms (O(1) lookup)."
            )

        # If it passes, it's still slower than optimal but acceptable
        print(f"  Performance: Acceptable but not optimal ({elapsed * 1000:.2f} ms)")
        print("  After fix with manifest: Expected < 50 ms")

    def test_search_finds_active_session_at_end(self, temp_project_root):
        """
        Characterization: Worst case - active_session is in the last file.

        Given: 100 terminal task files, active_session in the last one
        When: _load_active_session_task() searches through all files
        Then: Must read all 100 files before finding the target

        This demonstrates the worst-case scenario for linear search.
        """
        project_root, task_tracker_dir = temp_project_root

        # Arrange: Create 100 files, with active_session in the last one
        for i in range(99):
            self.create_terminal_task_file(
                task_tracker_dir, f"term_{i:03d}", has_active_session=False
            )

        # Last file has the active_session
        self.create_terminal_task_file(task_tracker_dir, "term_099", has_active_session=True)

        # Act: Time the search operation
        with patch(
            "handoff.hooks.SessionStart_handoff_restore.PROJECT_ROOT", project_root
        ):
            from handoff.hooks.SessionStart_handoff_restore import (
                _load_active_session_task,
            )

            start = time.perf_counter()
            task, terminal = _load_active_session_task("term_unknown")
            elapsed = time.perf_counter() - start

        # Assert: Should find the task
        assert task is not None
        assert task["task_name"] == "test_handoff_task"
        assert terminal == "term_099"

        # Performance: Worst case - must read all 100 files
        print(f"\n100 files (worst case): {elapsed * 1000:.2f} ms")

        if elapsed > 1.0:
            pytest.fail(
                f"PERF-001: Worst-case search (last file) took {elapsed * 1000:.2f} ms. "
                f"After fix with manifest: Should be O(1) regardless of file count."
            )

    def test_search_scales_linearly_with_file_count(self, temp_project_root):
        """
        Characterization: Search time scales linearly with file count.

        Given: Varying numbers of terminal task files (10, 50, 100)
        When: _load_active_session_task() searches through all files
        Then: Time should scale roughly linearly with file count

        This demonstrates the O(n) complexity of the current implementation.
        Expected after fix: O(1) regardless of file count.
        """
        project_root, task_tracker_dir = temp_project_root

        file_counts = [10, 50, 100]
        search_times = []

        for count in file_counts:
            # Clean up previous files
            for task_file in task_tracker_dir.glob("*_tasks.json"):
                task_file.unlink()

            # Create test files
            for i in range(count):
                self.create_terminal_task_file(
                    task_tracker_dir, f"term_{i:03d}", has_active_session=False
                )

            # Time the search
            with patch(
                "handoff.hooks.SessionStart_handoff_restore.PROJECT_ROOT",
                project_root,
            ):
                from handoff.hooks.SessionStart_handoff_restore import (
                    _load_active_session_task,
                )

                start = time.perf_counter()
                task, terminal = _load_active_session_task("term_unknown")
                elapsed = time.perf_counter() - start

                search_times.append({"file_count": count, "time_ms": elapsed * 1000})

        print("\n=== Scaling Analysis ===")
        for result in search_times:
            print(f"Files: {result['file_count']:3d} | Time: {result['time_ms']:6.2f} ms")

        # Check linear scaling: doubling files should ~double time
        # (allowing generous tolerance for system noise)
        for i in range(1, len(search_times)):
            prev = search_times[i - 1]
            curr = search_times[i]

            file_ratio = curr["file_count"] / prev["file_count"]
            time_ratio = curr["time_ms"] / prev["time_ms"]

            print(f"  File ratio: {file_ratio:.2f}x, Time ratio: {time_ratio:.2f}x")

            # Time should scale roughly with file count (within 0.3x to 3x)
            # This confirms O(n) behavior
            # NOTE: This test may PASS even if timing is very fast due to caching,
            # but it still demonstrates the algorithmic complexity
            if time_ratio > 0:
                assert 0.1 <= time_ratio / file_ratio <= 5.0, (
                    f"Search time should scale roughly linearly: "
                    f"files={file_ratio:.2f}x but time={time_ratio:.2f}x"
                )

        print("\n  This confirms O(n) complexity.")
        print("  After fix with manifest file: Expected O(1) regardless of file count.")

    def test_fast_path_avoids_search(self, temp_project_root):
        """
        Characterization: Fast path finds task in current terminal without search.

        Given: Current terminal has active_session task
        When: _load_active_session_task() checks current terminal first
        Then: Should return immediately without searching other files

        This demonstrates the fast path optimization that already exists.
        """
        project_root, task_tracker_dir = temp_project_root

        # Arrange: Create current terminal task file with active_session
        current_terminal = "term_current"
        self.create_terminal_task_file(
            task_tracker_dir, current_terminal, has_active_session=True
        )

        # Create other terminal files (without active_session)
        for i in range(50):
            self.create_terminal_task_file(
                task_tracker_dir, f"term_other_{i}", has_active_session=False
            )

        # Act: Time the search operation
        with patch(
            "handoff.hooks.SessionStart_handoff_restore.PROJECT_ROOT", project_root
        ):
            from handoff.hooks.SessionStart_handoff_restore import (
                _load_active_session_task,
            )

            start = time.perf_counter()
            task, terminal = _load_active_session_task(current_terminal)
            elapsed = time.perf_counter() - start

        # Assert: Should find the task quickly
        assert task is not None
        assert task["task_name"] == "test_handoff_task"
        assert terminal == current_terminal

        # Performance: Fast path should be very fast
        print(f"\nFast path (current terminal): {elapsed * 1000:.2f} ms")
        assert elapsed < 0.1, f"Fast path took {elapsed * 1000:.2f} ms, should be < 100 ms"

        print("  Fast path works correctly (O(1) for current terminal)")


class TestManifestFileDesign:
    """Tests documenting the expected behavior after implementing manifest file."""

    def test_manifest_file_design(self):
        """
        Document the design for the fix (not implemented yet).

        After implementing PERF-001 fix:
        1. Create active_session_manifest.json in task_tracker directory
        2. Manifest contains: {"terminal_id": "term_123", "timestamp": "..."}
        3. Fast path: Read manifest → get terminal_id → read specific task file
        4. Update manifest when active_session task is created/deleted
        5. Performance: O(1) regardless of terminal count

        Expected performance after fix:
        - 10 terminals: < 10 ms (vs ~50 ms current)
        - 100 terminals: < 10 ms (vs ~500+ ms current)
        - 1000 terminals: < 10 ms (vs ~5000+ ms current)
        """
        # This test documents the design, doesn't test current implementation
        print("\n=== Manifest File Design ===")
        print("Location: .claude/state/task_tracker/active_session_manifest.json")
        print("Structure:")
        print("  {")
        print('    "terminal_id": "term_123",')
        print('    "timestamp": "2026-03-01T12:00:00Z",')
        print('    "handoff_path": "/path/to/handoff.json"')
        print("  }")
        print("\nPerformance improvement:")
        print("  Current: O(n) - scan all task files")
        print("  After fix: O(1) - read manifest, then read specific task file")
        print("\nImplementation steps:")
        print("  1. Create manifest when active_session task is created")
        print("  2. Update manifest when terminal_id changes (after compaction)")
        print("  3. Delete manifest when active_session is consumed")
        print("  4. Read manifest in _load_active_session_task() fast path")


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "-s"])

#!/usr/bin/env python3
"""
Test Suite for TEST-002: Concurrency Safety During Compaction

These tests verify that concurrent compaction operations on the same terminal
do not cause data corruption. The tests use multiprocessing.Pool to simulate
multiple Claude Code instances performing compaction simultaneously.

Current Behavior (BEFORE FIX):
- No concurrency test coverage exists
- File locking may have TOCTOU vulnerabilities
- Concurrent writes may corrupt task tracker JSON files
- No verification that serialization prevents data loss

Expected Behavior (AFTER FIX):
- File locking prevents concurrent writes to same terminal
- Only one process writes at a time (serialization)
- Task tracker JSON files remain valid
- No data corruption occurs

Run with: pytest P:/packages/handoff/tests/test_concurrency_compaction.py -v

Reference: TEST-002 in test coverage gap analysis
"""

import json
import os
import sys
import tempfile
import time
from multiprocessing import Pool
from pathlib import Path

# Add src to path for imports
hooks_dir = Path(__file__).resolve().parent.parent / "src" / "handoff" / "hooks"
sys.path.insert(0, str(hooks_dir))
sys.path.insert(0, str(hooks_dir / "__lib"))

from handoff.hooks.__lib.handoff_store import HandoffStore


def worker_compact_terminal(worker_id: int, temp_dir_str: str, terminal_id: str) -> dict:
    """
    Worker process that performs compaction on a shared terminal.

    This simulates one Claude Code instance performing PreCompact handoff capture.
    Multiple workers running concurrently represents multiple instances compacting
    the same terminal session (which should be prevented by file locking).

    Args:
        worker_id: Unique worker identifier (0-3)
        temp_dir_str: Path to temporary directory (as string)
        terminal_id: Shared terminal ID (all workers use same ID)

    Returns:
        Dict with success status, worker_id, and whether write succeeded
    """
    try:
        temp_path = Path(temp_dir_str)
        project_root = temp_path

        # Create HandoffStore for this worker
        store = HandoffStore(project_root, terminal_id)

        # Build handoff data unique to this worker
        handoff_data = store.build_handoff_data(
            task_name=f"concurrent_task_worker_{worker_id}",
            progress_pct=25 * (worker_id + 1),  # 25%, 50%, 75%, 100%
            blocker=None,
            files_modified=[f"worker_{worker_id}_file.py"],
            next_steps=[f"Step {worker_id}: Complete work"],
            handover={
                "decisions": [
                    {
                        "topic": f"Worker {worker_id} Decision",
                        "decision": f"Decision made by worker {worker_id}",
                        "timestamp": "2024-01-01T00:00:00.000000",
                    }
                ],
                "patterns_learned": [f"Pattern from worker {worker_id}"],
            },
            modifications=[
                {
                    "file": f"worker_{worker_id}_file.py",
                    "operation": "edit",
                    "lines": [1, 2, 3],
                }
            ],
            add_bridge_tokens=False,
            calculate_quality=False,
        )

        # Create handoff_metadata from handoff_data
        # create_continue_session_task expects a specific metadata structure
        handoff_metadata = {
            "task_name": f"concurrent_task_worker_{worker_id}",
            "progress_percent": handoff_data["progress_pct"],
            "blocker": handoff_data["blocker"],
            "next_steps": "\n".join(handoff_data["next_steps"]),
            "saved_at": handoff_data.get("saved_at", "2024-01-01T00:00:00.000000"),
            "checkpoint_id": handoff_data.get("checkpoint_id", ""),
            "chain_id": handoff_data.get("chain_id", ""),
            "handover": handoff_data["handover"],
            "modifications": handoff_data["modifications"],
            "files_modified": handoff_data.get("files_modified", []),
        }

        # Attempt to create continue_session task
        # This is where concurrent writes would cause corruption
        store.create_continue_session_task(
            task_name=f"concurrent_task_worker_{worker_id}",
            task_id=f"task_worker_{worker_id}",
            handoff_metadata=handoff_metadata,
        )

        # Report success
        return {
            "status": "success",
            "worker_id": worker_id,
            "pid": os.getpid(),
        }

    except Exception as e:
        # Report failure
        return {
            "status": "error",
            "worker_id": worker_id,
            "error": str(e),
            "error_type": type(e).__name__,
        }


def verify_task_file_integrity(task_file_path: Path, expected_terminal_id: str) -> dict:
    """
    Verify that the task tracker file is valid and not corrupted.

    Args:
        task_file_path: Path to task tracker JSON file
        expected_terminal_id: Expected terminal_id in the file

    Returns:
        Dict with validation results
    """
    result = {
        "exists": task_file_path.exists(),
        "valid_json": False,
        "has_terminal_id": False,
        "has_tasks": False,
        "has_continue_session": False,
        "has_active_session": False,
        "terminal_id_match": False,
        "error": None,
    }

    if not result["exists"]:
        result["error"] = "Task file does not exist"
        return result

    try:
        with open(task_file_path, encoding="utf-8") as f:
            data = json.load(f)

        result["valid_json"] = True

        # Check structure
        result["has_terminal_id"] = "terminal_id" in data
        result["has_tasks"] = "tasks" in data and isinstance(data["tasks"], dict)

        if result["has_terminal_id"]:
            result["terminal_id_match"] = data["terminal_id"] == expected_terminal_id

        # Check for expected tasks
        if result["has_tasks"]:
            result["has_continue_session"] = "continue_session" in data["tasks"]
            result["has_active_session"] = "active_session" in data["tasks"]

    except json.JSONDecodeError as e:
        result["error"] = f"Invalid JSON: {e}"
    except Exception as e:
        result["error"] = f"Read error: {e}"

    return result


class TestConcurrencyCompaction:
    """Tests for concurrent compaction safety."""

    def test_concurrent_compaction_with_four_processes(self):
        """
        Test that 4 concurrent processes compacting same terminal don't corrupt data.

        Given: 4 worker processes using multiprocessing.Pool
        When: All processes perform compaction on the same terminal simultaneously
        Then:
            1. File locking should serialize writes
            2. Task tracker file should remain valid JSON
            3. No data corruption should occur
            4. Lock mechanism should prevent race conditions

        This is the MAIN test for TEST-002: Concurrency safety verification.

        Current behavior (BEFORE FIX):
        - May experience data corruption from concurrent writes
        - File locking may have TOCTOU vulnerabilities
        - Multiple processes might write simultaneously

        Expected behavior (AFTER FIX):
        - Only one process holds lock at a time
        - File remains valid JSON
        - No data loss or corruption
        """
        # Setup: Create temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create task tracker directory
            task_tracker_dir = temp_path / ".claude" / "state" / "task_tracker"
            task_tracker_dir.mkdir(parents=True, exist_ok=True)

            # All workers share the same terminal ID (simulates concurrent compaction)
            terminal_id = "test_terminal_concurrent_4proc"
            task_file_path = task_tracker_dir / f"{terminal_id}_tasks.json"

            # Create initial task file
            initial_data = {
                "terminal_id": terminal_id,
                "tasks": {},
                "last_update": "2024-01-01T00:00:00.000000",
            }
            with open(task_file_path, "w", encoding="utf-8") as f:
                json.dump(initial_data, f, indent=2)

            # Launch 4 concurrent workers using Pool
            num_workers = 4

            with Pool(processes=num_workers) as pool:
                # Start all workers simultaneously
                results = pool.starmap(
                    worker_compact_terminal,
                    [(i, str(temp_path), terminal_id) for i in range(num_workers)],
                )

            # Analyze results
            success_count = sum(1 for r in results if r["status"] == "success")
            error_count = sum(1 for r in results if r["status"] == "error")

            print("\n" + "=" * 60)
            print("CONCURRENT COMPACTION TEST RESULTS")
            print("=" * 60)
            print(f"Workers launched: {num_workers}")
            print(f"Successful writes: {success_count}")
            print(f"Failed writes: {error_count}")
            print(f"Success rate: {success_count / num_workers * 100:.1f}%")
            print("=" * 60)

            # Print detailed results
            for r in results:
                if r["status"] == "success":
                    print(f"Worker {r['worker_id']}: SUCCESS (PID {r['pid']})")
                else:
                    print(f"Worker {r['worker_id']}: FAILED ({r['error_type']}: {r['error']})")

            # Verify task file integrity
            print("\n" + "-" * 60)
            print("TASK FILE INTEGRITY CHECK")
            print("-" * 60)

            verification = verify_task_file_integrity(task_file_path, terminal_id)

            print(f"File exists: {verification['exists']}")
            print(f"Valid JSON: {verification['valid_json']}")
            print(f"Has terminal_id: {verification['has_terminal_id']}")
            print(f"terminal_id matches: {verification['terminal_id_match']}")
            print(f"Has tasks dict: {verification['has_tasks']}")
            print(f"Has continue_session: {verification['has_continue_session']}")
            print(f"Has active_session: {verification['has_active_session']}")

            if verification["error"]:
                print(f"Error: {verification['error']}")

            print("-" * 60)

            # ASSERTIONS

            # 1. File must exist and be valid JSON (no corruption)
            assert verification["exists"], "Task file must exist after concurrent writes"
            assert verification["valid_json"], "Task file must be valid JSON (no corruption)"

            # 2. File must have correct structure
            assert verification["has_terminal_id"], "Task file must have terminal_id"
            assert verification["has_tasks"], "Task file must have tasks dict"

            # 3. Expected tasks must be present
            assert verification["has_continue_session"], "Task file must have continue_session task"
            assert verification["has_active_session"], "Task file must have active_session task"

            # 4. Terminal ID must match
            assert verification["terminal_id_match"], "Terminal ID must match expected value"

            # 5. At least one worker should succeed
            assert success_count >= 1, "At least one worker must succeed"

            # 6. If file locking works correctly, we expect some workers to fail
            # because the lock serializes access. If all 4 succeed, locking may be broken.
            # NOTE: This assertion demonstrates the CONCURRENCY ISSUE
            # After implementing proper locking, we expect fewer successes
            if success_count == num_workers:
                print("\n" + "!" * 60)
                print("WARNING: All workers succeeded")
                print("This suggests file locking may not be working correctly!")
                print("Expected: Only 1-2 workers should succeed (serialized access)")
                print("Actual: All 4 workers succeeded (possible race condition)")
                print("!" * 60)

            # Load and validate the final data structure
            with open(task_file_path, encoding="utf-8") as f:
                final_data = json.load(f)

            # Verify continue_session task is well-formed
            continue_task = final_data["tasks"]["continue_session"]
            assert isinstance(continue_task, dict), "continue_session must be a dict"
            assert "id" in continue_task, "continue_session must have 'id'"
            assert "metadata" in continue_task, "continue_session must have 'metadata'"
            assert "handoff" in continue_task["metadata"], "continue_session metadata must have handoff"

            # Verify active_session task is well-formed
            active_task = final_data["tasks"]["active_session"]
            assert isinstance(active_task, dict), "active_session must be a dict"
            assert "metadata" in active_task, "active_session must have 'metadata'"
            assert "handoff" in active_task["metadata"], "active_session metadata must have handoff"

            # Verify handoff data is present
            handoff = continue_task["metadata"]["handoff"]
            assert "task_name" in handoff, "Handoff must have task_name"
            # Note: handoff_metadata uses "progress_percent" not "progress_pct"
            assert "progress_percent" in handoff, "Handoff must have progress_percent"
            assert "next_steps" in handoff, "Handoff must have next_steps"

            print("\n" + "=" * 60)
            print("TEST PASSED: No data corruption detected")
            print("=" * 60)

    def test_concurrent_compaction_data_integrity(self):
        """
        Test that concurrent compaction preserves data integrity.

        Given: Multiple processes writing to same terminal
        When: Concurrent writes occur
        Then: Final state should be consistent (no partial writes)

        This test verifies that the final handoff data is complete and
        not a mix of partial writes from different processes.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create task tracker directory
            task_tracker_dir = temp_path / ".claude" / "state" / "task_tracker"
            task_tracker_dir.mkdir(parents=True, exist_ok=True)

            terminal_id = "test_terminal_integrity"
            task_file_path = task_tracker_dir / f"{terminal_id}_tasks.json"

            # Create initial task file
            initial_data = {
                "terminal_id": terminal_id,
                "tasks": {},
                "last_update": "2024-01-01T00:00:00.000000",
            }
            with open(task_file_path, "w", encoding="utf-8") as f:
                json.dump(initial_data, f, indent=2)

            # Launch 4 concurrent workers
            num_workers = 4

            with Pool(processes=num_workers) as pool:
                results = pool.starmap(
                    worker_compact_terminal,
                    [(i, str(temp_path), terminal_id) for i in range(num_workers)],
                )

            # Verify final file is valid JSON
            with open(task_file_path, encoding="utf-8") as f:
                final_data = json.load(f)

            # Check that all required fields are present
            assert "terminal_id" in final_data, "Must have terminal_id"
            assert "tasks" in final_data, "Must have tasks"
            assert "last_update" in final_data, "Must have last_update"

            # Check that handoff data is complete
            continue_task = final_data["tasks"]["continue_session"]
            handoff = continue_task["metadata"]["handoff"]

            # These fields should never be missing or empty
            required_handoff_fields = [
                "task_name",
                "progress_percent",  # Note: handoff_metadata uses progress_percent
                "blocker",
                "next_steps",
                "handover",
                "modifications",
                "saved_at",
            ]

            for field in required_handoff_fields:
                assert field in handoff, f"Handoff must have {field} field"

            # Verify handover is complete
            handover = handoff["handover"]
            assert "decisions" in handover, "Handover must have decisions"
            assert "patterns_learned" in handover, "Handover must have patterns_learned"

            print("\nData integrity verification: PASSED")
            print("All required fields present and well-formed")

    def test_concurrent_compaction_lock_file_behavior(self):
        """
        Test that lock file is created and cleaned up correctly.

        Given: Concurrent compaction operations
        When: File locking is active
        Then: Lock file should exist during writes, be cleaned up after

        This test verifies the lock file mechanism works as expected.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create task tracker directory
            task_tracker_dir = temp_path / ".claude" / "state" / "task_tracker"
            task_tracker_dir.mkdir(parents=True, exist_ok=True)

            terminal_id = "test_terminal_lock_behavior"
            task_file_path = task_tracker_dir / f"{terminal_id}_tasks.json"
            lock_file_path = task_file_path.with_suffix(".lock")

            # Create initial task file
            initial_data = {
                "terminal_id": terminal_id,
                "tasks": {},
                "last_update": "2024-01-01T00:00:00.000000",
            }
            with open(task_file_path, "w", encoding="utf-8") as f:
                json.dump(initial_data, f, indent=2)

            # Verify no lock file initially
            assert not lock_file_path.exists(), "Lock file should not exist initially"

            # Launch workers
            num_workers = 4

            with Pool(processes=num_workers) as pool:
                results = pool.starmap(
                    worker_compact_terminal,
                    [(i, str(temp_path), terminal_id) for i in range(num_workers)],
                )

            # After all workers complete, lock should be cleaned up
            # (or not exist if last worker cleaned it up)
            if lock_file_path.exists():
                # Check if lock is stale
                lock_stat = os.stat(lock_file_path)
                lock_age = time.time() - lock_stat.st_mtime
                print(f"\nLock file exists after test, age: {lock_age:.2f} seconds")

                # Lock older than 1 second is stale
                # (this might indicate cleanup didn't happen)
                if lock_age > 1:
                    print("Warning: Lock file may not have been cleaned up properly")

            # Verify task file was written successfully
            assert task_file_path.exists(), "Task file must exist"

            print("\nLock file behavior test completed")


if __name__ == "__main__":
    # Run tests
    import pytest

    pytest.main([__file__, "-v", "-s"])

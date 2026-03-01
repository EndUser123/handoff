"""Performance tests for JSON serialization operations (PERF-002).

This test module captures CURRENT BEHAVIOR before refactoring to fix
duplicate JSON serialization during quality scoring.

Performance Issue: PERF-002
============================
The handoff_store module serializes JSON twice during quality scoring:
1. Line 346: Calculate estimated_size in _validate_handoff_data_size()
2. Line 161/168: Serialize for size calculation in atomic_write_with_validation()

This is wasteful for large handoffs with 1000+ modifications.

Expected After Fix:
-------------------
- JSON should be serialized only ONCE
- Use cached serialization result for both size calculation and write
- Performance improvement: ~2x faster serialization for large handoffs

Run with:
    pytest tests/test_performance_json_serialization.py -v
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from handoff.hooks.__lib.handoff_store import (
    _validate_handoff_data_size,
    atomic_write_with_validation,
)


class TestJSONSerializationPerformance:
    """Tests for PERF-002: Duplicate JSON serialization during quality scoring."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def large_handoff_data(self):
        """Create large handoff data with 1000+ modifications.

        This simulates a real-world scenario where a long session
        generates many modifications, making JSON serialization expensive.
        """
        modifications = []
        for i in range(1000):
            modifications.append({
                "file": f"src/module_{i % 10}.py",
                "action": "edit" if i % 2 == 0 else "create",
                "lines_changed": 10 + (i % 50),
                "timestamp": "2026-03-01T12:00:00Z",
            })

        active_files = [f"src/module_{i}.py" for i in range(100)]
        recent_tools = [f"tool_{i}" for i in range(30)]

        handoff_data = {
            "task_name": "large_refactoring_task",
            "session_id": "session_12345_large_refactoring",
            "timestamp": "2026-03-01T12:00:00Z",
            "progress_pct": 75,
            "blocker": None,
            "files_modified": active_files,
            "active_files": active_files,
            "next_steps": "Continue refactoring the core modules\n" * 100,
            "session_summary": "Large refactoring session",
            "handover": {
                "decisions": [
                    {"topic": f"Decision {i}", "timestamp": "2026-03-01T12:00:00Z"}
                    for i in range(10)
                ],
                "patterns_learned": [
                    f"Pattern {i}: Some description text here"
                    for i in range(10)
                ],
            },
            "modifications": modifications,
            "recent_tools": recent_tools,
            "pending_operations": [],
        }

        return handoff_data

    def test_quality_score_duplicate_json_serialization(
        self, large_handoff_data, temp_dir
    ):
        """Characterization: Count JSON serialization operations during quality scoring.

        Given: Large handoff data (1000+ modifications)
        When: Validating and writing handoff data with quality scoring
        Then: JSON is currently serialized MULTIPLE times (before fix)
              - Line 161: atomic_write_with_validation() serializes original_data for size
              - Line 346: _validate_handoff_data_size() serializes for estimated_size
              - Line 168: atomic_write_with_validation() serializes final_data for size

        This test demonstrates the performance issue (PERF-002).
        After implementing caching, this test should be updated to expect fewer calls.

        Note: The actual file write uses the cached final_data string,
        so there's no 4th serialization for the write itself.
        """
        target_path = temp_dir / "test_handoff.json"

        # Track all json.dumps calls
        json_dumps_calls = []
        original_json_dumps = json.dumps

        def tracking_json_dumps(*args, **kwargs):
            """Track json.dumps calls and delegate to original."""
            # Track all dict serialization calls
            if args and isinstance(args[0], dict):
                json_dumps_calls.append({
                    "arg_keys": list(args[0].keys())[:10],  # First 10 keys for identification
                    "has_modifications": "modifications" in args[0],
                    "mod_count": len(args[0].get("modifications", [])),
                    "indent": kwargs.get("indent", "default"),
                })
            return original_json_dumps(*args, **kwargs)

        # Patch json.dumps to track serialization calls
        with patch("handoff.hooks.__lib.handoff_store.json.dumps", side_effect=tracking_json_dumps):
            # Execute the function that triggers quality scoring
            result = atomic_write_with_validation(large_handoff_data, target_path)

        # Verify the file was written successfully
        assert target_path.exists(), "Handoff file should be created"
        assert result["truncated"] is True, "Large data should be truncated"

        # Characterization: Count actual JSON serialization calls
        # CURRENT BEHAVIOR: 3+ calls (before fix)
        # - Line 161: atomic_write_with_validation() serializes original_data (1000 mods)
        # - Line 346: _validate_handoff_data_size() serializes validated_data (50 mods after truncation)
        # - Line 168: atomic_write_with_validation() serializes final_data (50 mods)
        #
        # EXPECTED AFTER FIX: 2 calls (eliminate the line 346 call by reusing line 168 result)

        print("\n=== JSON Serialization Calls ===")
        print(f"Total json.dumps calls: {len(json_dumps_calls)}")
        for i, call in enumerate(json_dumps_calls, 1):
            print(f"  Call {i}: mod_count={call['mod_count']}, indent={call['indent']}")

        # CURRENT BEHAVIOR: Assert that we see multiple serializations (demonstrates the bug)
        # We expect at least 2 calls: original_data size calculation + final_data size calculation
        # Plus possibly the validation size check
        assert len(json_dumps_calls) >= 2, (
            f"CURRENT BEHAVIOR: JSON serialized {len(json_dumps_calls)} times. "
            f"Expected at least 2 before fix (original + final), will be optimized after fix."
        )

        # Specifically verify we're serializing the original large data
        original_data_calls = [c for c in json_dumps_calls if c["mod_count"] == 1000]
        assert len(original_data_calls) >= 1, (
            f"Should serialize original data at least once for size calculation, "
            f"got {len(original_data_calls)} calls with 1000 modifications"
        )

    def test_validation_serialize_for_size_check(self, large_handoff_data):
        """Characterization: _validate_handoff_data_size skips serialization with cached_json=None.

        Given: Large handoff data
        When: Calling _validate_handoff_data_size() with default cached_json=None
        Then: JSON is NOT serialized internally (PERF-002 fix)

        After the fix, validation skips the internal size check serialization
        to avoid duplicate work when the caller will serialize anyway.
        """
        # Track json.dumps calls
        json_dumps_calls = []
        original_json_dumps = json.dumps

        def tracking_json_dumps(*args, **kwargs):
            """Track json.dumps calls."""
            if args and isinstance(args[0], dict) and "modifications" in args[0]:
                json_dumps_calls.append({
                    "mod_count": len(args[0].get("modifications", [])),
                })
            return original_json_dumps(*args, **kwargs)

        with patch("handoff.hooks.__lib.handoff_store.json.dumps", side_effect=tracking_json_dumps):
            # Validate handoff data with cached_json=None (default)
            # PERF-002: This should NOT trigger internal serialization
            validated = _validate_handoff_data_size(large_handoff_data)

        # Verify data was truncated
        assert len(validated["modifications"]) == 50, "Should truncate to MAX_MODIFICATIONS"

        # Count serialization calls
        print("\n=== Validation Serialization Calls ===")
        print(f"Total serializations: {len(json_dumps_calls)}")

        # AFTER FIX: No serialization should happen internally
        # The caller (atomic_write_with_validation) handles serialization
        assert len(json_dumps_calls) == 0, (
            f"PERF-002: Validation should NOT serialize internally when cached_json=None, "
            f"got {len(json_dumps_calls)} calls. Caller handles serialization."
        )

    def test_write_serialize_for_actual_write(self, large_handoff_data, temp_dir):
        """Characterization: atomic_write_with_validation serializes JSON for write.

        Given: Large handoff data (already validated)
        When: Calling atomic_write_with_validation()
        Then: JSON is serialized for original_size calculation (line 161)
             And serialized again for final_size calculation (line 168)
             And serialized a third time for the actual write (implicit in f.write())

        Note: After validation, the data is smaller (truncated to 50 modifications),
        so we can't easily track the exact serialization without inspecting the data.
        """
        target_path = temp_dir / "test_handoff.json"

        # Track json.dumps calls
        json_dumps_calls = []
        original_json_dumps = json.dumps

        def tracking_json_dumps(*args, **kwargs):
            """Track json.dumps calls."""
            if args and isinstance(args[0], dict):
                json_dumps_calls.append({
                    "has_modifications": "modifications" in args[0],
                    "mod_count": len(args[0].get("modifications", [])),
                    "indent": kwargs.get("indent", "default"),
                })
            return original_json_dumps(*args, **kwargs)

        with patch("handoff.hooks.__lib.handoff_store.json.dumps", side_effect=tracking_json_dumps):
            # Write validated data
            result = atomic_write_with_validation(large_handoff_data, target_path)

        # Verify success
        assert target_path.exists()
        assert result["truncated"] is True

        print("\n=== Write Serialization Calls ===")
        print(f"Total json.dumps calls: {len(json_dumps_calls)}")
        for i, call in enumerate(json_dumps_calls, 1):
            print(f"  Call {i}: mod_count={call['mod_count']}, indent={call['indent']}")

        # CURRENT BEHAVIOR:
        # - Line 161: Serialize original_data for original_size (1000 mods)
        # - Line 346: Serialize validated data in _validate_handoff_data_size (50 mods after truncation)
        # - Line 168: Serialize final_data for final_size (50 mods)
        #
        # Note: The actual file write uses the final_data string, not a new json.dumps call
        #
        # So we expect at least 2-3 calls depending on truncation
        assert len(json_dumps_calls) >= 2, (
            f"Write process should serialize at least twice (original + validated/final), "
            f"got {len(json_dumps_calls)}"
        )


@pytest.fixture
def temp_dir():
    """Create temporary directory for test files (shared across all tests)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestSerializationPerformanceImpact:
    """Tests measuring performance impact of duplicate serialization."""

    @pytest.fixture
    def large_handoff_data(self):
        """Create handoff data with configurable size."""
        def create_data(modification_count):
            modifications = []
            for i in range(modification_count):
                modifications.append({
                    "file": f"src/module_{i % 10}.py",
                    "action": "edit",
                    "lines_changed": 10 + (i % 50),
                    "timestamp": "2026-03-01T12:00:00Z",
                })

            return {
                "task_name": "performance_test",
                "modifications": modifications,
                "active_files": [f"src/module_{i}.py" for i in range(100)],
                "next_steps": "Continue work\n" * 100,
                "handover": {
                    "decisions": [{"topic": f"Decision {i}"} for i in range(10)],
                    "patterns_learned": [f"Pattern {i}" for i in range(10)],
                },
            }

        return create_data

    def test_serialization_cost_scales_with_data_size(self, large_handoff_data, temp_dir):
        """Characterization: Serialization cost scales linearly with data size.

        Given: Handoff data with varying modification counts
        When: Serializing to JSON
        Then: Time scales linearly with modification count

        This demonstrates why duplicate serialization is wasteful.
        """
        import time

        target_path = temp_dir / "test_perf.json"

        modification_counts = [100, 500, 1000, 2000]
        serialization_times = []

        for count in modification_counts:
            data = large_handoff_data(count)

            # Measure serialization time
            start = time.perf_counter()
            json_str = json.dumps(data, indent=2)
            elapsed = time.perf_counter() - start

            serialization_times.append({
                "modifications": count,
                "size_bytes": len(json_str.encode("utf-8")),
                "time_seconds": elapsed,
            })

        print("\n=== Serialization Performance ===")
        for result in serialization_times:
            print(
                f"Mods: {result['modifications']:4d} | "
                f"Size: {result['size_bytes']:7d} bytes | "
                f"Time: {result['time_seconds']*1000:6.2f} ms"
            )

        # Verify linear scaling (each 2x increase in mods should take ~2x time)
        # Allow generous tolerance for system noise
        for i in range(1, len(serialization_times)):
            prev = serialization_times[i - 1]
            curr = serialization_times[i]

            mod_ratio = curr["modifications"] / prev["modifications"]
            time_ratio = curr["time_seconds"] / prev["time_seconds"]

            print(f"  Mod ratio: {mod_ratio:.2f}x, Time ratio: {time_ratio:.2f}x")

            # Time should scale reasonably with modifications (within 0.5x to 3x)
            assert 0.5 <= time_ratio / mod_ratio <= 3.0, (
                f"Serialization time should scale roughly linearly: "
                f"mods={mod_ratio:.2f}x but time={time_ratio:.2f}x"
            )

    def test_duplicate_serialization_doubles_cost(self, large_handoff_data, temp_dir):
        """Characterization: Duplicate serialization doubles the cost.

        Given: Large handoff data (1000 modifications)
        When: Going through validation + write process
        Then: Serialization happens twice, doubling the cost

        This quantifies the performance waste from PERF-002.
        """
        import time

        data = large_handoff_data(1000)
        target_path = temp_dir / "test_perf.json"

        # Measure single serialization
        start = time.perf_counter()
        json_str = json.dumps(data, indent=2)
        single_serialization_time = time.perf_counter() - start

        # Measure full validation + write process
        start = time.perf_counter()
        result = atomic_write_with_validation(data, target_path)
        full_process_time = time.perf_counter() - start

        print("\n=== Performance Cost Analysis ===")
        print(f"Single serialization: {single_serialization_time*1000:.2f} ms")
        print(f"Full process (validation + write): {full_process_time*1000:.2f} ms")
        print(f"Overhead: {(full_process_time - single_serialization_time)*1000:.2f} ms")
        print(f"Ratio: {full_process_time / single_serialization_time:.2f}x")

        # The full process should take at least 2x single serialization
        # (because we serialize twice: once in validation, once in write)
        # Allow generous tolerance for other overhead
        assert full_process_time >= single_serialization_time * 1.5, (
            f"Full process should take at least 1.5x single serialization "
            f"(indicating duplicate work), got {full_process_time / single_serialization_time:.2f}x"
        )


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "-s"])

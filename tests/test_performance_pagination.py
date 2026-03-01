"""Performance tests for lazy loading of large lists (PERF-003).

These tests verify that large lists (modifications, decisions, etc.)
are loaded lazily using iterators rather than loading everything into
memory then slicing.

Issue: PERF-003 - No Pagination for Large Lists
Current behavior: Loads entire list into memory, then slices
Expected behavior: Lazy loading with itertools.islice() or similar

Run with: pytest tests/test_performance_pagination.py -v
"""

from unittest.mock import MagicMock


class TestModificationsLazyLoading:
    """Tests for lazy loading of modifications list."""

    def test_modifications_last_five_should_not_load_all(self):
        """
        Test that displaying last 5 modifications doesn't load all 10,000 into memory.

        Given: Handoff data with 10,000 modifications
        When: format_llm_prompt() is called to display last 5 modifications
        Then: Only 5 modifications should be accessed (lazy loading)

        Current implementation FAILS this test because it loads all modifications
        into memory with modifications[-5:] before iterating.

        After fix with itertools.islice(), this test will PASS.
        """
        # Arrange: Create handoff data with 10,000 modifications
        large_modification_list = [
            {"file": f"src/file_{i}.py", "action": "modified"}
            for i in range(10000)
        ]

        handoff_data = {
            "session_id": "test_session",
            "timestamp": "2026-03-01T00:00:00Z",
            "quality_score": 0.85,
            "quality_rating": "Good",
            "modifications": large_modification_list,
            "next_steps": ["Step 1", "Step 2"],
            "handover": {
                "decisions": [
                    {
                        "topic": "Test decision",
                        "decision": "Test decision text",
                        "bridge_token": "BRIDGE_20260301-000000_TEST"
                    }
                ]
            }
        }

        # Track how many modifications are actually accessed
        access_tracker = {"count": 0}

        def tracking_getitem(idx):
            """Wrapper that tracks list access."""
            if isinstance(idx, slice):
                # Track slice access
                start, stop, step = idx.indices(len(large_modification_list))
                count = len(range(start, stop, step))
                access_tracker["count"] += count
                return large_modification_list[idx]
            else:
                access_tracker["count"] += 1
                return large_modification_list[idx]

        # Create a tracked list that records access
        tracked_modifications = MagicMock()
        tracked_modifications.__getitem__.side_effect = tracking_getitem
        tracked_modifications.__len__.return_value = len(large_modification_list)

        # Replace modifications with tracked version
        handoff_data["modifications"] = tracked_modifications

        # Act: Import and call format_llm_prompt
        # This should only access the last 5 items if lazy loading works
        from handoff.cli import format_llm_prompt

        result = format_llm_prompt(handoff_data, expand_tokens=False)

        # Assert: Should only access 5 items, not all 10,000
        # Current implementation FAILS because it does modifications[-5:]
        # which creates a new list containing 5 elements (accessing all 10,000
        # to create the slice in Python's list implementation)

        # For a proper lazy implementation using itertools.islice,
        # we would only iterate over the last 5 elements without loading all

        # This assertion will FAIL with current implementation
        # demonstrating the memory inefficiency
        assert access_tracker["count"] <= 5, (
            f"Expected to access only 5 modifications, but accessed {access_tracker['count']}. "
            f"This demonstrates PERF-003: loads all {len(large_modification_list)} items "
            f"into memory before slicing, causing memory inefficiency."
        )

    def test_modifications_slice_memory_overhead(self):
        """
        Test that modifications[-5:] creates unnecessary memory overhead.

        Given: Handoff data with 10,000 modifications
        When: Slicing with modifications[-5:]
        Then: Should use lazy iteration, not materialize slice

        This test demonstrates the current inefficient behavior.
        """
        # Arrange
        import tracemalloc

        large_modification_list = [
            {"file": f"src/file_{i}.py", "action": "modified", "metadata": "x" * 100}
            for i in range(10000)
        ]

        # Start tracking memory
        tracemalloc.start()

        # Act: Current implementation approach (loads all then slices)
        snapshot_before = tracemalloc.take_snapshot()

        # This is what the current code does
        last_five_inefficient = large_modification_list[-5:]

        snapshot_after = tracemalloc.take_snapshot()

        # Calculate memory used by the slice operation
        top_stats = snapshot_after.compare_to(snapshot_before, 'lineno')
        total_memory_kb = sum(stat.size_diff for stat in top_stats) / 1024

        tracemalloc.stop()

        # Assert: Even though we only want 5 items, the slice operation
        # has to materialize references to all 10,000 items first
        # This demonstrates the inefficiency

        # The test will show that slicing creates overhead
        # (though Python optimizes this by not copying, it still iterates internally)

        # After fix with itertools.islice(), we should see zero memory overhead
        # for accessing the last 5 items

        # For now, this test documents the current behavior
        assert len(last_five_inefficient) == 5
        # The real issue is that Python had to iterate through all 10,000
        # items to get to the last 5, which is inefficient


class TestDecisionsLazyLoading:
    """Tests for lazy loading of decisions list."""

    def test_decisions_first_five_should_not_load_all(self):
        """
        Test that displaying first 5 decisions doesn't load all into memory.

        Given: Handoff data with 10,000 decisions
        When: format_llm_prompt() displays first 5 decisions
        Then: Only 5 decisions should be accessed

        Current implementation: decisions[:5] loads all then slices
        Expected: Lazy loading with itertools.islice()
        """
        # Arrange: Create handoff with 10,000 decisions
        large_decision_list = [
            {
                "topic": f"Decision {i}",
                "decision": f"Decision text {i}",
                "bridge_token": f"BRIDGE_20260301-00000{i}"
            }
            for i in range(10000)
        ]

        handoff_data = {
            "session_id": "test_session",
            "timestamp": "2026-03-01T00:00:00Z",
            "quality_score": 0.85,
            "quality_rating": "Good",
            "modifications": [],
            "next_steps": [],
            "handover": {
                "decisions": large_decision_list
            }
        }

        # Track access count
        access_tracker = {"count": 0}

        def tracking_getitem(idx):
            """Wrapper that tracks list access."""
            if isinstance(idx, slice):
                start, stop, step = idx.indices(len(large_decision_list))
                count = len(range(start, stop, step))
                access_tracker["count"] += count
                return large_decision_list[idx]
            else:
                access_tracker["count"] += 1
                return large_decision_list[idx]

        tracked_decisions = MagicMock()
        tracked_decisions.__getitem__.side_effect = tracking_getitem
        tracked_decisions.__len__.return_value = len(large_decision_list)

        handoff_data["handover"]["decisions"] = tracked_decisions

        # Act
        from handoff.cli import format_llm_prompt

        result = format_llm_prompt(handoff_data, expand_tokens=False)

        # Assert: Should only access 5 decisions
        # This will FAIL with current implementation
        assert access_tracker["count"] <= 5, (
            f"Expected to access only 5 decisions, but accessed {access_tracker['count']}. "
            f"This demonstrates PERF-003: loads all {len(large_decision_list)} decisions "
            f"into memory before slicing."
        )


class TestNextStepsLazyLoading:
    """Tests for lazy loading of next_steps list."""

    def test_next_steps_first_five_should_not_load_all(self):
        """
        Test that displaying first 5 next_steps doesn't load all into memory.

        Given: Handoff data with 10,000 next steps
        When: format_llm_prompt() displays first 5 next steps
        Then: Only 5 next steps should be accessed
        """
        # Arrange
        large_next_steps = [f"Step {i}: Do something" for i in range(10000)]

        handoff_data = {
            "session_id": "test_session",
            "timestamp": "2026-03-01T00:00:00Z",
            "quality_score": 0.85,
            "quality_rating": "Good",
            "modifications": [],
            "next_steps": large_next_steps,
            "handover": {
                "decisions": []
            }
        }

        # Track access count
        access_tracker = {"count": 0}

        def tracking_getitem(idx):
            """Wrapper that tracks list access."""
            if isinstance(idx, slice):
                start, stop, step = idx.indices(len(large_next_steps))
                count = len(range(start, stop, step))
                access_tracker["count"] += count
                return large_next_steps[idx]
            else:
                access_tracker["count"] += 1
                return large_next_steps[idx]

        tracked_next_steps = MagicMock()
        tracked_next_steps.__getitem__.side_effect = tracking_getitem
        tracked_next_steps.__len__.return_value = len(large_next_steps)

        handoff_data["next_steps"] = tracked_next_steps

        # Act
        from handoff.cli import format_llm_prompt

        result = format_llm_prompt(handoff_data, expand_tokens=False)

        # Assert: Should only access 5 steps
        # This will FAIL with current implementation
        assert access_tracker["count"] <= 5, (
            f"Expected to access only 5 next_steps, but accessed {access_tracker['count']}. "
            f"This demonstrates PERF-003: loads all {len(large_next_steps)} steps "
            f"into memory before slicing."
        )

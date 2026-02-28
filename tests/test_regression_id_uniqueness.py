#!/usr/bin/env python3
"""Regression test for checkpoint ID uniqueness.

This test verifies that multiple checkpoints get unique IDs (no collisions).
Creating 100 checkpoints should produce 100 unique IDs.

Run with: pytest P:/packages/handoff/tests/test_regression_id_uniqueness.py -v
"""

from __future__ import annotations

from pathlib import Path

# Add handoff package to path
HANDOFF_PACKAGE = Path(__file__).parent.parent / "src"
if str(HANDOFF_PACKAGE) not in globals():
    import sys
    sys.path.insert(0, str(HANDOFF_PACKAGE))

from handoff.hooks.__lib.handoff_store import HandoffStore


class TestCheckpointIDUniquenessRegression:
    """Regression tests for checkpoint ID uniqueness."""

    def test_multiple_checkpoints_have_unique_ids(self):
        """
        Test that creating multiple checkpoints produces unique IDs.

        Given: A HandoffStore instance
        When: Creating 100 checkpoints
        Then: All 100 checkpoint IDs should be unique (no collisions)

        Regression: Ensures uuid4() generates sufficient randomness to prevent
        collisions in normal usage patterns.
        """
        # Arrange
        store = HandoffStore(
            project_root=Path("."),
            terminal_id="test_terminal_uniqueness"
        )

        # Act
        checkpoint_ids = set()
        num_checkpoints = 100

        for i in range(num_checkpoints):
            handoff = store.build_handoff_data(
                task_name=f"Task {i}",
                progress_pct=i,
                blocker=None,
                files_modified=[],
                next_steps=[f"Step {i}"],
                handover={},
                modifications=[],
            )
            checkpoint_ids.add(handoff["checkpoint_id"])

        # Assert
        assert len(checkpoint_ids) == num_checkpoints, (
            f"Expected {num_checkpoints} unique checkpoint IDs, "
            f"but got {len(checkpoint_ids)} unique IDs. "
            f"This indicates {num_checkpoints - len(checkpoint_ids)} collision(s)."
        )

    def test_chain_id_persists_across_checkpoints(self):
        """
        Test that chain_id remains consistent across checkpoints in same session.

        Given: A HandoffStore instance
        When: Creating multiple checkpoints in sequence
        Then: All checkpoints should share the same chain_id

        Regression: Ensures chain linking works correctly for session grouping.
        """
        # Arrange
        store = HandoffStore(
            project_root=Path("."),
            terminal_id="test_terminal_chain"
        )

        # Act
        handoffs = []
        num_checkpoints = 10

        for i in range(num_checkpoints):
            handoff = store.build_handoff_data(
                task_name=f"Task {i}",
                progress_pct=i * 10,
                blocker=None,
                files_modified=[],
                next_steps=[f"Step {i}"],
                handover={},
                modifications=[],
            )
            handoffs.append(handoff)

        # Assert
        chain_ids = {h["chain_id"] for h in handoffs}
        assert len(chain_ids) == 1, (
            f"Expected all checkpoints to share the same chain_id, "
            f"but found {len(chain_ids)} different chain_ids: {chain_ids}"
        )

        # Verify all checkpoint_ids are unique despite same chain_id
        checkpoint_ids = {h["checkpoint_id"] for h in handoffs}
        assert len(checkpoint_ids) == num_checkpoints, (
            f"Expected {num_checkpoints} unique checkpoint_ids within chain, "
            f"but got {len(checkpoint_ids)} unique IDs"
        )

    def test_parent_linking_across_checkpoints(self):
        """
        Test that parent_checkpoint_id correctly links checkpoints in sequence.

        Given: A HandoffStore instance
        When: Creating multiple checkpoints in sequence
        Then: Each checkpoint (except first) should have the previous checkpoint as parent

        Regression: Ensures chain traversal can navigate backwards through history.
        """
        # Arrange
        store = HandoffStore(
            project_root=Path("."),
            terminal_id="test_terminal_parent"
        )

        # Act
        handoffs = []
        num_checkpoints = 5

        for i in range(num_checkpoints):
            handoff = store.build_handoff_data(
                task_name=f"Task {i}",
                progress_pct=i * 20,
                blocker=None,
                files_modified=[],
                next_steps=[f"Step {i}"],
                handover={},
                modifications=[],
            )
            handoffs.append(handoff)

        # Assert
        # First checkpoint should have no parent
        assert handoffs[0]["parent_checkpoint_id"] is None, (
            "First checkpoint should have parent_checkpoint_id=None"
        )

        # Subsequent checkpoints should link to previous
        for i in range(1, num_checkpoints):
            expected_parent = handoffs[i - 1]["checkpoint_id"]
            actual_parent = handoffs[i]["parent_checkpoint_id"]
            assert actual_parent == expected_parent, (
                f"Checkpoint {i} should have parent_checkpoint_id={expected_parent}, "
                f"but got {actual_parent}"
            )

        # Verify no checkpoint links to itself
        for i, handoff in enumerate(handoffs):
            assert handoff["checkpoint_id"] != handoff["parent_checkpoint_id"], (
                f"Checkpoint {i} cannot be its own parent"
            )

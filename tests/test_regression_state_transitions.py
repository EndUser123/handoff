#!/usr/bin/env python3
"""Regression tests for PendingOperation state transitions.

These tests verify that pending operations transition through states correctly:
- PENDING -> IN_PROGRESS -> COMPLETED
- Invalid transitions should raise errors

This is a REGRESSION test to ensure state transition validation works correctly.
Run with: pytest tests/test_regression_state_transitions.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Add handoff package to path
HANDOFF_PACKAGE = Path(__file__).parent.parent / "src"
if str(HANDOFF_PACKAGE) not in globals():
    import sys
    sys.path.insert(0, str(HANDOFF_PACKAGE))

from handoff.checkpoint_ops import PendingOperation


class TestPendingOperationStateTransitions:
    """Tests for valid state transitions in PendingOperation."""

    def test_pending_to_in_progress_transition(self):
        """Test valid state transition from PENDING to IN_PROGRESS.

        Given: A PendingOperation in PENDING state
        When: State is transitioned to IN_PROGRESS
        Then: Transition should succeed
        """
        op = PendingOperation(
            type="edit",
            target="src/main.py",
            state="pending",
            details={}
        )

        # Expect transition method to exist and work
        op.transition_to("in_progress")
        assert op.state == "in_progress"

    def test_in_progress_to_completed_transition(self):
        """Test valid state transition from IN_PROGRESS to COMPLETED.

        Given: A PendingOperation in IN_PROGRESS state
        When: State is transitioned to COMPLETED
        Then: Transition should succeed
        """
        op = PendingOperation(
            type="edit",
            target="src/main.py",
            state="in_progress",
            details={}
        )

        # Expect transition method to exist and work
        op.transition_to("completed")
        assert op.state == "completed"

    def test_full_workflow_transition(self):
        """Test complete workflow: PENDING -> IN_PROGRESS -> COMPLETED.

        Given: A PendingOperation in PENDING state
        When: State transitions through full lifecycle
        Then: All transitions should succeed in sequence
        """
        op = PendingOperation(
            type="test",
            target="tests/test_main.py",
            state="pending",
            details={}
        )

        # Full lifecycle
        op.transition_to("in_progress")
        assert op.state == "in_progress"

        op.transition_to("completed")
        assert op.state == "completed"

    def test_in_progress_to_failed_transition(self):
        """Test valid state transition from IN_PROGRESS to FAILED.

        Given: A PendingOperation in IN_PROGRESS state
        When: State is transitioned to FAILED
        Then: Transition should succeed
        """
        op = PendingOperation(
            type="edit",
            target="src/main.py",
            state="in_progress",
            details={}
        )

        # Expect transition to failed to work
        op.transition_to("failed")
        assert op.state == "failed"

    def test_invalid_transition_from_completed(self):
        """Test invalid state transition from COMPLETED to IN_PROGRESS.

        Given: A PendingOperation in COMPLETED state
        When: State is transitioned to IN_PROGRESS
        Then: Should raise ValueError (cannot reopen completed operation)
        """
        op = PendingOperation(
            type="edit",
            target="src/main.py",
            state="completed",
            details={}
        )

        # Should not allow transitioning from completed back to in_progress
        with pytest.raises(ValueError, match="Invalid state transition|cannot transition"):
            op.transition_to("in_progress")

    def test_invalid_transition_from_failed_to_pending(self):
        """Test invalid state transition from FAILED to PENDING.

        Given: A PendingOperation in FAILED state
        When: State is transitioned to PENDING
        Then: Should raise ValueError (cannot reset failed operation)
        """
        op = PendingOperation(
            type="test",
            target="tests/test_main.py",
            state="failed",
            details={}
        )

        # Should not allow transitioning from failed back to pending
        with pytest.raises(ValueError, match="Invalid state transition|cannot transition"):
            op.transition_to("pending")

    def test_invalid_transition_same_state(self):
        """Test invalid state transition to same state.

        Given: A PendingOperation in PENDING state
        When: State is transitioned to PENDING (same state)
        Then: Should raise ValueError (no-op transitions not allowed)
        """
        op = PendingOperation(
            type="read",
            target="README.md",
            state="pending",
            details={}
        )

        # Should not allow transitioning to same state
        with pytest.raises(ValueError, match="Invalid state transition|same state"):
            op.transition_to("pending")

    def test_invalid_state_value(self):
        """Test transition to invalid state value.

        Given: A PendingOperation in PENDING state
        When: State is transitioned to "cancelled" (invalid)
        Then: Should raise ValueError (invalid state)
        """
        op = PendingOperation(
            type="command",
            target="pytest tests/",
            state="pending",
            details={}
        )

        # Should not allow transitioning to unknown state
        with pytest.raises(ValueError, match="Invalid state|Must be one of"):
            op.transition_to("cancelled")


class TestPendingOperationStateValidation:
    """Tests for state validation in PendingOperation."""

    def test_completed_state_exists(self):
        """Test that COMPLETED state is a valid state.

        Given: A PendingOperation is created
        When: State is set to "completed"
        Then: Should accept the state (completed should be valid)
        """
        op = PendingOperation(
            type="edit",
            target="src/main.py",
            state="completed",
            details={}
        )
        assert op.state == "completed"

    def test_all_valid_states(self):
        """Test that all expected states are valid.

        Given: A PendingOperation is created
        When: Each valid state is used
        Then: All should be accepted including completed
        """
        valid_states = ["pending", "in_progress", "completed", "failed"]

        for state in valid_states:
            op = PendingOperation(
                type="edit",
                target="test.py",
                state=state,
                details={}
            )
            assert op.state == state

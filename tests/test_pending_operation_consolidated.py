"""Test that PendingOperation is consolidated to a single definition.

These tests verify that PendingOperation exists as a single, unified class
with complete functionality across the handoff package.

Current State (BEFORE consolidation):
- handoff.models.PendingOperation: 3 states, no validation
- handoff.checkpoint_ops.PendingOperation: 4 states, with validation

Expected State (AFTER consolidation):
- Single PendingOperation class with 4 states and validation
- Both import paths resolve to the same class
"""

import pytest

from handoff.checkpoint_ops import PendingOperation as CheckpointOpsPendingOperation

# Test imports from both modules
from handoff.models import PendingOperation as ModelsPendingOperation


class TestPendingOperationConsolidation:
    """Tests verifying PendingOperation is consolidated to a single definition."""

    def test_both_imports_resolve_to_same_class(self):
        """
        Test that imports from both modules resolve to the same class.

        Given: PendingOperation is defined in two places (current state)
        When: Importing from both handoff.models and handoff.checkpoint_ops
        Then: Both imports should resolve to the SAME class object

        This test will FAIL until consolidation is complete.
        """
        # This assertion will FAIL because they are different classes
        assert ModelsPendingOperation is CheckpointOpsPendingOperation, (
            "PendingOperation should be a single class - imports from "
            "handoff.models and handoff.checkpoint_ops must resolve to the same object"
        )

    def test_pending_operation_has_all_four_states(self):
        """
        Test that PendingOperation supports all 4 required states.

        Given: PendingOperation tracks operation state
        When: Checking the state type annotation
        Then: All 4 states should be supported: pending, in_progress, completed, failed

        Note: handoff.models version only has 3 states (missing 'completed')
        """
        # Import from the module that should have the complete definition
        from handoff.checkpoint_ops import PendingOperation

        # Create instance with 'completed' state (only supported by checkpoint_ops version)
        op = PendingOperation(
            type="edit",
            target="src/main.py",
            state="completed",  # This state is missing from models version
            details={"line": 42}
        )

        assert op.state == "completed"

    def test_pending_operation_has_validation(self):
        """
        Test that PendingOperation has __post_init__ validation.

        Given: PendingOperation should validate targets on construction
        When: Creating an instance with an invalid target
        Then: Validation should raise ValueError

        Note: handoff.models version has no __post_init__ method
        """
        from handoff.checkpoint_ops import PendingOperation

        # Test empty target validation
        with pytest.raises(ValueError, match="target cannot be empty"):
            PendingOperation(
                type="edit",
                target="",  # Invalid: empty string
                state="pending",
                details={}
            )

        # Test null byte validation
        with pytest.raises(ValueError, match="target cannot contain null bytes"):
            PendingOperation(
                type="edit",
                target="test\x00.py",  # Invalid: contains null byte
                state="pending",
                details={}
            )

        # Test length validation
        with pytest.raises(ValueError, match="target cannot exceed"):
            PendingOperation(
                type="edit",
                target="a" * 300,  # Invalid: exceeds MAX_TARGET_LENGTH (255)
                state="pending",
                details={}
            )

    def test_models_version_has_completed_state(self):
        """
        Test that handoff.models.PendingOperation supports 'completed' state.

        Given: PendingOperation should have 4 states
        When: Creating instance from handoff.models with 'completed' state
        Then: Should succeed (will FAIL until models version is updated)

        This test will FAIL because handoff.models only has 3 states.
        """
        # This will raise TypeError because 'completed' is not in the Literal
        op = ModelsPendingOperation(
            type="edit",
            target="src/main.py",
            state="completed",  # Not in models.PendingOperation state Literal
            details={"line": 42}
        )
        assert op.state == "completed"

    def test_models_version_has_validation(self):
        """
        Test that handoff.models.PendingOperation has validation.

        Given: PendingOperation should validate targets
        When: Creating instance with invalid target from handoff.models
        Then: Should raise ValueError

        This test will FAIL because handoff.models has no __post_init__.
        """
        # This will NOT raise ValueError (no validation in models version)
        with pytest.raises(ValueError, match="target cannot be empty"):
            ModelsPendingOperation(
                type="edit",
                target="",  # Should be invalid but isn't in models version
                state="pending",
                details={}
            )

    def test_class_attributes_are_consistent(self):
        """
        Test that both versions have consistent class attributes.

        Given: PendingOperation should have consistent API
        When: Comparing class attributes between imports
        Then: Should have same methods and attributes

        This test will FAIL until consolidation complete.
        """
        # Check that both have same methods
        models_methods = set(dir(ModelsPendingOperation))
        checkpoint_ops_methods = set(dir(CheckpointOpsPendingOperation))

        # Key methods that should exist
        required_methods = {"to_dict", "from_dict", "__post_init__"}

        assert models_methods == checkpoint_ops_methods, (
            f"Methods differ between versions:\n"
            f"  models only: {models_methods - checkpoint_ops_methods}\n"
            f"  checkpoint_ops only: {checkpoint_ops_methods - models_methods}"
        )

        assert required_methods.issubset(models_methods), (
            f"Missing required methods: {required_methods - models_methods}"
        )

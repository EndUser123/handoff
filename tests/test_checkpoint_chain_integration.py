#!/usr/bin/env python3
"""Integration tests for checkpoint chain traversal in CheckpointChain.

These tests verify the full chain traversal functionality:
- get_chain() returns all checkpoints in a chain
- get_latest() returns the most recent checkpoint
- get_previous() navigates to parent checkpoint
- get_next() navigates to child checkpoint

Run with: pytest tests/test_checkpoint_chain_integration.py -v
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

# Add handoff package to path
HANDOFF_PACKAGE = Path(__file__).parent.parent / "src"
if str(HANDOFF_PACKAGE) not in globals():
    import sys
    sys.path.insert(0, str(HANDOFF_PACKAGE))

from handoff.checkpoint_chain import CheckpointChain, HandoffCheckpointRef


class TestCheckpointChainIntegration:
    """Integration tests for checkpoint chain traversal."""

    def test_get_chain_returns_all_checkpoints_chronologically(self):
        """
        Test that get_chain() returns all checkpoints in a chain in chronological order.

        Given: A task tracker file with 3 checkpoints in a chain
        When: get_chain() is called with the chain_id
        Then: All 3 checkpoints are returned in oldest-to-newest order
        """
        # Arrange
        chain_id = str(uuid4())
        checkpoint_id_1 = str(uuid4())
        checkpoint_id_2 = str(uuid4())
        checkpoint_id_3 = str(uuid4())

        with tempfile.TemporaryDirectory() as tmpdir:
            task_file = Path(tmpdir) / "test_terminal_tasks.json"

            # Create task file with 3 checkpoints in a chain
            task_data = {
                "tasks": {
                    "task_1": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_id_1,
                                "parent_checkpoint_id": None,
                                "chain_id": chain_id,
                                "saved_at": "2025-02-16T12:00:00Z",
                                "transcript_offset": 0,
                                "transcript_entry_count": 0
                            }
                        },
                        "created_at": "2025-02-16T12:00:00Z"
                    },
                    "task_2": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_id_2,
                                "parent_checkpoint_id": checkpoint_id_1,
                                "chain_id": chain_id,
                                "saved_at": "2025-02-16T12:05:00Z",
                                "transcript_offset": 1000,
                                "transcript_entry_count": 10
                            }
                        },
                        "created_at": "2025-02-16T12:05:00Z"
                    },
                    "task_3": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_id_3,
                                "parent_checkpoint_id": checkpoint_id_2,
                                "chain_id": chain_id,
                                "saved_at": "2025-02-16T12:10:00Z",
                                "transcript_offset": 2000,
                                "transcript_entry_count": 20
                            }
                        },
                        "created_at": "2025-02-16T12:10:00Z"
                    }
                }
            }

            task_file.write_text(json.dumps(task_data))

            # Act
            chain = CheckpointChain(Path(tmpdir), "test_terminal")
            result = chain.get_chain(chain_id)

            # Assert
            assert len(result) == 3, f"Expected 3 checkpoints, got {len(result)}"
            assert result[0].checkpoint_id == checkpoint_id_1, "First checkpoint should be oldest"
            assert result[1].checkpoint_id == checkpoint_id_2, "Second checkpoint should be middle"
            assert result[2].checkpoint_id == checkpoint_id_3, "Third checkpoint should be newest"
            assert result[0].parent_checkpoint_id is None, "First checkpoint should have no parent"
            assert result[1].parent_checkpoint_id == checkpoint_id_1, "Second checkpoint parent should be first"
            assert result[2].parent_checkpoint_id == checkpoint_id_2, "Third checkpoint parent should be second"

    def test_get_latest_returns_most_recent_checkpoint(self):
        """
        Test that get_latest() returns the most recent checkpoint in a chain.

        Given: A task tracker file with 3 checkpoints in a chain
        When: get_latest() is called with the chain_id
        Then: The checkpoint with the latest saved_at timestamp is returned
        """
        # Arrange
        chain_id = str(uuid4())
        checkpoint_id_1 = str(uuid4())
        checkpoint_id_2 = str(uuid4())
        checkpoint_id_3 = str(uuid4())

        with tempfile.TemporaryDirectory() as tmpdir:
            task_file = Path(tmpdir) / "test_terminal_tasks.json"

            task_data = {
                "tasks": {
                    "task_1": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_id_1,
                                "parent_checkpoint_id": None,
                                "chain_id": chain_id,
                                "saved_at": "2025-02-16T12:00:00Z",
                                "transcript_offset": 0,
                                "transcript_entry_count": 0
                            }
                        },
                        "created_at": "2025-02-16T12:00:00Z"
                    },
                    "task_2": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_id_2,
                                "parent_checkpoint_id": checkpoint_id_1,
                                "chain_id": chain_id,
                                "saved_at": "2025-02-16T12:05:00Z",
                                "transcript_offset": 1000,
                                "transcript_entry_count": 10
                            }
                        },
                        "created_at": "2025-02-16T12:05:00Z"
                    },
                    "task_3": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_id_3,
                                "parent_checkpoint_id": checkpoint_id_2,
                                "chain_id": chain_id,
                                "saved_at": "2025-02-16T12:10:00Z",
                                "transcript_offset": 2000,
                                "transcript_entry_count": 20
                            }
                        },
                        "created_at": "2025-02-16T12:10:00Z"
                    }
                }
            }

            task_file.write_text(json.dumps(task_data))

            # Act
            chain = CheckpointChain(Path(tmpdir), "test_terminal")
            latest = chain.get_latest(chain_id)

            # Assert
            assert latest is not None, "get_latest() should return a checkpoint"
            assert latest.checkpoint_id == checkpoint_id_3, f"Expected {checkpoint_id_3}, got {latest.checkpoint_id}"
            assert latest.parent_checkpoint_id == checkpoint_id_2, "Latest checkpoint should have second as parent"
            assert latest.transcript_offset == 2000, "Latest checkpoint should have transcript_offset of 2000"
            assert latest.transcript_entry_count == 20, "Latest checkpoint should have 20 transcript entries"

    def test_get_previous_navigates_to_parent(self):
        """
        Test that get_previous() navigates to the parent checkpoint.

        Given: A task tracker file with 3 checkpoints in a chain
        When: get_previous() is called with the middle checkpoint
        Then: The first checkpoint (parent) is returned
        """
        # Arrange
        chain_id = str(uuid4())
        checkpoint_id_1 = str(uuid4())
        checkpoint_id_2 = str(uuid4())
        checkpoint_id_3 = str(uuid4())

        with tempfile.TemporaryDirectory() as tmpdir:
            task_file = Path(tmpdir) / "test_terminal_tasks.json"

            task_data = {
                "tasks": {
                    "task_1": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_id_1,
                                "parent_checkpoint_id": None,
                                "chain_id": chain_id,
                                "saved_at": "2025-02-16T12:00:00Z",
                                "transcript_offset": 0,
                                "transcript_entry_count": 0
                            }
                        },
                        "created_at": "2025-02-16T12:00:00Z"
                    },
                    "task_2": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_id_2,
                                "parent_checkpoint_id": checkpoint_id_1,
                                "chain_id": chain_id,
                                "saved_at": "2025-02-16T12:05:00Z",
                                "transcript_offset": 1000,
                                "transcript_entry_count": 10
                            }
                        },
                        "created_at": "2025-02-16T12:05:00Z"
                    },
                    "task_3": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_id_3,
                                "parent_checkpoint_id": checkpoint_id_2,
                                "chain_id": chain_id,
                                "saved_at": "2025-02-16T12:10:00Z",
                                "transcript_offset": 2000,
                                "transcript_entry_count": 20
                            }
                        },
                        "created_at": "2025-02-16T12:10:00Z"
                    }
                }
            }

            task_file.write_text(json.dumps(task_data))

            # Act
            chain = CheckpointChain(Path(tmpdir), "test_terminal")

            # Test navigating from middle to first
            prev = chain.get_previous(checkpoint_id_2)

            # Assert
            assert prev is not None, "get_previous() should return a checkpoint for middle checkpoint"
            assert prev.checkpoint_id == checkpoint_id_1, f"Expected {checkpoint_id_1}, got {prev.checkpoint_id}"
            assert prev.parent_checkpoint_id is None, "First checkpoint should have no parent"
            assert prev.transcript_offset == 0, "First checkpoint should have transcript_offset of 0"

    def test_get_previous_returns_none_for_first_checkpoint(self):
        """
        Test that get_previous() returns None for the first checkpoint in a chain.

        Given: A task tracker file with 3 checkpoints in a chain
        When: get_previous() is called with the first checkpoint
        Then: None is returned (no parent exists)
        """
        # Arrange
        chain_id = str(uuid4())
        checkpoint_id_1 = str(uuid4())

        with tempfile.TemporaryDirectory() as tmpdir:
            task_file = Path(tmpdir) / "test_terminal_tasks.json"

            task_data = {
                "tasks": {
                    "task_1": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_id_1,
                                "parent_checkpoint_id": None,
                                "chain_id": chain_id,
                                "saved_at": "2025-02-16T12:00:00Z",
                                "transcript_offset": 0,
                                "transcript_entry_count": 0
                            }
                        },
                        "created_at": "2025-02-16T12:00:00Z"
                    }
                }
            }

            task_file.write_text(json.dumps(task_data))

            # Act
            chain = CheckpointChain(Path(tmpdir), "test_terminal")
            prev = chain.get_previous(checkpoint_id_1)

            # Assert
            assert prev is None, f"Expected None for first checkpoint, got {prev}"

    def test_get_next_navigates_to_child(self):
        """
        Test that get_next() navigates to the child checkpoint.

        Given: A task tracker file with 3 checkpoints in a chain
        When: get_next() is called with the middle checkpoint
        Then: The third checkpoint (child) is returned
        """
        # Arrange
        chain_id = str(uuid4())
        checkpoint_id_1 = str(uuid4())
        checkpoint_id_2 = str(uuid4())
        checkpoint_id_3 = str(uuid4())

        with tempfile.TemporaryDirectory() as tmpdir:
            task_file = Path(tmpdir) / "test_terminal_tasks.json"

            task_data = {
                "tasks": {
                    "task_1": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_id_1,
                                "parent_checkpoint_id": None,
                                "chain_id": chain_id,
                                "saved_at": "2025-02-16T12:00:00Z",
                                "transcript_offset": 0,
                                "transcript_entry_count": 0
                            }
                        },
                        "created_at": "2025-02-16T12:00:00Z"
                    },
                    "task_2": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_id_2,
                                "parent_checkpoint_id": checkpoint_id_1,
                                "chain_id": chain_id,
                                "saved_at": "2025-02-16T12:05:00Z",
                                "transcript_offset": 1000,
                                "transcript_entry_count": 10
                            }
                        },
                        "created_at": "2025-02-16T12:05:00Z"
                    },
                    "task_3": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_id_3,
                                "parent_checkpoint_id": checkpoint_id_2,
                                "chain_id": chain_id,
                                "saved_at": "2025-02-16T12:10:00Z",
                                "transcript_offset": 2000,
                                "transcript_entry_count": 20
                            }
                        },
                        "created_at": "2025-02-16T12:10:00Z"
                    }
                }
            }

            task_file.write_text(json.dumps(task_data))

            # Act
            chain = CheckpointChain(Path(tmpdir), "test_terminal")

            # Test navigating from middle to last
            next_cp = chain.get_next(checkpoint_id_2)

            # Assert
            assert next_cp is not None, "get_next() should return a checkpoint for middle checkpoint"
            assert next_cp.checkpoint_id == checkpoint_id_3, f"Expected {checkpoint_id_3}, got {next_cp.checkpoint_id}"
            assert next_cp.parent_checkpoint_id == checkpoint_id_2, "Child checkpoint should have middle as parent"
            assert next_cp.transcript_offset == 2000, "Child checkpoint should have transcript_offset of 2000"

    def test_get_next_returns_none_for_last_checkpoint(self):
        """
        Test that get_next() returns None for the last checkpoint in a chain.

        Given: A task tracker file with 3 checkpoints in a chain
        When: get_next() is called with the last checkpoint
        Then: None is returned (no child exists)
        """
        # Arrange
        chain_id = str(uuid4())
        checkpoint_id_1 = str(uuid4())
        checkpoint_id_2 = str(uuid4())
        checkpoint_id_3 = str(uuid4())

        with tempfile.TemporaryDirectory() as tmpdir:
            task_file = Path(tmpdir) / "test_terminal_tasks.json"

            task_data = {
                "tasks": {
                    "task_1": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_id_1,
                                "parent_checkpoint_id": None,
                                "chain_id": chain_id,
                                "saved_at": "2025-02-16T12:00:00Z",
                                "transcript_offset": 0,
                                "transcript_entry_count": 0
                            }
                        },
                        "created_at": "2025-02-16T12:00:00Z"
                    },
                    "task_2": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_id_2,
                                "parent_checkpoint_id": checkpoint_id_1,
                                "chain_id": chain_id,
                                "saved_at": "2025-02-16T12:05:00Z",
                                "transcript_offset": 1000,
                                "transcript_entry_count": 10
                            }
                        },
                        "created_at": "2025-02-16T12:05:00Z"
                    },
                    "task_3": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_id_3,
                                "parent_checkpoint_id": checkpoint_id_2,
                                "chain_id": chain_id,
                                "saved_at": "2025-02-16T12:10:00Z",
                                "transcript_offset": 2000,
                                "transcript_entry_count": 20
                            }
                        },
                        "created_at": "2025-02-16T12:10:00Z"
                    }
                }
            }

            task_file.write_text(json.dumps(task_data))

            # Act
            chain = CheckpointChain(Path(tmpdir), "test_terminal")
            next_cp = chain.get_next(checkpoint_id_3)

            # Assert
            assert next_cp is None, f"Expected None for last checkpoint, got {next_cp}"

    def test_full_chain_traversal_forward_and_backward(self):
        """
        Test full forward and backward traversal through a checkpoint chain.

        Given: A task tracker file with 5 checkpoints in a chain
        When: Traversing forward from first to last, then backward to first
        Then: All checkpoints are visited in correct order both ways
        """
        # Arrange
        chain_id = str(uuid4())
        checkpoint_ids = [str(uuid4()) for _ in range(5)]

        with tempfile.TemporaryDirectory() as tmpdir:
            task_file = Path(tmpdir) / "test_terminal_tasks.json"

            # Build chain with 5 checkpoints
            tasks = {}
            for i, cp_id in enumerate(checkpoint_ids):
                parent_id = checkpoint_ids[i - 1] if i > 0 else None
                tasks[f"task_{i+1}"] = {
                    "metadata": {
                        "handoff": {
                            "checkpoint_id": cp_id,
                            "parent_checkpoint_id": parent_id,
                            "chain_id": chain_id,
                            "saved_at": f"2025-02-16T12:0{i}:00Z",
                            "transcript_offset": i * 1000,
                            "transcript_entry_count": i * 10
                        }
                    },
                    "created_at": f"2025-02-16T12:0{i}:00Z"
                }

            task_data = {"tasks": tasks}
            task_file.write_text(json.dumps(task_data))

            # Act & Assert - Forward traversal
            chain = CheckpointChain(Path(tmpdir), "test_terminal")

            # Start from first checkpoint
            current = checkpoint_ids[0]
            forward_path = [current]

            # Traverse forward
            for _ in range(len(checkpoint_ids) - 1):
                next_cp = chain.get_next(current)
                assert next_cp is not None, f"Expected next checkpoint from {current}"
                forward_path.append(next_cp.checkpoint_id)
                current = next_cp.checkpoint_id

            assert forward_path == checkpoint_ids, f"Forward path mismatch: {forward_path} vs {checkpoint_ids}"

            # Backward traversal
            current = checkpoint_ids[-1]
            backward_path = [current]

            # Traverse backward
            for _ in range(len(checkpoint_ids) - 1):
                prev = chain.get_previous(current)
                assert prev is not None, f"Expected previous checkpoint from {current}"
                backward_path.append(prev.checkpoint_id)
                current = prev.checkpoint_id

            # Reverse backward path to compare with forward
            backward_path_reversed = list(reversed(backward_path))
            assert backward_path_reversed == checkpoint_ids, f"Backward path mismatch: {backward_path_reversed} vs {checkpoint_ids}"

    def test_chain_isolation_different_chains_dont_interfere(self):
        """
        Test that different chains don't interfere with each other.

        Given: A task tracker file with 2 separate chains (chain_a and chain_b)
        When: Querying each chain separately
        Then: Only checkpoints from the respective chain are returned
        """
        # Arrange
        chain_a_id = str(uuid4())
        chain_b_id = str(uuid4())
        checkpoint_a1 = str(uuid4())
        checkpoint_a2 = str(uuid4())
        checkpoint_b1 = str(uuid4())
        checkpoint_b2 = str(uuid4())

        with tempfile.TemporaryDirectory() as tmpdir:
            task_file = Path(tmpdir) / "test_terminal_tasks.json"

            task_data = {
                "tasks": {
                    "task_a1": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_a1,
                                "parent_checkpoint_id": None,
                                "chain_id": chain_a_id,
                                "saved_at": "2025-02-16T12:00:00Z",
                                "transcript_offset": 0,
                                "transcript_entry_count": 0
                            }
                        },
                        "created_at": "2025-02-16T12:00:00Z"
                    },
                    "task_a2": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_a2,
                                "parent_checkpoint_id": checkpoint_a1,
                                "chain_id": chain_a_id,
                                "saved_at": "2025-02-16T12:05:00Z",
                                "transcript_offset": 1000,
                                "transcript_entry_count": 10
                            }
                        },
                        "created_at": "2025-02-16T12:05:00Z"
                    },
                    "task_b1": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_b1,
                                "parent_checkpoint_id": None,
                                "chain_id": chain_b_id,
                                "saved_at": "2025-02-16T13:00:00Z",
                                "transcript_offset": 0,
                                "transcript_entry_count": 0
                            }
                        },
                        "created_at": "2025-02-16T13:00:00Z"
                    },
                    "task_b2": {
                        "metadata": {
                            "handoff": {
                                "checkpoint_id": checkpoint_b2,
                                "parent_checkpoint_id": checkpoint_b1,
                                "chain_id": chain_b_id,
                                "saved_at": "2025-02-16T13:05:00Z",
                                "transcript_offset": 500,
                                "transcript_entry_count": 5
                            }
                        },
                        "created_at": "2025-02-16T13:05:00Z"
                    }
                }
            }

            task_file.write_text(json.dumps(task_data))

            # Act
            chain = CheckpointChain(Path(tmpdir), "test_terminal")

            chain_a = chain.get_chain(chain_a_id)
            chain_b = chain.get_chain(chain_b_id)

            # Assert
            assert len(chain_a) == 2, f"Chain A should have 2 checkpoints, got {len(chain_a)}"
            assert len(chain_b) == 2, f"Chain B should have 2 checkpoints, got {len(chain_b)}"

            # Verify chain A checkpoints
            chain_a_ids = [cp.checkpoint_id for cp in chain_a]
            assert checkpoint_a1 in chain_a_ids, "Chain A should contain checkpoint_a1"
            assert checkpoint_a2 in chain_a_ids, "Chain A should contain checkpoint_a2"
            assert checkpoint_b1 not in chain_a_ids, "Chain A should NOT contain checkpoint_b1"
            assert checkpoint_b2 not in chain_a_ids, "Chain A should NOT contain checkpoint_b2"

            # Verify chain B checkpoints
            chain_b_ids = [cp.checkpoint_id for cp in chain_b]
            assert checkpoint_b1 in chain_b_ids, "Chain B should contain checkpoint_b1"
            assert checkpoint_b2 in chain_b_ids, "Chain B should contain checkpoint_b2"
            assert checkpoint_a1 not in chain_b_ids, "Chain B should NOT contain checkpoint_a1"
            assert checkpoint_a2 not in chain_b_ids, "Chain B should NOT contain checkpoint_a2"

            # Verify get_latest returns correct checkpoint for each chain
            latest_a = chain.get_latest(chain_a_id)
            latest_b = chain.get_latest(chain_b_id)

            assert latest_a.checkpoint_id == checkpoint_a2, f"Chain A latest should be checkpoint_a2, got {latest_a.checkpoint_id}"
            assert latest_b.checkpoint_id == checkpoint_b2, f"Chain B latest should be checkpoint_b2, got {latest_b.checkpoint_id}"

#!/usr/bin/env python3
"""
Basic usage example for the handoff package.

This example demonstrates how to:
1. Create a HandoffStore instance
2. Save handoff data
3. Load handoff data
4. Work with checkpoint chains
"""

import json

from core.checkpoint_chain import CheckpointChain
from core.models import HandoffCheckpoint, PendingOperation


def example_basic_handoff():
    """Basic handoff save and load example."""
    print("=== Basic Handoff Example ===\n")

    # Create a handoff checkpoint
    checkpoint = HandoffCheckpoint(
        checkpoint_id="ckpt_001",
        parent_checkpoint_id=None,
        chain_id="chain_001",
        timestamp="2026-02-17T12:00:00Z",
        task="Refactor the authentication module",
        last_user_message="Please refactor the auth module to use JWT tokens",
        transcript="User: Please refactor the auth module\\nAssistant: I'll help with that...",
        transcript_offset=0,
        transcript_entry_count=5,
        visual_context=None,
        pending_operations=[
            PendingOperation(type="edit", target="src/auth.py", status="pending")
        ],
        metadata_checksum="abc123",
        metadata={"file_count": 3, "test_coverage": 0.85},
    )

    # Display checkpoint
    print(f"Checkpoint ID: {checkpoint.checkpoint_id}")
    print(f"Task: {checkpoint.task}")
    print(f"Pending Operations: {len(checkpoint.pending_operations)}")
    print()


def example_checkpoint_chain():
    """Checkpoint chain traversal example."""
    print("=== Checkpoint Chain Example ===\n")

    # Create a chain of checkpoints
    checkpoints = [
        HandoffCheckpoint(
            checkpoint_id=f"ckpt_{i:03d}",
            parent_checkpoint_id=f"ckpt_{i - 1:03d}" if i > 0 else None,
            chain_id="chain_001",
            timestamp="2026-02-17T12:00:00Z",
            task=f"Step {i}: Implementation",
            last_user_message=f"Complete step {i}",
            transcript="",
            transcript_offset=0,
            transcript_entry_count=1,
            visual_context=None,
            pending_operations=[],
            metadata_checksum="",
            metadata={"step": i},
        )
        for i in range(1, 4)
    ]

    # Create chain
    chain = CheckpointChain(checkpoints)

    # Display chain
    print(f"Chain ID: {checkpoints[0].chain_id}")
    print(f"Total checkpoints: {len(checkpoints)}")
    print(f"Latest checkpoint: {chain.get_latest().checkpoint_id}")
    print()

    # Traverse chain
    print("Chain traversal:")
    current = chain.get_latest()
    while current:
        print(f"  - {current.checkpoint_id}: {current.task}")
        current = chain.get_previous(current.checkpoint_id)


def example_serialization():
    """HandoffCheckpoint serialization example."""
    print("=== Serialization Example ===\n")

    checkpoint = HandoffCheckpoint(
        checkpoint_id="ckpt_ser_001",
        parent_checkpoint_id=None,
        chain_id="chain_ser_001",
        timestamp="2026-02-17T12:00:00Z",
        task="Example task",
        last_user_message="Example message",
        transcript="Example transcript",
        transcript_offset=0,
        transcript_entry_count=1,
        visual_context=None,
        pending_operations=[
            PendingOperation(type="edit", target="file.py", status="pending")
        ],
        metadata_checksum="checksum123",
        metadata={"key": "value"},
    )

    # Serialize to dict
    data = checkpoint.to_dict()
    print("Serialized:")
    print(json.dumps(data, indent=2, default=str))
    print()

    # Deserialize from dict
    restored = HandoffCheckpoint.from_dict(data)
    print(f"Deserialized checkpoint ID: {restored.checkpoint_id}")
    print(f"Match: {restored == checkpoint}")


if __name__ == "__main__":
    example_basic_handoff()
    example_checkpoint_chain()
    example_serialization()

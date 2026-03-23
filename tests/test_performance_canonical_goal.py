"""Performance baseline tests for canonical_goal extraction.

This module establishes performance baselines before implementing
extract_last_substantive_user_message() to ensure the new implementation
meets the < 100ms target for 1000-entry transcripts.
"""

import json
import time
from pathlib import Path

from core.hooks.__lib.transcript import TranscriptParser


def create_synthetic_transcript(entry_count: int, output_path: Path) -> None:
    """Create a synthetic transcript for performance testing.

    Args:
        entry_count: Number of transcript entries to generate
        output_path: Path where transcript will be written
    """
    entries = []
    for i in range(entry_count):
        entries.append(
            {
                "type": "user",
                "timestamp": "2026-03-08T12:00:00Z",
                "message": {"content": [f"Test message {i} with some content"]},
            }
        )

    with open(output_path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def test_performance_baseline_100_entries(tmp_path: Path) -> None:
    """Establish baseline performance for 100-entry transcript.

    Target: < 10ms for small transcripts
    """
    transcript_path = tmp_path / "test_100_entries.jsonl"
    create_synthetic_transcript(100, transcript_path)

    start = time.perf_counter()
    parser = TranscriptParser(transcript_path)
    entries = parser._get_parsed_entries()  # Fixed: use _get_parsed_entries()
    elapsed = time.perf_counter() - start

    print(f"100 entries: {elapsed * 1000:.2f}ms")
    assert elapsed < 0.010, f"Too slow: {elapsed * 1000:.2f}ms for 100 entries"


def test_performance_baseline_1000_entries(tmp_path: Path) -> None:
    """Establish baseline performance for 1000-entry transcript.

    Target: < 100ms for large transcripts (requirement from plan)
    """
    transcript_path = tmp_path / "test_1000_entries.jsonl"
    create_synthetic_transcript(1000, transcript_path)

    start = time.perf_counter()
    parser = TranscriptParser(transcript_path)
    entries = parser._get_parsed_entries()  # Fixed: use _get_parsed_entries()
    elapsed = time.perf_counter() - start

    print(f"1000 entries: {elapsed * 1000:.2f}ms")
    assert elapsed < 0.100, (
        f"Too slow: {elapsed * 1000:.2f}ms for 1000 entries (target: <100ms)"
    )

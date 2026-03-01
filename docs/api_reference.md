# API Reference

This document provides detailed API documentation for the handoff package's public interfaces.

## Public API

### `HandoffStorage` Protocol

Type-safe protocol defining the handoff storage interface.

```python
from handoff import HandoffStorage
from typing import runtime_checkable

@runtime_checkable
class HandoffStorage(Protocol):
    """Protocol defining handoff storage interface."""

    def save_handoff(
        self,
        task_name: str,
        terminal_id: str,
        data: dict[str, Any]
    ) -> Path:
        """Save handoff data to storage.

        Args:
            task_name: Task identifier for the handoff
            terminal_id: Terminal identifier for isolation
            data: Dictionary containing handoff data

        Returns:
            Path to the saved handoff file

        Raises:
            ValueError: If data validation fails
            IOError: If write operation fails
        """
        ...

    def load_handoff(
        self,
        task_name: str,
        terminal_id: str,
        strict: bool = True
    ) -> dict[str, Any] | None:
        """Load handoff data from storage.

        Args:
            task_name: Task identifier for the handoff
            terminal_id: Terminal identifier for isolation
            strict: If True, raise exception on validation error
                   If False, return None or partial data on error

        Returns:
            Handoff data dictionary, or None if not found

        Raises:
            ValueError: If checksum validation fails (when strict=True)
        """
        ...

    def list_handoffs(
        self,
        task_name: str,
        terminal_id: str
    ) -> list[Path]:
        """List all handoff versions for a task.

        Args:
            task_name: Task identifier
            terminal_id: Terminal identifier

        Returns:
            List of paths to handoff files, sorted by version (newest first)
        """
        ...

    def delete_handoff(
        self,
        task_name: str,
        terminal_id: str,
        version: int
    ) -> bool:
        """Delete specific handoff version.

        Args:
            task_name: Task identifier
            terminal_id: Terminal identifier
            version: Handoff version to delete

        Returns:
            True if deleted, False if not found
        """
        ...
```

#### Usage Example

```python
# Any class implementing HandoffStorage methods satisfies the protocol
class TaskTrackerStorage:
    def save_handoff(self, task_name: str, terminal_id: str, data: dict) -> Path:
        # Implementation here
        ...

    def load_handoff(self, task_name: str, terminal_id: str, strict: bool = True):
        # Implementation here
        ...

    def list_handoffs(self, task_name: str, terminal_id: str):
        # Implementation here
        ...

    def delete_handoff(self, task_name: str, terminal_id: str, version: int):
        # Implementation here
        ...

# Runtime type checking
storage = TaskTrackerStorage()
assert isinstance(storage, HandoffStorage)  # Passes

# Type checker knows storage has these methods
path = storage.save_handoff("my-task", "terminal-1", {"data": "value"})
```

### Utility Functions

#### `compute_metadata_checksum(data: dict[str, Any]) -> str`

Compute SHA256 checksum for handoff metadata.

**Parameters:**
- `data` (dict[str, Any]): Handoff metadata dictionary

**Returns:**
- `str`: Hexadecimal SHA256 checksum

**Example:**
```python
from handoff import compute_metadata_checksum

metadata = {
    "task_name": "my-task",
    "decisions": [{"topic": "Use FastAPI", "decision": "Framework chosen"}]
}
checksum = compute_metadata_checksum(metadata)
print(f"Checksum: {checksum}")  # SHA256 hash
```

#### `validate_handoff_size(data: dict[str, Any], max_size_mb: float = 5.0) -> bool`

Validate handoff data size is within acceptable limits.

**Parameters:**
- `data` (dict[str, Any]): Handoff metadata dictionary
- `max_size_mb` (float): Maximum size in megabytes (default: 5.0)

**Returns:**
- `bool`: True if size is within limits, False otherwise

**Example:**
```python
from handoff import validate_handoff_size

metadata = {"task_name": "my-task", "decisions": [...]}
if validate_handoff_size(metadata, max_size_mb=10.0):
    print("Handoff size is acceptable")
else:
    print("Handoff exceeds size limit")
```

## Data Models

### `HandoffCheckpoint`

Typed handoff checkpoint with chain links (see `handoff.models`).

**Attributes:**
- `checkpoint_id`: Unique checkpoint identifier
- `parent_id`: Parent checkpoint ID (for chain traversal)
- `task_name`: Associated task name
- `terminal_id`: Terminal identifier
- `created_at`: ISO timestamp of creation
- `metadata`: Handoff metadata dictionary

### `PendingOperation`

Fault tracking for incomplete operations (see `handoff.checkpoint_ops`).

**States:**
- `pending`: Operation not yet started
- `in_progress`: Operation currently running
- `completed`: Operation finished successfully
- `failed`: Operation failed

**Validated Targets:**
- Must not be empty
- Must not contain null bytes
- Must not exceed 255 characters

## CLI Interface

### `/hod` Skill

Main command for interacting with handoff system.

```bash
# Show current handoff
/hod

# Summarize current work
/hod "summarize my current work"

# Show handoff quality score
/hod --score

# List all handoffs
/hod --list

# Clean old handoffs
/hod --cleanup --retention 90
```

### Migration Tool

```bash
# Migrate handoffs from old JSON format to task tracker
python -m handoff.migrate --handoff-dir ~/.handoff --dry-run
python -m handoff.migrate --handoff-dir ~/.handoff
```

## Extension Points

### Custom Storage Backends

Implement the `HandoffStorage` protocol to create custom storage backends:

```python
class S3HandoffStorage:
    """S3-based handoff storage."""

    def __init__(self, bucket: str, prefix: str = "handoffs"):
        self.bucket = bucket
        self.prefix = prefix
        self.s3 = boto3.client('s3')

    def save_handoff(self, task_name: str, terminal_id: str, data: dict) -> Path:
        key = f"{self.prefix}/{task_name}/{terminal_id}.json"
        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=json.dumps(data)
        )
        return Path(f"s3://{self.bucket}/{key}")

    # ... implement other methods
```

### Custom Metadata Extractors

Extend `TranscriptParser` to extract custom metadata:

```python
from handoff.hooks.__lib.transcript import TranscriptParser

class CustomTranscriptParser(TranscriptParser):
    def extract_session_patterns(self) -> list[dict]:
        # Custom pattern extraction logic
        patterns = super().extract_session_patterns()
        # Add custom patterns
        return patterns
```

## Type Hints

All public APIs use Python type hints for IDE support and mypy validation:

```python
from handoff import HandoffStorage, compute_metadata_checksum
from pathlib import Path
from typing import Any

def process_handoff(
    storage: HandoffStorage,
    task_name: str,
    data: dict[str, Any]
) -> Path:
    """Type-annotated function with protocol parameter."""
    checksum = compute_metadata_checksum(data)
    data["checksum"] = checksum
    return storage.save_handoff(task_name, "default", data)
```

## Error Handling

All public APIs follow these error handling patterns:

1. **Validation errors** → `ValueError` with descriptive message
2. **I/O errors** → `IOError` or `OSError` with context
3. **Not found errors** → `None` return (non-strict mode)
4. **Checksum validation** → `ValueError` in strict mode

## See Also

- [ARCHITECTURE.md](../ARCHITECTURE.md) - System architecture and design
- [examples/](../examples/) - Usage examples and integration patterns
- [CHANGELOG.md](../CHANGELOG.md) - Version history

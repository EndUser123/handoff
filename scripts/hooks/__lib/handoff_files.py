#!/usr/bin/env python3
"""File-based storage for the Handoff V2 envelope."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from scripts.hooks.__lib.handoff_store import FileLock, atomic_write_with_retry
from scripts.hooks.__lib.handoff_v2 import (
    HandoffValidationError,
    SNAPSHOT_PENDING,
    SNAPSHOT_REJECTED_STALE,
    compute_checksum,
    mark_snapshot_status,
    parse_iso8601,
    utcnow,
    validate_envelope,
)

logger = logging.getLogger(__name__)

# Configure logging for handoff file operations
# Logs will be written to .claude/logs/handoff_files.log
_log_file_path = (
    Path(__file__).resolve().parents[3] / ".claude" / "logs" / "handoff_files.log"
)
_log_file_path.parent.mkdir(parents=True, exist_ok=True)
if not logger.handlers:
    _handler = logging.FileHandler(_log_file_path, encoding="utf-8")
    _handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    logger.addHandler(_handler)
logger.setLevel(logging.DEBUG)


class HandoffFileStorage:
    """Persist one Handoff V2 envelope per terminal."""

    def __init__(self, project_root: Path, terminal_id: str):
        self._validate_terminal_id(terminal_id)
        self.project_root = project_root
        self.terminal_id = terminal_id
        self.handoff_dir = project_root / ".claude" / "state" / "handoff"
        self.handoff_file = self.handoff_dir / f"{terminal_id}_handoff.json"

    @staticmethod
    def _validate_terminal_id(terminal_id: str) -> None:
        if not terminal_id or not terminal_id.strip():
            raise ValueError("terminal_id cannot be empty or whitespace-only")
        if "\x00" in terminal_id:
            raise ValueError("terminal_id cannot contain null bytes")
        if ".." in terminal_id or terminal_id.startswith("./"):
            raise ValueError("terminal_id cannot contain path traversal sequences")
        if terminal_id.startswith("/") or terminal_id.startswith("\\"):
            raise ValueError("terminal_id cannot be an absolute path")

    def save_handoff(self, payload: dict[str, Any]) -> bool:
        """Validate and persist the V2 payload."""
        try:
            logger.debug(
                "[HandoffFileStorage] save_handoff called: terminal_id=%s, file=%s",
                self.terminal_id,
                self.handoff_file,
            )

            validate_envelope(payload)
            logger.debug("[HandoffFileStorage] Envelope validation passed")

            self.handoff_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(
                "[HandoffFileStorage] Directory created/verified: %s", self.handoff_dir
            )

            serialized = json.dumps(payload, indent=2, ensure_ascii=False)
            logger.debug(
                "[HandoffFileStorage] Serialized envelope: %d bytes",
                len(serialized),
            )

            lock_file = self.handoff_file.with_suffix(".lock")
            with FileLock(lock_file, timeout=5.0) as lock:
                if not lock:
                    logger.warning(
                        "[HandoffFileStorage] Failed to acquire lock for %s",
                        self.handoff_file.name,
                    )
                    return False

                logger.debug(
                    "[HandoffFileStorage] Lock acquired for %s", lock_file.name
                )

                fd, temp_path = tempfile.mkstemp(
                    suffix=".tmp",
                    dir=str(self.handoff_dir),
                    prefix=f"{self.terminal_id}_handoff_",
                )
                logger.debug("[HandoffFileStorage] Temp file created: %s", temp_path)

                try:
                    # CRITICAL: Compute checksum from in-memory payload BEFORE any file write
                    # This prevents TOCTOU race condition and eliminates double I/O (PERF-001)
                    expected_checksum = payload.get("checksum")
                    if expected_checksum:
                        # Validate checksum from in-memory payload
                        computed_checksum = compute_checksum(payload)
                        if computed_checksum != expected_checksum:
                            logger.error(
                                "[HandoffFileStorage] Checksum mismatch before write: expected=%s, computed=%s",
                                expected_checksum,
                                computed_checksum,
                            )
                            return False
                        logger.debug(
                            "[HandoffFileStorage] Checksum validated from memory: %s",
                            computed_checksum,
                        )

                    # Write to temp file
                    with os.fdopen(fd, "w", encoding="utf-8") as handle:
                        handle.write(serialized)
                    logger.debug(
                        "[HandoffFileStorage] Wrote %d bytes to temp file",
                        len(serialized),
                    )

                    # Verify temp file integrity BEFORE atomic move (still within FileLock context)
                    # This prevents TOCTOU race condition (LOGIC-001)
                    try:
                        with open(temp_path, encoding="utf-8") as verify_handle:
                            temp_payload = json.load(verify_handle)
                        # Verify checksum from temp file
                        temp_checksum = compute_checksum(temp_payload)
                        if expected_checksum and temp_checksum != expected_checksum:
                            logger.error(
                                "[HandoffFileStorage] Checksum mismatch in temp file: expected=%s, actual=%s",
                                expected_checksum,
                                temp_checksum,
                            )
                            os.unlink(temp_path)
                            return False
                        logger.debug(
                            "[HandoffFileStorage] Temp file checksum verified: %s",
                            temp_checksum,
                        )
                    except (json.JSONDecodeError, OSError) as verify_exc:
                        logger.error(
                            "[HandoffFileStorage] Failed to verify temp file: %s",
                            verify_exc,
                        )
                        try:
                            os.unlink(temp_path)
                        except OSError:
                            pass
                        return False

                    # Atomic move (now safe because we verified within FileLock context)
                    atomic_write_with_retry(temp_path, self.handoff_file)
                    logger.info(
                        "[HandoffFileStorage] Handoff saved successfully: %s -> %s",
                        temp_path,
                        self.handoff_file,
                    )

                    # Verify file was actually created
                    if not self.handoff_file.exists():
                        logger.error(
                            "[HandoffFileStorage] File does not exist after atomic_write: %s",
                            self.handoff_file,
                        )
                        return False

                    file_size = self.handoff_file.stat().st_size
                    logger.info(
                        "[HandoffFileStorage] File verified: %s (%d bytes)",
                        self.handoff_file.name,
                        file_size,
                    )

                    return True
                except Exception as inner_exc:
                    logger.error(
                        "[HandoffFileStorage] Exception during file write: %s",
                        inner_exc,
                        exc_info=True,
                    )
                    try:
                        os.unlink(temp_path)
                    except OSError:
                        pass
                    raise
        except HandoffValidationError as exc:
            logger.error(
                "[HandoffFileStorage] Invalid handoff payload: %s",
                exc,
                exc_info=True,
            )
            return False
        except Exception as exc:
            logger.error(
                "[HandoffFileStorage] Exception saving handoff: %s",
                exc,
                exc_info=True,
            )
            return False

    def load_handoff(self) -> dict[str, Any] | None:
        """Load and validate the current V2 payload."""
        try:
            payload = self.load_raw_handoff()
            if not payload:
                return None
            validate_envelope(payload)

            # CRIT-006 FIX: Guard against stale pending handoffs.
            # Snapshots only get rejected at restore time, so expired pending handoffs
            # can accumulate in the state directory indefinitely. Mark them stale here
            # so they won't be returned as valid for restore.
            snapshot = payload["resume_snapshot"]
            snapshot_status = snapshot.get("status")
            if snapshot_status == SNAPSHOT_PENDING:
                expires_at = snapshot.get("expires_at")
                if expires_at:
                    try:
                        if parse_iso8601(expires_at) < utcnow():
                            # Expired pending snapshot — mark as rejected_stale
                            reason = "snapshot expired while pending (auto-rejected at load time)"
                            marked = mark_snapshot_status(
                                payload,
                                status=SNAPSHOT_REJECTED_STALE,
                                session_id="system",
                                reason=reason,
                            )
                            self.save_handoff(marked)
                            logger.info(
                                "[HandoffFileStorage] Auto-rejected stale pending handoff: %s (%s)",
                                self.handoff_file.name,
                                reason,
                            )
                            return None
                    except Exception:
                        pass  # If time parsing fails, fall through to terminal check

            snapshot_terminal = snapshot["terminal_id"]
            if snapshot_terminal != self.terminal_id:
                logger.warning(
                    "[HandoffFileStorage] Terminal mismatch in %s: expected %s, got %s",
                    self.handoff_file.name,
                    self.terminal_id,
                    snapshot_terminal,
                )
                return None
            return payload
        except HandoffValidationError as exc:
            logger.error(
                "[HandoffFileStorage] Invalid handoff payload in %s: %s",
                self.handoff_file.name,
                exc,
            )
            return None
        except json.JSONDecodeError as exc:
            logger.error(
                "[HandoffFileStorage] JSON parse error in %s: %s",
                self.handoff_file.name,
                exc,
            )
            return None
        except Exception as exc:
            logger.error("[HandoffFileStorage] Exception loading handoff: %s", exc)
            return None

    def load_raw_handoff(self) -> dict[str, Any] | None:
        """Load the current payload without validation."""
        try:
            if not self.handoff_file.exists():
                return None
            with open(self.handoff_file, encoding="utf-8") as handle:
                payload = json.load(handle)
            if not isinstance(payload, dict):
                logger.error(
                    "[HandoffFileStorage] Raw handoff payload is not a dict in %s",
                    self.handoff_file.name,
                )
                return None
            return payload
        except json.JSONDecodeError as exc:
            logger.error(
                "[HandoffFileStorage] JSON parse error in %s: %s",
                self.handoff_file.name,
                exc,
            )
            return None
        except Exception as exc:
            logger.error("[HandoffFileStorage] Exception loading raw handoff: %s", exc)
            return None

    def update_snapshot_status(
        self, *, status: str, session_id: str, reason: str | None = None
    ) -> bool:
        """Load the current payload, update snapshot status, and persist it."""
        payload = self.load_handoff()
        if not payload:
            return False
        updated = mark_snapshot_status(
            payload, status=status, session_id=session_id, reason=reason
        )
        return self.save_handoff(updated)

    def update_snapshot_status_from_payload(
        self,
        payload: dict[str, Any],
        *,
        status: str,
        session_id: str,
        reason: str | None = None,
    ) -> bool:
        """Persist a status update starting from a raw payload."""
        updated = mark_snapshot_status(
            payload, status=status, session_id=session_id, reason=reason
        )
        return self.save_handoff(updated)

    def read_accumulated_state(self) -> list[dict[str, Any]]:
        """Read the per-terminal accumulated JSONL state.

        Returns list of events from the JSONL file, or empty list.
        Non-existent or corrupt files return empty list (non-fatal).
        """
        accum_path = self.handoff_dir / f"{self.terminal_id}_accumulated.jsonl"
        if not accum_path.exists():
            return []

        events: list[dict[str, Any]] = []
        try:
            with open(accum_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                        if isinstance(event, dict):
                            events.append(event)
                    except json.JSONDecodeError:
                        continue  # Skip malformed lines
        except OSError:
            return []

        return events

    def truncate_accumulated_state(self) -> bool:
        """Truncate the accumulated JSONL file (called on new session start)."""
        accum_path = self.handoff_dir / f"{self.terminal_id}_accumulated.jsonl"
        try:
            if accum_path.exists():
                accum_path.unlink()
            return True
        except OSError:
            return False

    def delete_handoff(self) -> bool:
        """Delete the per-terminal handoff file."""
        try:
            if self.handoff_file.exists():
                self.handoff_file.unlink()
            return True
        except Exception as exc:
            logger.error("[HandoffFileStorage] Failed to delete handoff: %s", exc)
            return False

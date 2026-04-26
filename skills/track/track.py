#!/usr/bin/env python3
"""
track.py - Work Thread Tracker.

Tracks work-in-progress across terminals and sessions. Each terminal is
isolated — reads only its own terminal context, never shared session state.

Usage:
    python track.py                          # Show catch-up brief
    python track.py brief                    # Same as above
    python track.py "working on <intent>"  # Start/update thread
    python track.py next "<step>"          # Update next step
    python track.py done "<checkpoint>"     # Update checkpoint
    python track.py blocker "<blocker>"    # Update blocker
    python track.py list                     # List all threads
    python track.py thread <thread-id>       # Switch to thread
    python track.py info                    # Full thread detail
    python track.py done                    # Archive current thread
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

TRACK_DIR = Path.home() / ".claude" / "track"
TERMINALS_DIR = Path.home() / ".claude" / "terminals"


def _ensure_track_dir() -> Path:
    TRACK_DIR.mkdir(parents=True, exist_ok=True)
    return TRACK_DIR


def _current_thread_file_for_terminal(terminal_id: str) -> Path:
    """Per-terminal current thread pointer — ensures terminal isolation."""
    return TRACK_DIR / f"current_{terminal_id}.txt"


def _threads_dir() -> Path:
    """Per-terminal thread storage — each terminal is fully isolated."""
    terminal_id = _detect_terminal_id()
    d = TRACK_DIR / f"threads_{terminal_id}"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Terminal ID Detection (same logic as term.py / hooks)
# ---------------------------------------------------------------------------


def _detect_terminal_id() -> str:
    """Detect current terminal ID."""
    tid = os.environ.get("CLAUDE_TERMINAL_ID", "").strip()
    if tid:
        return _normalize_id(tid, "env")
    wt = os.environ.get("WT_SESSION", "").strip()
    if wt:
        return _normalize_id(wt, "console")
    if sys.platform == "win32":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            h = kernel32.GetConsoleWindow()
            if h:
                return _normalize_id(hex(h)[2:], "console")
        except Exception:
            pass
    # Temp file fallback
    tfile = Path(tempfile.gettempdir()) / "claude_terminal_id.txt"
    if tfile.exists():
        try:
            c = tfile.read_text().strip()
            if c:
                return _normalize_id(c, "env")
        except Exception:
            pass

    raw = f"pid_{os.getpid()}_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    return _normalize_id(raw, "fallback")


def _normalize_id(raw_id: str, source: str) -> str:
    if not raw_id:
        return f"{source}_unknown"
    # Reject path traversal attempts
    if ".." in raw_id or "/" in raw_id or "\\" in raw_id:
        raise ValueError(f"Invalid terminal ID (path traversal attempt): {raw_id!r}")
    known = ("env_", "console_", "fallback_")
    if raw_id.startswith(known):
        return raw_id
    if raw_id.startswith("ConsoleHost_"):
        return f"console_{raw_id[12:]}"
    if raw_id.startswith("session_"):
        return f"env_{raw_id[8:]}"
    return f"{source}_{raw_id}"


# ---------------------------------------------------------------------------
# Thread ID / Storage
# ---------------------------------------------------------------------------


def _make_thread_id(intent: str) -> str:
    """Create a stable thread ID from intent text."""
    h = hashlib.sha256(intent.encode()).hexdigest()[:12]
    return h


def _get_current_thread_id() -> str | None:
    """Get the currently active thread ID for this terminal."""
    terminal_id = _detect_terminal_id()
    f = _current_thread_file_for_terminal(terminal_id)
    if not f.exists():
        return None
    try:
        return f.read_text().strip() or None
    except Exception:
        return None


def _set_current_thread(thread_id: str | None) -> None:
    """Set the currently active thread for this terminal."""
    terminal_id = _detect_terminal_id()
    _ensure_track_dir()
    f = _current_thread_file_for_terminal(terminal_id)
    if thread_id is None:
        if f.exists():
            f.unlink()
        return
    f.write_text(thread_id)


def _load_thread(thread_id: str) -> dict[str, Any]:
    """Load a thread's data from this terminal's thread storage."""
    f = _threads_dir() / f"{thread_id}.json"
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_thread(thread_id: str, data: dict[str, Any]) -> None:
    """Save a thread's data to this terminal's thread storage."""
    _ensure_track_dir()
    f = _threads_dir() / f"{thread_id}.json"
    f.write_text(json.dumps(data, indent=2))


def _list_threads(include_archived: bool = False) -> list[dict[str, Any]]:
    """List all threads for this terminal, sorted by last_activity descending."""
    threads_dir = _threads_dir()
    threads = []

    if threads_dir.is_dir():
        for f in threads_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                if not include_archived and data.get("archived"):
                    continue
                threads.append(data)
            except Exception:
                pass

    threads.sort(key=lambda t: t.get("last_activity", 0), reverse=True)
    return threads


# ---------------------------------------------------------------------------
# Reconstruction from other sources
# ---------------------------------------------------------------------------


def _reconstruct_from_terminal() -> dict[str, Any] | None:
    """Try to reconstruct from /term terminal files for THIS terminal only."""
    terminal_id = _detect_terminal_id()
    term_file = TERMINALS_DIR / f"{terminal_id}.json"
    if term_file.exists():
        try:
            data = json.loads(term_file.read_text())
            return {
                "reconstructed": True,
                "intent": data.get("intent", ""),
                "checkpoint": data.get("checkpoint", ""),
                "next_step": data.get("next_step", ""),
                "blocker": data.get("blocker", ""),
                "source": "term",
            }
        except Exception:
            pass
    return None


def _reconstruct() -> dict[str, Any]:
    """Reconstruct thread context from this terminal's sources only."""
    term_data = _reconstruct_from_terminal()
    if term_data and term_data.get("intent"):
        return term_data

    return {
        "reconstructed": True,
        "intent": "",
        "checkpoint": "",
        "next_step": "",
        "blocker": "",
        "source": "none",
    }


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_brief() -> None:
    """Show catch-up brief for current thread or reconstructed context."""
    thread_id = _get_current_thread_id()

    if thread_id:
        data = _load_thread(thread_id)
        if data and not data.get("archived"):
            _show_brief(data)
            return

    # No active thread — reconstruct
    data = _reconstruct()
    if data.get("source") != "none" and data.get("intent"):
        print("[Reconstructed from last session]")
        _show_brief(data)
    else:
        print('No active work thread. Run `/track "working on <intent>"` to start one.')


def _show_brief(data: dict[str, Any]) -> None:
    intent = data.get("intent", "unknown")
    checkpoint = data.get("checkpoint", "")
    next_step = data.get("next_step", "")
    blocker = data.get("blocker", "")
    thread_id = data.get("thread_id", "")

    print(f"Thread: {thread_id}")
    print(f"Intent: {intent}")
    if checkpoint:
        print(f"Done: {checkpoint}")
    if next_step:
        print(f"Next: {next_step}")
    if blocker:
        print(f"Blocker: {blocker}")
    elif not next_step and not checkpoint:
        print("(no checkpoint or next step set)")


def cmd_capture(intent: str) -> None:
    """Start or update a work thread with the given intent."""
    thread_id = _make_thread_id(intent)
    existing = _load_thread(thread_id)

    terminal_id = _detect_terminal_id()
    cwd = str(Path.cwd())

    data = {
        "thread_id": thread_id,
        "intent": intent,
        "checkpoint": existing.get("checkpoint", ""),
        "next_step": existing.get("next_step", ""),
        "blocker": existing.get("blocker", ""),
        "terminal_id": terminal_id,
        "cwd": cwd,
        "last_activity": int(time.time()),
        "created_at": existing.get("created_at", int(time.time())),
        "archived": False,
        "files_modified": existing.get("files_modified", []),
    }

    _save_thread(thread_id, data)
    _set_current_thread(thread_id)

    print(f"Thread: {thread_id}")
    print(f"Intent: {intent}")
    if existing.get("checkpoint"):
        print(f"Existing checkpoint: {existing['checkpoint']}")
    if existing.get("next_step"):
        print(f"Existing next: {existing['next_step']}")
    print("(thread updated)")


def cmd_next(step: str) -> None:
    """Update the next-step field of current thread."""
    thread_id = _get_current_thread_id()
    if not thread_id:
        data = _reconstruct()
        if data.get("reconstructed"):
            print("No active thread. Starting one with reconstructed context...")
            intent = data.get("intent", "unknown work")
            cmd_capture(intent)
            thread_id = _get_current_thread_id()

    if not thread_id:
        print('No active thread. Run `/track "working on <intent>"` first.')
        return

    data = _load_thread(thread_id)
    data["next_step"] = step
    data["last_activity"] = int(time.time())
    _save_thread(thread_id, data)
    print(f"Next step set: {step}")


def cmd_done(checkpoint: str) -> None:
    """Update the checkpoint field of current thread."""
    thread_id = _get_current_thread_id()
    if not thread_id:
        data = _reconstruct()
        if data.get("reconstructed"):
            print("No active thread. Starting one with reconstructed context...")
            intent = data.get("intent", "unknown work")
            cmd_capture(intent)
            thread_id = _get_current_thread_id()

    if not thread_id:
        print('No active thread. Run `/track "working on <intent>"` first.')
        return

    data = _load_thread(thread_id)
    data["checkpoint"] = checkpoint
    data["last_activity"] = int(time.time())
    _save_thread(thread_id, data)
    print(f"Checkpoint saved: {checkpoint}")


def cmd_blocker(blocker: str) -> None:
    """Update the blocker field of current thread."""
    thread_id = _get_current_thread_id()
    if not thread_id:
        data = _reconstruct()
        if data.get("reconstructed") and data.get("intent"):
            print("No active thread. Starting one with reconstructed context...")
            intent = data.get("intent", "unknown work")
            cmd_capture(intent)
            thread_id = _get_current_thread_id()

    if not thread_id:
        print('No active thread. Run `/track "working on <intent>"` first.')
        return

    data = _load_thread(thread_id)
    data["blocker"] = blocker
    data["last_activity"] = int(time.time())
    _save_thread(thread_id, data)
    print(f"Blocker set: {blocker}")


def cmd_list() -> None:
    """List all work threads for this terminal."""
    threads = _list_threads()
    if not threads:
        print("No active work threads.")
        print('Run `/track "working on <intent>"` to start one.')
        return

    print(f"{'Thread ID':<14} {'Intent':<35} {'Last Activity':<12}")
    print("-" * 65)
    current_id = _get_current_thread_id()
    for t in threads:
        tid = t.get("thread_id", "")[:14]
        intent = t.get("intent", "")[:35]
        last_ts = t.get("last_activity", 0)
        last_str = datetime.fromtimestamp(last_ts).strftime("%m-%d %H:%M") if last_ts else "-"
        current = " <-" if tid == current_id else ""
        print(f"{tid:<14} {intent:<35} {last_str:<12}{current}")


def cmd_info() -> None:
    """Show full detail for current thread."""
    thread_id = _get_current_thread_id()

    if not thread_id:
        data = _reconstruct()
        if data.get("source") != "none":
            print("[Reconstructed from last session]")
            for k, v in data.items():
                if v:
                    print(f"  {k}: {v}")
            return
        print('No active thread. Run `/track "working on <intent>"` to start one.')
        return

    data = _load_thread(thread_id)
    if not data:
        print(f"Thread '{thread_id}' not found.")
        return

    print(f"Thread ID:    {data.get('thread_id', '')}")
    print(f"Intent:      {data.get('intent', '')}")
    print(f"Checkpoint:  {data.get('checkpoint', '')}")
    print(f"Next Step:   {data.get('next_step', '')}")
    print(f"Blocker:     {data.get('blocker', '')}")
    print(f"Terminal:     {data.get('terminal_id', '')}")
    print(f"CWD:          {data.get('cwd', '')}")
    last_ts = data.get("last_activity", 0)
    print(
        f"Last Active:  {datetime.fromtimestamp(last_ts).strftime('%Y-%m-%d %H:%M:%S') if last_ts else '-'}"
    )
    created = data.get("created_at", 0)
    print(
        f"Created:     {datetime.fromtimestamp(created).strftime('%Y-%m-%d %H:%M:%S') if created else '-'}"
    )
    files = data.get("files_modified", [])
    if files:
        print(f"Files:       {', '.join(files[:10])}")


def cmd_archive() -> None:
    """Mark current thread as complete/designived."""
    thread_id = _get_current_thread_id()
    if not thread_id:
        print("No active thread to archive.")
        return

    data = _load_thread(thread_id)
    data["archived"] = True
    data["last_activity"] = int(time.time())
    _save_thread(thread_id, data)
    _set_current_thread(None)
    print(f"Thread '{thread_id}' archived.")


def cmd_prune(older_than_days: int = 30) -> None:
    """Delete archived threads older than N days."""
    threads_dir = _threads_dir()
    if not threads_dir.is_dir():
        print("No threads directory found.")
        return

    cutoff = int(time.time()) - (older_than_days * 86400)
    removed = 0
    for f in threads_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            if data.get("archived") and data.get("last_activity", 0) < cutoff:
                f.unlink()
                removed += 1
        except Exception:
            pass

    print(f"Removed {removed} archived thread(s) older than {older_than_days} days.")


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------


def main() -> None:
    if len(sys.argv) < 2:
        cmd_brief()
        return

    cmd = sys.argv[1].lower()

    if cmd == "brief":
        cmd_brief()
    elif cmd == "list":
        cmd_list()
    elif cmd == "info":
        cmd_info()
    elif cmd == "done":
        if len(sys.argv) >= 3:
            cmd_done(sys.argv[2])
        else:
            cmd_archive()
    elif cmd == "archive":
        cmd_archive()
    elif cmd == "next":
        if len(sys.argv) < 3:
            print('Usage: track.py next "<next step>"')
            sys.exit(1)
        cmd_next(sys.argv[2])
    elif cmd == "blocker":
        if len(sys.argv) < 3:
            print('Usage: track.py blocker "<blocker>"')
            sys.exit(1)
        cmd_blocker(sys.argv[2])
    elif cmd == "prune":
        cmd_prune()
    else:
        # Anything else is treated as an intent string
        intent = sys.argv[1]
        cmd_capture(intent)


if __name__ == "__main__":
    main()

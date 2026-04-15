#!/usr/bin/env python3
"""Handoff V2 CLI tool for capture, restore, and debug operations.

Usage:
    python -m scripts.cli capture [--terminal ID] [--transcript PATH]
    python -m scripts.cli restore [--terminal ID]
    python -m scripts.cli list [--terminal ID]
    python -m scripts.cli debug [--terminal ID]
    python -m scripts.cli health [--terminal ID]
    python -m scripts.cli cleanup [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from scripts.config import cleanup_old_handoffs
from scripts.hooks.__lib.handoff_files import HandoffFileStorage
from scripts.hooks.__lib.handoff_v2 import (
    compute_checksum,
    evaluate_for_restore,
    validate_envelope,
)
from scripts.hooks.__lib.terminal_detection import resolve_terminal_key


def cmd_capture(args: argparse.Namespace) -> int:
    """Capture a handoff from the current session state.

    This is primarily useful for testing and debugging. In production,
    the PreCompact hook automatically captures handoffs.
    """
    terminal_id = resolve_terminal_key(args.terminal)

    if not args.transcript:
        print("Error: --transcript is required for capture", file=sys.stderr)
        return 1

    transcript_path = Path(args.transcript)
    if not transcript_path.exists():
        print(f"Error: Transcript not found: {transcript_path}", file=sys.stderr)
        return 1

    # For now, just indicate that capture is handled by the PreCompact hook
    print("Handoff capture is handled by the PreCompact hook.")
    print("To capture manually, trigger a compaction in your terminal.")
    print(f"Terminal ID: {terminal_id}")
    print(f"Transcript: {transcript_path}")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    """Show restore status for the current terminal."""
    terminal_id = resolve_terminal_key(args.terminal)
    project_root = Path.cwd()

    storage = HandoffFileStorage(project_root, terminal_id)
    handoff = storage.load_handoff()

    if not handoff:
        print(f"No handoff found for terminal: {terminal_id}")
        print("\nTo create a handoff, trigger a session compaction.")
        return 0

    # Evaluate for restore
    result = evaluate_for_restore(
        handoff,
        terminal_id=terminal_id,
        source="compact",
        project_root=project_root,
        now=None,
    )

    if result.ok:
        print("HANDOFF RESTORE STATUS: Ready to restore")
        print(f"Schema Version: {handoff['resume_snapshot']['schema_version']}")
        print(f"Created: {handoff['resume_snapshot']['created_at']}")
        print(f"Expires: {handoff['resume_snapshot']['expires_at']}")
        print(f"Status: {handoff['resume_snapshot']['status']}")
        if "quality_score" in handoff["resume_snapshot"]:
            print(f"Quality Score: {handoff['resume_snapshot']['quality_score']:.2f}")
        return 0
    else:
        print("HANDOFF RESTORE STATUS: Not restoreable")
        print(f"Reason: {result.reason}")
        print(f"Created: {handoff['resume_snapshot']['created_at']}")
        print(f"Status: {handoff['resume_snapshot']['status']}")
        return 0


def cmd_list(args: argparse.Namespace) -> int:
    """List all handoffs for the current terminal."""
    terminal_id = resolve_terminal_key(args.terminal)
    project_root = Path.cwd()

    storage = HandoffFileStorage(project_root, terminal_id)
    handoff = storage.load_handoff()

    if not handoff:
        print(f"No handoff found for terminal: {terminal_id}")
        return 0

    snapshot = handoff["resume_snapshot"]
    print(f"Handoff V{snapshot['schema_version']} for terminal: {terminal_id}")
    print(f"Snapshot ID: {snapshot['snapshot_id']}")
    print(f"Created: {snapshot['created_at']}")
    print(f"Expires: {snapshot['expires_at']}")
    print(f"Status: {snapshot['status']}")
    print(f"Goal: {snapshot['goal']}")
    print(f"Active Files: {len(snapshot['active_files'])}")
    print(f"Decisions: {len(snapshot['decision_refs'])}")
    print(f"Evidence Items: {len(snapshot['evidence_refs'])}")

    if "quality_score" in snapshot:
        print(f"Quality Score: {snapshot['quality_score']:.2f}")

    print(f"\nChecksum: {handoff.get('checksum', 'N/A')}")
    return 0


def cmd_debug(args: argparse.Namespace) -> int:
    """Show detailed debug information for the current terminal's handoff."""
    terminal_id = resolve_terminal_key(args.terminal)
    project_root = Path.cwd()

    storage = HandoffFileStorage(project_root, terminal_id)
    handoff = storage.load_handoff()

    if not handoff:
        print(f"No handoff found for terminal: {terminal_id}")
        return 0

    # Validate the handoff
    try:
        validate_envelope(handoff)
        print("✓ Handoff envelope is valid")
    except Exception as exc:
        print(f"✗ Handoff envelope validation failed: {exc}")
        return 1

    # Check checksum
    computed = compute_checksum(handoff)
    stored = handoff.get("checksum")
    if computed == stored:
        print(f"✓ Checksum matches: {stored}")
    else:
        print(f"✗ Checksum mismatch: stored={stored}, computed={computed}")
        return 1

    # Verify transcript still exists
    transcript_path = handoff["resume_snapshot"]["n_1_transcript_path"]
    if transcript_path:
        transcript_file = Path(transcript_path)
        if transcript_file.exists():
            print(f"✓ Transcript exists: {transcript_path}")
        else:
            print(f"✗ Transcript missing: {transcript_path}")
            return 1

    # Show decision register
    decisions = handoff.get("decision_register", [])
    print(f"\nDecision Register ({len(decisions)} decisions):")
    for decision in decisions[:5]:
        print(f"  [{decision['kind']}] {decision['summary'][:60]}...")

    # Show evidence index
    evidence = handoff.get("evidence_index", [])
    print(f"\nEvidence Index ({len(evidence)} items):")
    for item in evidence[:5]:
        h = item.get("content_hash", "N/A")
        print(f"  [{item['type']}] {item['label']} ({h})")

    return 0


def cmd_health(args: argparse.Namespace) -> int:
    """Quick health check for handoff system.

    Returns exit code 0 if healthy, 1 if issues found.
    """
    terminal_id = resolve_terminal_key(args.terminal)
    project_root = Path.cwd()
    storage = HandoffFileStorage(project_root, terminal_id)
    handoff = storage.load_handoff()

    if not handoff:
        print("HEALTH: No handoff found")
        print(f"Terminal: {terminal_id}")
        return 0

    issues = []

    # Check envelope validation
    try:
        validate_envelope(handoff)
    except Exception as exc:
        issues.append(f"envelope validation: {exc}")

    # Check checksum
    computed = compute_checksum(handoff)
    stored = handoff.get("checksum")
    if computed != stored:
        issues.append(f"checksum mismatch (stored={stored}, computed={computed})")

    # Check transcript exists
    transcript_path = handoff["resume_snapshot"]["n_1_transcript_path"]
    if transcript_path:
        if not Path(transcript_path).exists():
            issues.append(f"transcript missing: {transcript_path}")

    if issues:
        print("HEALTH: ISSUES FOUND")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    else:
        print("HEALTH: OK")
        snapshot = handoff.get("resume_snapshot", {})
        print(f"Schema: {snapshot.get('schema_version', 'unknown')}")
        print(f"Created: {snapshot.get('created_at', 'unknown')}")
        print(f"Status: {snapshot.get('status', 'unknown')}")
        return 0


def cmd_cleanup(args: argparse.Namespace) -> int:
    """Clean up old handoffs."""
    project_root = Path.cwd()

    if args.dry_run:
        print("Dry-run mode: showing what would be cleaned")
        print(f"Project root: {project_root}")
        # Count handoffs that would be cleaned

        handoff_dir = project_root / ".claude" / "state" / "handoff"
        if handoff_dir.exists():
            handoffs = list(handoff_dir.glob("*_handoff.json"))
            print(f"Found {len(handoffs)} handoff file(s)")
        else:
            print("No handoff directory found")
        return 0

    count = cleanup_old_handoffs(project_root)
    print(f"Cleaned up {count} old handoff(s)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Handoff V2 CLI tool for capture, restore, and debug operations."
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # capture command
    capture_parser = subparsers.add_parser("capture", help="Capture a handoff")
    capture_parser.add_argument(
        "--terminal", default=None, help="Terminal ID (default: current terminal)"
    )
    capture_parser.add_argument(
        "--transcript", default=None, help="Path to transcript file"
    )

    # restore command
    restore_parser = subparsers.add_parser("restore", help="Show restore status")
    restore_parser.add_argument(
        "--terminal", default=None, help="Terminal ID (default: current terminal)"
    )

    # list command
    list_parser = subparsers.add_parser("list", help="List handoffs")
    list_parser.add_argument(
        "--terminal", default=None, help="Terminal ID (default: current terminal)"
    )

    # debug command
    debug_parser = subparsers.add_parser("debug", help="Show debug information")
    debug_parser.add_argument(
        "--terminal", default=None, help="Terminal ID (default: current terminal)"
    )

    # health command
    health_parser = subparsers.add_parser("health", help="Quick health check")
    health_parser.add_argument(
        "--terminal", default=None, help="Terminal ID (default: current terminal)"
    )

    # cleanup command
    cleanup_parser = subparsers.add_parser("cleanup", help="Clean up old handoffs")
    cleanup_parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be cleaned"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    handlers = {
        "capture": cmd_capture,
        "restore": cmd_restore,
        "list": cmd_list,
        "debug": cmd_debug,
        "health": cmd_health,
        "cleanup": cmd_cleanup,
    }

    handler = handlers.get(args.command)
    if not handler:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        return 1

    return handler(args)


if __name__ == "__main__":
    sys.exit(main())

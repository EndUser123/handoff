"""Regression tests for namespaced snapshot hook entrypoints."""

from __future__ import annotations

import json
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
HOOKS_JSON = PACKAGE_ROOT / "hooks" / "hooks.json"


def test_snapshot_hooks_use_namespaced_entrypoints() -> None:
    manifest = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    commands = [
        hook["command"]
        for entries in manifest["hooks"].values()
        for match in entries
        for hook in match["hooks"]
    ]

    assert "python \"$CLAUDE_PLUGIN_ROOT/scripts/hooks/snapshot_PreCompact.py\"" in commands
    assert "python \"$CLAUDE_PLUGIN_ROOT/scripts/hooks/snapshot_SessionStart.py\"" in commands
    assert "python \"$CLAUDE_PLUGIN_ROOT/scripts/hooks/snapshot_SessionEnd_tldr.py\"" in commands
    assert "python \"$CLAUDE_PLUGIN_ROOT/scripts/hooks/snapshot_UserPromptSubmit.py\"" in commands
    assert all("/scripts/hooks/PreCompact.py\"" not in command for command in commands)
    assert all("/scripts/hooks/SessionStart.py\"" not in command for command in commands)
    assert all("/scripts/hooks/userpromptsubmit_task_injector.py\"" not in command for command in commands)

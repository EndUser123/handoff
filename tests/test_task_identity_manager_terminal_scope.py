#!/usr/bin/env python3
"""Tests for terminal-scoped task identity state."""

from __future__ import annotations

import json

from core.hooks.__lib.task_identity_manager import TaskIdentityManager


def test_global_task_name_env_var_is_ignored(monkeypatch, tmp_path):
    monkeypatch.setenv("TASK_NAME", "other_terminal_task")

    manager = TaskIdentityManager(project_root=tmp_path, terminal_id="console_a")

    assert manager.get_current_task() is None


def test_active_command_is_terminal_scoped(tmp_path):
    manager_a = TaskIdentityManager(project_root=tmp_path, terminal_id="console_a")
    manager_b = TaskIdentityManager(project_root=tmp_path, terminal_id="console_b")

    assert manager_a.record_active_command("search", "execution")
    assert manager_a.get_current_task() == "adhoc_search"
    assert manager_b.get_current_task() is None


def test_legacy_shared_active_command_file_is_ignored(tmp_path):
    legacy_file = tmp_path / ".claude" / "active_command.json"
    legacy_file.parent.mkdir(parents=True, exist_ok=True)
    legacy_file.write_text(
        json.dumps(
            {"command": "duf", "phase": "execution", "terminal_id": "console_other"}
        ),
        encoding="utf-8",
    )

    manager = TaskIdentityManager(project_root=tmp_path, terminal_id="console_a")

    assert manager.get_current_task() is None

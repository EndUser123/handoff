#!/usr/bin/env python3
"""pytest configuration for core handoff tests."""

import sys
from pathlib import Path

import pytest

package_root = Path(__file__).resolve().parents[2]
if str(package_root) not in sys.path:
    sys.path.insert(0, str(package_root))

# Register meta path finder for core.hooks.* imports BEFORE test imports
import core.hooks.__lib  # noqa: F401  # Registers finder for import redirection


@pytest.fixture(autouse=True)
def handoff_test_root(tmp_path, monkeypatch):
    """Force core hook tests to write only inside a temp project root."""
    (tmp_path / ".claude" / "state" / "handoff").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HANDOFF_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("HANDOFF_TEST_ROOT", str(tmp_path))
    yield

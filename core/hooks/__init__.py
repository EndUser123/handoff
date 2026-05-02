"""Core hooks namespace - meta path finder for import redirection."""

from __future__ import annotations

import sys
from importlib.abc import MetaPathFinder, Loader
from importlib.util import spec_from_file_location
from pathlib import Path

# Resolve the actual directories (from core/hooks/__init__.py at package root)
# We need to go up to package root, then into scripts/hooks/
_LIB_DIR = Path(__file__).resolve().parents[2] / "scripts" / "hooks" / "__lib"
_HOOKS_DIR = Path(__file__).resolve().parents[2] / "scripts" / "hooks"


class CoreHooksFinder(MetaPathFinder):
    """Meta path finder that redirects core.hooks.* imports."""

    def find_spec(self, fullname: str, path, target):
        # Handle core.hooks.__lib.* modules
        if fullname.startswith("core.hooks.__lib."):
            module_name = fullname.rsplit(".", 1)[-1]
            # Redirect old handoff-named __lib modules to snapshot-named files
            _LIB_REDIRECT_MAP = {
                "handoff_v2": "snapshot_v2",
                "handoff_files": "snapshot_files",
                "handoff_store": "snapshot_store",
                "handoff_accumulator": "snapshot_accumulator",
            }
            redirected = _LIB_REDIRECT_MAP.get(module_name, module_name)
            file_path = _LIB_DIR / f"{redirected}.py"
            if file_path.exists():
                return spec_from_file_location(
                    fullname, file_path, loader=CoreHooksLoader()
                )

        # Handle core.hooks.{hook_name} modules (e.g., PreCompact_snapshot_capture)
        elif fullname.startswith("core.hooks.") and not fullname.startswith(
            "core.hooks.__"
        ):
            module_name = fullname.rsplit(".", 1)[-1]
            # Redirect old handoff-named hooks to snapshot-named files
            _REDIRECT_MAP = {
                "PreCompact_handoff_capture": "PreCompact_snapshot_capture",
                "SessionStart_handoff_restore": "SessionStart_snapshot_restore",
                "SessionEnd_handoff": "SessionEnd_tldr",
            }
            redirected = _REDIRECT_MAP.get(module_name, module_name)
            file_path = _HOOKS_DIR / f"{redirected}.py"
            if file_path.exists():
                return spec_from_file_location(
                    fullname, file_path, loader=CoreHooksLoader()
                )

        return None


class CoreHooksLoader(Loader):
    """Loader for core.hooks modules."""

    def create_module(self, spec):
        return None  # Use default module creation

    def exec_module(self, module):
        # Get the file path from the spec and execute it
        with open(module.__spec__.origin, "rb") as f:
            code = compile(f.read(), module.__spec__.origin, "exec")
        exec(code, module.__dict__)


# Register the meta path finder
sys.meta_path.insert(0, CoreHooksFinder())

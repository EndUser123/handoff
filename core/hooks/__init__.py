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
            file_path = _LIB_DIR / f"{module_name}.py"
            if file_path.exists():
                return spec_from_file_location(
                    fullname, file_path, loader=CoreHooksLoader()
                )

        # Handle core.hooks.{hook_name} modules (e.g., PreCompact_handoff_capture)
        elif fullname.startswith("core.hooks.") and not fullname.startswith(
            "core.hooks.__"
        ):
            module_name = fullname.rsplit(".", 1)[-1]
            file_path = _HOOKS_DIR / f"{module_name}.py"
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

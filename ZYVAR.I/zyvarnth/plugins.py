from __future__ import annotations

import importlib.util
from pathlib import Path

from .config import Settings
from .tools.registry import ToolRegistry, ToolSpec


class PluginManager:
    """Loads only explicitly enabled local plugins; plugin code has user-level privileges."""

    def __init__(self, settings: Settings, registry: ToolRegistry, directory: Path | None = None) -> None:
        self.settings = settings
        self.registry = registry
        self.directory = directory or Path(__file__).resolve().parent.parent / "plugins"

    def discover(self) -> list[str]:
        self.directory.mkdir(parents=True, exist_ok=True)
        return sorted(path.stem for path in self.directory.glob("*.py") if not path.name.startswith("_"))

    def load_enabled(self) -> list[tuple[str, str]]:
        outcomes = []
        allowed = set(self.settings.get("enabled_plugins", []))
        for name in self.discover():
            if name not in allowed:
                continue
            path = self.directory / f"{name}.py"
            try:
                spec = importlib.util.spec_from_file_location(f"zyvarnth_plugin_{name}", path)
                if spec is None or spec.loader is None:
                    raise RuntimeError("Could not load plugin module.")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                declarations = module.register()
                if not isinstance(declarations, list) or any(not isinstance(item, ToolSpec) for item in declarations):
                    raise ValueError("Plugin register() must return a list of ToolSpec declarations.")
                for declaration in declarations:
                    self.registry.register(declaration)
                outcomes.append((name, "loaded"))
            except Exception as exc:
                outcomes.append((name, f"failed: {str(exc).splitlines()[0][:180]}"))
        return outcomes


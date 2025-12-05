"""Field type registry for managing field generators."""

from __future__ import annotations

import importlib.util
import sys
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from logsynth.fields.types import FieldGenerator

# Registry mapping field type names to generator factory functions
_registry: dict[str, Callable[[dict[str, Any]], FieldGenerator]] = {}

# Track whether plugins have been loaded
_plugins_loaded = False


def register(type_name: str) -> Callable[[Callable], Callable]:
    """Decorator to register a field generator factory."""

    def decorator(factory: Callable[[dict[str, Any]], FieldGenerator]) -> Callable:
        _registry[type_name] = factory
        return factory

    return decorator


def get_generator(type_name: str, config: dict[str, Any]) -> FieldGenerator:
    """Get a field generator instance for the given type and config."""
    if type_name not in _registry:
        available = ", ".join(sorted(_registry.keys()))
        raise ValueError(f"Unknown field type '{type_name}'. Available: {available}")
    return _registry[type_name](config)


def list_types() -> list[str]:
    """List all registered field types."""
    return sorted(_registry.keys())


def load_plugin_file(path: Path) -> None:
    """Load a single plugin Python file.

    The plugin file should use the @register decorator to register
    custom field types.
    """
    module_name = f"logsynth_plugin_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)


def scan_plugin_dir(plugins_dir: Path) -> list[str]:
    """Scan directory for plugin files and load them.

    Returns list of loaded plugin names.
    """
    loaded: list[str] = []
    if not plugins_dir.exists():
        return loaded

    for path in sorted(plugins_dir.glob("*.py")):
        # Skip private modules
        if path.name.startswith("_"):
            continue
        try:
            load_plugin_file(path)
            loaded.append(path.stem)
        except Exception as e:
            warnings.warn(f"Failed to load plugin {path.name}: {e}")

    return loaded


def load_plugins() -> list[str]:
    """Load all plugins from the configured plugins directory.

    Returns list of loaded plugin names.
    """
    from logsynth.config import PLUGINS_DIR

    return scan_plugin_dir(PLUGINS_DIR)


def ensure_plugins_loaded() -> None:
    """Ensure plugins are loaded (idempotent).

    Call this to lazily load plugins on first use.
    """
    global _plugins_loaded
    if not _plugins_loaded:
        load_plugins()
        _plugins_loaded = True

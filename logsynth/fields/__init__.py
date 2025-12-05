"""Field type generators."""

from logsynth.fields.registry import (
    ensure_plugins_loaded,
    get_generator,
    list_types,
    load_plugins,
    register,
)
from logsynth.fields.types import FieldGenerator

# Load plugins when the module is imported
ensure_plugins_loaded()

__all__ = [
    "FieldGenerator",
    "ensure_plugins_loaded",
    "get_generator",
    "list_types",
    "load_plugins",
    "register",
]

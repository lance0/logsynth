"""Field type registry for managing field generators."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from logsynth.fields.types import FieldGenerator

# Registry mapping field type names to generator factory functions
_registry: dict[str, Callable[[dict[str, Any]], FieldGenerator]] = {}


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

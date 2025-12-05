"""Core log generator that orchestrates templates, fields, and formatting."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Callable

from logsynth.config import PRESETS_DIR
from logsynth.fields import FieldGenerator, get_generator
from logsynth.utils.formatter import Formatter, get_formatter
from logsynth.utils.schema import Template, load_template


class LogGenerator:
    """Generates log lines from a template."""

    def __init__(
        self,
        template: Template,
        formatter: Formatter | None = None,
        seed: int | None = None,
    ) -> None:
        self.template = template
        self.formatter = formatter or get_formatter(template.format)
        self.seed = seed

        # Initialize random seed if provided
        if seed is not None:
            random.seed(seed)

        # Create field generators
        self.field_generators: dict[str, FieldGenerator] = {}
        for field_name, field_config in template.fields.items():
            self.field_generators[field_name] = get_generator(
                field_config.type,
                field_config.config,
            )

    def generate(self) -> str:
        """Generate a single log line."""
        # Generate values for all fields
        values: dict[str, Any] = {}
        for field_name, generator in self.field_generators.items():
            values[field_name] = generator.generate()

        # Format the log line
        return self.formatter.format(self.template.pattern, values)

    def generate_values(self) -> dict[str, Any]:
        """Generate field values without formatting (useful for corruption)."""
        return {name: gen.generate() for name, gen in self.field_generators.items()}

    def reset(self) -> None:
        """Reset all field generators to initial state."""
        if self.seed is not None:
            random.seed(self.seed)
        for generator in self.field_generators.values():
            generator.reset()

    def preview(self) -> str:
        """Generate a preview line without advancing state."""
        # Save current state
        saved_state = random.getstate()

        # Generate line
        line = self.generate()

        # Restore state (this won't reset timestamp progression, but that's acceptable for preview)
        random.setstate(saved_state)

        return line


def create_generator(
    source: str | Path | Template,
    format_override: str | None = None,
    seed: int | None = None,
) -> LogGenerator:
    """Create a LogGenerator from various sources.

    Args:
        source: Template object, file path, or preset name
        format_override: Override the template's format setting
        seed: Random seed for reproducibility
    """
    # Handle Template objects directly
    if isinstance(source, Template):
        template = source
    # Handle preset names
    elif isinstance(source, str) and not Path(source).exists():
        preset_path = PRESETS_DIR / f"{source}.yaml"
        if preset_path.exists():
            template = load_template(preset_path)
        else:
            # Try as YAML string
            if ":" in source and "\n" in source:
                template = load_template(source)
            else:
                raise FileNotFoundError(
                    f"Template not found: '{source}'. "
                    f"Not a preset name or existing file path."
                )
    else:
        # Load from file path
        template = load_template(source)

    # Create formatter
    format_name = format_override or template.format
    formatter = get_formatter(format_name)

    return LogGenerator(template, formatter, seed)


def list_presets() -> list[str]:
    """List available preset template names."""
    if not PRESETS_DIR.exists():
        return []
    return sorted(p.stem for p in PRESETS_DIR.glob("*.yaml"))


def get_preset_path(name: str) -> Path | None:
    """Get the path to a preset template by name."""
    preset_path = PRESETS_DIR / f"{name}.yaml"
    if preset_path.exists():
        return preset_path
    return None


GeneratorFactory = Callable[[], str]


def create_generator_function(
    source: str | Path | Template,
    format_override: str | None = None,
    seed: int | None = None,
) -> GeneratorFactory:
    """Create a simple callable that generates log lines.

    This is useful for rate_control which expects a simple generate function.
    """
    gen = create_generator(source, format_override, seed)
    return gen.generate

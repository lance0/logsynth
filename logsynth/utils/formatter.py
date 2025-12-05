"""Output formatters for different log formats."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any

from jinja2 import BaseLoader, Environment


class Formatter(ABC):
    """Abstract base class for output formatters."""

    @abstractmethod
    def format(self, pattern: str, values: dict[str, Any]) -> str:
        """Format a log line with the given field values."""
        pass


def _is_jinja_pattern(pattern: str) -> bool:
    """Detect if pattern uses Jinja2 syntax."""
    return "{{" in pattern or "{%" in pattern


class SimpleSubstitutionFormatter(Formatter):
    """Format logs using simple $field pattern substitution."""

    def format(self, pattern: str, values: dict[str, Any]) -> str:
        """Substitute $field and ${field} placeholders in pattern."""
        result = pattern

        # Replace ${field} style first (more specific)
        for field, value in values.items():
            result = result.replace(f"${{{field}}}", str(value))

        # Replace $field style
        for field, value in values.items():
            result = re.sub(rf"\${field}(?!\w)", str(value), result)

        return result.strip()


class JinjaFormatter(Formatter):
    """Format logs using Jinja2 templating."""

    def __init__(self) -> None:
        self.env = Environment(
            loader=BaseLoader(),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._cache: dict[str, Any] = {}

    def format(self, pattern: str, values: dict[str, Any]) -> str:
        """Render pattern as Jinja2 template with values as context."""
        if pattern not in self._cache:
            self._cache[pattern] = self.env.from_string(pattern)
        template = self._cache[pattern]
        return template.render(**values).strip()


class PlainFormatter(Formatter):
    """Format logs with auto-detection of Jinja2 vs simple substitution."""

    def __init__(self) -> None:
        self._simple = SimpleSubstitutionFormatter()
        self._jinja = JinjaFormatter()

    def format(self, pattern: str, values: dict[str, Any]) -> str:
        """Auto-detect pattern type and format accordingly."""
        if _is_jinja_pattern(pattern):
            return self._jinja.format(pattern, values)
        return self._simple.format(pattern, values)


class JsonFormatter(Formatter):
    """Format logs as JSON objects."""

    def __init__(self, include_pattern: bool = False) -> None:
        self.include_pattern = include_pattern

    def format(self, pattern: str, values: dict[str, Any]) -> str:
        """Format field values as JSON."""
        data = dict(values)
        if self.include_pattern:
            # Also include the rendered pattern as 'message'
            plain = PlainFormatter().format(pattern, values)
            data["message"] = plain
        return json.dumps(data, default=str)


class LogfmtFormatter(Formatter):
    """Format logs in logfmt style (key=value pairs)."""

    def format(self, pattern: str, values: dict[str, Any]) -> str:
        """Format field values as logfmt."""
        parts = []
        for key, value in values.items():
            str_value = str(value)
            # Quote values with spaces or special characters
            if " " in str_value or '"' in str_value or "=" in str_value:
                str_value = '"' + str_value.replace('"', '\\"') + '"'
            parts.append(f"{key}={str_value}")
        return " ".join(parts)


def get_formatter(format_name: str) -> Formatter:
    """Get a formatter instance by name."""
    formatters = {
        "plain": PlainFormatter,
        "jinja": JinjaFormatter,
        "json": JsonFormatter,
        "logfmt": LogfmtFormatter,
    }

    if format_name not in formatters:
        available = ", ".join(sorted(formatters.keys()))
        raise ValueError(f"Unknown format '{format_name}'. Available: {available}")

    return formatters[format_name]()

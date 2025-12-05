"""YAML template schema validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from logsynth.fields import list_types


@dataclass
class FieldConfig:
    """Configuration for a single field."""

    name: str
    type: str
    config: dict[str, Any]


@dataclass
class Template:
    """Parsed and validated template."""

    name: str
    format: str
    pattern: str
    fields: dict[str, FieldConfig]
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def field_names(self) -> list[str]:
        """Get list of field names."""
        return list(self.fields.keys())


class ValidationError(Exception):
    """Raised when template validation fails."""

    def __init__(self, message: str, errors: list[str] | None = None):
        self.message = message
        self.errors = errors or []
        super().__init__(message)


VALID_FORMATS = {"plain", "json", "logfmt"}


def validate_template(data: dict[str, Any]) -> list[str]:
    """Validate template data and return list of errors (empty if valid)."""
    errors: list[str] = []

    # Required fields
    if "name" not in data:
        errors.append("Missing required field: 'name'")

    if "pattern" not in data:
        errors.append("Missing required field: 'pattern'")

    if "fields" not in data:
        errors.append("Missing required field: 'fields'")
    elif not isinstance(data["fields"], dict):
        errors.append("'fields' must be a dictionary")
    elif not data["fields"]:
        errors.append("'fields' cannot be empty")

    # Format validation
    fmt = data.get("format", "plain")
    if fmt not in VALID_FORMATS:
        errors.append(f"Invalid format '{fmt}'. Must be one of: {', '.join(VALID_FORMATS)}")

    # Validate each field
    if isinstance(data.get("fields"), dict):
        valid_types = set(list_types())
        for field_name, field_config in data["fields"].items():
            if not isinstance(field_config, dict):
                errors.append(f"Field '{field_name}': configuration must be a dictionary")
                continue

            if "type" not in field_config:
                errors.append(f"Field '{field_name}': missing required 'type'")
                continue

            field_type = field_config["type"]
            if field_type not in valid_types:
                errors.append(
                    f"Field '{field_name}': unknown type '{field_type}'. "
                    f"Valid types: {', '.join(sorted(valid_types))}"
                )

    # Validate pattern references fields
    pattern = data.get("pattern", "")
    if isinstance(data.get("fields"), dict) and pattern:
        # Check for $field or ${field} references
        import re

        field_refs = set(re.findall(r"\$\{?(\w+)\}?", pattern))
        defined_fields = set(data["fields"].keys())

        undefined = field_refs - defined_fields
        if undefined:
            errors.append(
                f"Pattern references undefined fields: {', '.join(sorted(undefined))}"
            )

    return errors


def load_template(source: str | Path) -> Template:
    """Load and validate a template from file path or YAML string."""
    if isinstance(source, Path) or (isinstance(source, str) and Path(source).exists()):
        path = Path(source)
        with open(path) as f:
            data = yaml.safe_load(f)
    else:
        # Treat as YAML string
        data = yaml.safe_load(source)

    if not isinstance(data, dict):
        raise ValidationError("Template must be a YAML dictionary")

    errors = validate_template(data)
    if errors:
        raise ValidationError(
            f"Template validation failed with {len(errors)} error(s)",
            errors=errors,
        )

    # Build Template object
    fields = {}
    for field_name, field_config in data["fields"].items():
        fields[field_name] = FieldConfig(
            name=field_name,
            type=field_config["type"],
            config=field_config,
        )

    return Template(
        name=data["name"],
        format=data.get("format", "plain"),
        pattern=data["pattern"],
        fields=fields,
        raw=data,
    )


def template_to_yaml(template: Template) -> str:
    """Convert a Template back to YAML string."""
    data = {
        "name": template.name,
        "format": template.format,
        "pattern": template.pattern,
        "fields": {},
    }

    for field_name, field_config in template.fields.items():
        data["fields"][field_name] = field_config.config

    return yaml.dump(data, default_flow_style=False, sort_keys=False)

"""Main schema inference engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from logsynth.infer.detector import (
    DetectionResult,
    aggregate_detections,
    detect_field_type,
)
from logsynth.infer.parser import (
    LogFormat,
    ParsedLine,
    build_pattern_from_tokens,
    infer_format_from_lines,
    parse_line,
    tokenize_plain,
)


class SchemaInferrer:
    """Infer log schema from sample log lines."""

    def __init__(
        self,
        max_lines: int = 1000,
        max_unique_values: int = 20,
    ) -> None:
        self.max_lines = max_lines
        self.max_unique_values = max_unique_values

    def infer_from_file(
        self,
        path: Path | str,
        name: str | None = None,
        format_hint: str | None = None,
    ) -> dict[str, Any]:
        """Infer schema from a log file."""
        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        # Read lines
        lines: list[str] = []
        with open(path, encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f):
                if i >= self.max_lines:
                    break
                line = line.strip()
                if line:  # Skip empty lines
                    lines.append(line)

        if not lines:
            raise ValueError(f"No valid log lines found in: {path}")

        # Use filename as default name
        template_name = name or path.stem

        return self.infer(lines, template_name, format_hint)

    def infer(
        self,
        lines: list[str],
        name: str = "inferred-template",
        format_hint: str | None = None,
    ) -> dict[str, Any]:
        """Infer schema from a list of log lines."""
        if not lines:
            raise ValueError("No log lines provided")

        # Determine format
        if format_hint:
            log_format = LogFormat(format_hint)
        else:
            log_format = infer_format_from_lines(lines)

        # Parse all lines
        parsed_lines = [parse_line(line, log_format) for line in lines]

        # Route to appropriate handler
        if log_format == LogFormat.JSON:
            return self._infer_json(parsed_lines, name)
        elif log_format == LogFormat.LOGFMT:
            return self._infer_logfmt(parsed_lines, name)
        else:
            return self._infer_plain(parsed_lines, name)

    def _infer_json(
        self,
        parsed_lines: list[ParsedLine],
        name: str,
    ) -> dict[str, Any]:
        """Infer schema from JSON log lines."""
        # Collect all field names and their values
        field_values: dict[str, list[str]] = {}

        for parsed in parsed_lines:
            for field_name, value in parsed.fields.items():
                if field_name not in field_values:
                    field_values[field_name] = []
                field_values[field_name].append(value)

        # Detect types for each field
        fields = self._build_fields(field_values)

        return {
            "name": name,
            "format": "json",
            "pattern": self._build_json_pattern(list(fields.keys())),
            "fields": fields,
        }

    def _infer_logfmt(
        self,
        parsed_lines: list[ParsedLine],
        name: str,
    ) -> dict[str, Any]:
        """Infer schema from logfmt log lines."""
        # Collect all field names and their values
        field_values: dict[str, list[str]] = {}

        for parsed in parsed_lines:
            for field_name, value in parsed.fields.items():
                if field_name not in field_values:
                    field_values[field_name] = []
                field_values[field_name].append(value)

        # Detect types for each field
        fields = self._build_fields(field_values)

        return {
            "name": name,
            "format": "logfmt",
            "pattern": self._build_logfmt_pattern(list(fields.keys())),
            "fields": fields,
        }

    def _infer_plain(
        self,
        parsed_lines: list[ParsedLine],
        name: str,
    ) -> dict[str, Any]:
        """Infer schema from plain text log lines."""
        # For plain text, we need consistent token counts
        # Find the most common token count
        token_counts: dict[int, int] = {}
        for parsed in parsed_lines:
            if parsed.tokens:
                count = len(parsed.tokens)
                token_counts[count] = token_counts.get(count, 0) + 1

        if not token_counts:
            raise ValueError("Could not parse any log lines")

        # Use most common token count
        target_count = max(token_counts, key=lambda c: token_counts[c])

        # Filter to lines with matching token count
        valid_lines = [p for p in parsed_lines if p.tokens and len(p.tokens) == target_count]

        if not valid_lines:
            raise ValueError("No consistent log line structure found")

        # Collect values by position
        field_values: dict[str, list[str]] = {}
        for i in range(target_count):
            field_values[f"field_{i + 1}"] = []

        for parsed in valid_lines:
            if parsed.tokens:
                for i, token in enumerate(parsed.tokens):
                    field_values[f"field_{i + 1}"].append(token)

        # Detect types and assign semantic names
        fields, field_name_map = self._build_fields_with_names(field_values)

        # Build pattern from first valid line
        first_line = valid_lines[0]
        tokens = tokenize_plain(first_line.raw)
        pattern = build_pattern_from_tokens(
            tokens,
            [field_name_map.get(f"field_{i + 1}", f"field_{i + 1}") for i in range(len(tokens))],
        )

        return {
            "name": name,
            "format": "plain",
            "pattern": pattern,
            "fields": fields,
        }

    def _build_fields(
        self,
        field_values: dict[str, list[str]],
    ) -> dict[str, dict[str, Any]]:
        """Build field configs from collected values."""
        fields: dict[str, dict[str, Any]] = {}

        for field_name, values in field_values.items():
            # Detect type for each value
            detections = [detect_field_type(v) for v in values]
            config = aggregate_detections(detections)

            # Clean up internal notes
            config.pop("_note", None)

            fields[field_name] = config

        return fields

    def _build_fields_with_names(
        self,
        field_values: dict[str, list[str]],
    ) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
        """Build field configs with semantic naming."""
        fields: dict[str, dict[str, Any]] = {}
        name_map: dict[str, str] = {}  # old_name -> new_name
        used_names: set[str] = set()

        for field_name, values in field_values.items():
            # Detect type for each value
            detections = [detect_field_type(v) for v in values]
            config = aggregate_detections(detections)

            # Get semantic name from detections
            semantic_name = self._get_semantic_name(detections, config)

            # Ensure unique name
            if semantic_name and semantic_name not in used_names:
                new_name = semantic_name
            else:
                new_name = field_name

            used_names.add(new_name)
            name_map[field_name] = new_name

            # Clean up internal notes
            config.pop("_note", None)

            fields[new_name] = config

        return fields, name_map

    def _get_semantic_name(
        self,
        detections: list[DetectionResult],
        config: dict[str, Any],
    ) -> str | None:
        """Get semantic name from detections."""
        # Check detections for semantic names
        for d in detections:
            if d.semantic_name:
                return d.semantic_name

        # Infer from config
        field_type = config.get("type")
        if field_type == "ip":
            return "ip"
        if field_type == "uuid":
            return "uuid"
        if field_type == "timestamp":
            return "timestamp"

        # Check choice values for patterns
        if field_type == "choice":
            values = config.get("values", [])
            if values:
                # HTTP methods
                http_methods = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
                if set(values) <= http_methods:
                    return "method"

                # Log levels
                log_levels = {
                    "DEBUG", "INFO", "WARN", "WARNING", "ERROR",
                    "FATAL", "CRITICAL", "TRACE", "NOTICE",
                }
                if set(v.upper() for v in values) <= log_levels:
                    return "level"

                # HTTP status codes
                if all(str(v).isdigit() and 100 <= int(v) <= 599 for v in values):
                    return "status"

        return None

    def _build_json_pattern(self, field_names: list[str]) -> str:
        """Build a JSON pattern string."""
        # JSON format uses built-in serialization
        return ""

    def _build_logfmt_pattern(self, field_names: list[str]) -> str:
        """Build a logfmt pattern string."""
        # Logfmt format uses built-in serialization
        return ""


def infer_to_yaml(
    source: Path | str | list[str],
    name: str | None = None,
    format_hint: str | None = None,
    max_lines: int = 1000,
) -> str:
    """Infer schema and return as YAML string."""
    inferrer = SchemaInferrer(max_lines=max_lines)

    if isinstance(source, list):
        template = inferrer.infer(source, name or "inferred-template", format_hint)
    else:
        template = inferrer.infer_from_file(source, name, format_hint)

    # Custom YAML formatting for readability
    return yaml.dump(
        template,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
        width=120,
    )

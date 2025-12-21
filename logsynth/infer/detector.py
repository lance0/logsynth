"""Field type detection using regex patterns and heuristics."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class DetectionResult:
    """Result of field type detection."""

    field_type: str
    config: dict[str, Any]
    confidence: float  # 0.0 to 1.0
    semantic_name: str | None = None


# Timestamp format patterns with their strftime equivalents
TIMESTAMP_PATTERNS: list[tuple[str, str, str]] = [
    # ISO 8601 variants
    (r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z?$", "%Y-%m-%dT%H:%M:%S.%f", "iso8601_micro"),
    (r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z?$", "%Y-%m-%dT%H:%M:%S", "iso8601"),
    (r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+$", "%Y-%m-%d %H:%M:%S.%f", "datetime_micro"),
    (r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", "%Y-%m-%d %H:%M:%S", "datetime"),
    # Common Log Format (CLF) - nginx/apache
    (r"^\d{2}/\w{3}/\d{4}:\d{2}:\d{2}:\d{2} [+-]\d{4}$", "%d/%b/%Y:%H:%M:%S %z", "clf"),
    # Syslog style
    (r"^\w{3}\s+\d{1,2} \d{2}:\d{2}:\d{2}$", "%b %d %H:%M:%S", "syslog"),
    # Unix timestamp
    (r"^\d{10}$", "epoch", "epoch"),
    (r"^\d{13}$", "epoch_ms", "epoch_ms"),
]

# Patterns for specific field types (pattern, type, semantic_name)
TYPE_PATTERNS: list[tuple[str, str, str | None]] = [
    # UUID
    (r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", "uuid", "uuid"),  # noqa: E501
    # IPv4
    (r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", "ip", "ip"),
    # IPv6 (simplified)
    (r"^([0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}$", "ip", "ip"),
    # HTTP methods
    (r"^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS|CONNECT|TRACE)$", "choice", "method"),
    # Log levels
    (r"^(DEBUG|INFO|WARN|WARNING|ERROR|FATAL|CRITICAL|TRACE|NOTICE)$", "choice", "level"),
    # HTTP status codes
    (r"^[1-5]\d{2}$", "choice", "status"),
    # URL paths
    (r"^/[\w/\-_.?&=%]*$", "choice", "path"),
    # Email (simplified)
    (r"^[\w.+-]+@[\w.-]+\.\w+$", "choice", "email"),
    # Hex strings (like commit hashes)
    (r"^[0-9a-fA-F]{7,64}$", "choice", "hash"),
]

# Known literal values that appear frequently
KNOWN_LITERALS = {"-", "null", "NULL", "nil", "none", "None", "true", "false", "True", "False"}


def detect_timestamp(value: str) -> DetectionResult | None:
    """Detect if value is a timestamp and return format info."""
    for pattern, fmt, name in TIMESTAMP_PATTERNS:
        if re.match(pattern, value):
            config: dict[str, Any] = {"type": "timestamp"}
            if fmt.startswith("epoch"):
                config["format"] = "%Y-%m-%d %H:%M:%S"
                config["_note"] = f"Detected as {name}, using standard output format"
            else:
                config["format"] = fmt
            return DetectionResult(
                field_type="timestamp",
                config=config,
                confidence=0.95,
                semantic_name="timestamp",
            )
    return None


def detect_by_pattern(value: str) -> DetectionResult | None:
    """Detect field type using regex patterns."""
    for pattern, field_type, semantic_name in TYPE_PATTERNS:
        if re.match(pattern, value, re.IGNORECASE):
            config: dict[str, Any] = {"type": field_type}
            # Special handling for IP validation
            if field_type == "ip" and "." in value:
                parts = value.split(".")
                if not all(0 <= int(p) <= 255 for p in parts if p.isdigit()):
                    continue
            return DetectionResult(
                field_type=field_type,
                config=config,
                confidence=0.9,
                semantic_name=semantic_name,
            )
    return None


def detect_number(value: str) -> DetectionResult | None:
    """Detect if value is a number (int or float)."""
    # Integer
    if re.match(r"^-?\d+$", value):
        try:
            int_val = int(value)
            return DetectionResult(
                field_type="int",
                config={"type": "int", "min": int_val, "max": int_val},
                confidence=0.85,
                semantic_name=None,
            )
        except ValueError:
            pass

    # Float
    if re.match(r"^-?\d+\.\d+$", value):
        try:
            float_val = float(value)
            return DetectionResult(
                field_type="float",
                config={"type": "float", "min": float_val, "max": float_val, "precision": 2},
                confidence=0.85,
                semantic_name=None,
            )
        except ValueError:
            pass

    return None


def detect_literal(value: str) -> DetectionResult | None:
    """Detect if value is a known literal."""
    if value in KNOWN_LITERALS:
        return DetectionResult(
            field_type="literal",
            config={"type": "literal", "value": value},
            confidence=0.95,
            semantic_name=None,
        )
    return None


def detect_field_type(value: str) -> DetectionResult:
    """Detect the most likely field type for a single value."""
    value = value.strip()

    # Empty or whitespace
    if not value:
        return DetectionResult(
            field_type="literal",
            config={"type": "literal", "value": ""},
            confidence=1.0,
            semantic_name=None,
        )

    # Try detection in priority order
    result = detect_literal(value)
    if result:
        return result

    result = detect_timestamp(value)
    if result:
        return result

    result = detect_by_pattern(value)
    if result:
        return result

    result = detect_number(value)
    if result:
        return result

    # Default to choice (will be aggregated later)
    return DetectionResult(
        field_type="choice",
        config={"type": "choice", "values": [value]},
        confidence=0.5,
        semantic_name=None,
    )


def aggregate_detections(detections: list[DetectionResult]) -> dict[str, Any]:
    """Aggregate multiple detection results into a single field config."""
    if not detections:
        return {"type": "literal", "value": ""}

    # Count field types
    type_counts: dict[str, int] = {}
    for d in detections:
        type_counts[d.field_type] = type_counts.get(d.field_type, 0) + 1

    # Find majority type
    majority_type = max(type_counts, key=lambda t: type_counts[t])

    # Build config based on majority type
    if majority_type == "timestamp":
        # Use format from first timestamp detection
        for d in detections:
            if d.field_type == "timestamp":
                config = d.config.copy()
                config.pop("_note", None)
                return config

    if majority_type == "ip":
        return {"type": "ip"}

    if majority_type == "uuid":
        return {"type": "uuid"}

    if majority_type == "int":
        int_detections = [d for d in detections if d.field_type == "int"]
        min_val = min(d.config.get("min", 0) for d in int_detections)
        max_val = max(d.config.get("max", 100) for d in int_detections)
        return {"type": "int", "min": min_val, "max": max_val}

    if majority_type == "float":
        float_detections = [d for d in detections if d.field_type == "float"]
        min_val = min(d.config.get("min", 0.0) for d in float_detections)
        max_val = max(d.config.get("max", 1.0) for d in float_detections)
        return {"type": "float", "min": min_val, "max": max_val, "precision": 2}

    if majority_type == "literal":
        # Check if all literals are the same
        literal_values = [d.config.get("value") for d in detections if d.field_type == "literal"]
        unique_literals = set(literal_values)
        if len(unique_literals) == 1:
            return {"type": "literal", "value": literal_values[0]}
        # Multiple literals -> choice
        majority_type = "choice"

    # Default to choice - collect all unique values
    all_values: list[str] = []
    for d in detections:
        if d.field_type == "choice":
            all_values.extend(d.config.get("values", []))
        elif d.field_type == "literal":
            all_values.append(str(d.config.get("value", "")))

    # Count occurrences for weights
    value_counts: dict[str, int] = {}
    for v in all_values:
        value_counts[v] = value_counts.get(v, 0) + 1

    unique_values = list(value_counts.keys())
    total = sum(value_counts.values())

    # If too many unique values (> 50), it's probably not a choice field
    if len(unique_values) > 50:
        return {"type": "choice", "values": unique_values[:20], "_note": "truncated"}

    # Calculate weights
    weights = [round(value_counts[v] / total, 3) for v in unique_values]

    config: dict[str, Any] = {"type": "choice", "values": unique_values}
    if len(unique_values) > 1:
        config["weights"] = weights

    return config

"""Log line parsing for different formats (JSON, logfmt, plain text)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum


class LogFormat(Enum):
    """Detected log format."""

    JSON = "json"
    LOGFMT = "logfmt"
    PLAIN = "plain"


@dataclass
class ParsedLine:
    """A parsed log line with extracted fields."""

    format: LogFormat
    fields: dict[str, str]  # field_name -> value
    raw: str
    tokens: list[str] | None = None  # For plain text, the raw tokens


@dataclass
class Token:
    """A token extracted from a plain text log line."""

    value: str
    start: int
    end: int
    delimiter_before: str
    delimiter_after: str


def detect_format(line: str) -> LogFormat:
    """Detect the format of a log line."""
    line = line.strip()

    # JSON detection
    if line.startswith("{") and line.endswith("}"):
        try:
            json.loads(line)
            return LogFormat.JSON
        except json.JSONDecodeError:
            pass

    # Logfmt detection - key=value or key="value" patterns
    logfmt_pattern = r'^[\w\-_.]+=(?:"[^"]*"|[^\s]+)(?:\s+[\w\-_.]+=(?:"[^"]*"|[^\s]+))*\s*$'
    if re.match(logfmt_pattern, line):
        return LogFormat.LOGFMT

    # Also detect logfmt with leading timestamp/level
    # e.g., "2024-01-01 10:00:00 INFO key=value key2=value2"
    partial_logfmt = r'[\w\-_.]+=(?:"[^"]*"|[^\s]+)'
    matches = re.findall(partial_logfmt, line)
    if len(matches) >= 2:  # At least 2 key=value pairs
        return LogFormat.LOGFMT

    return LogFormat.PLAIN


def parse_json(line: str) -> dict[str, str]:
    """Parse a JSON log line."""
    try:
        data = json.loads(line)
        if isinstance(data, dict):
            # Flatten nested objects and convert all values to strings
            result: dict[str, str] = {}
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    result[key] = json.dumps(value)
                else:
                    result[key] = str(value) if value is not None else ""
            return result
    except json.JSONDecodeError:
        pass
    return {}


def parse_logfmt(line: str) -> dict[str, str]:
    """Parse a logfmt log line."""
    result: dict[str, str] = {}

    # Pattern for key=value or key="quoted value"
    pattern = r'([\w\-_.]+)=(?:"([^"]*)"|([^\s]*))'

    for match in re.finditer(pattern, line):
        key = match.group(1)
        value = match.group(2) if match.group(2) is not None else match.group(3)
        result[key] = value

    return result


def tokenize_plain(line: str) -> list[Token]:
    """Tokenize a plain text log line preserving delimiters."""
    tokens: list[Token] = []

    # Common delimiters in logs
    # We want to split on spaces but preserve bracketed content, quoted strings
    # Pattern groups: quoted strings, bracketed content, or space-separated tokens
    pattern = r'"([^"]*)"|\[([^\]]*)\]|(\S+)'

    last_end = 0
    for match in re.finditer(pattern, line):
        start = match.start()
        end = match.end()

        # Get delimiter before this token
        delimiter_before = line[last_end:start] if last_end < start else ""

        # Determine the actual value
        if match.group(1) is not None:  # Quoted string
            value = match.group(1)
            # Include quotes in delimiter representation
            delimiter_before = delimiter_before + '"'
            delimiter_after = '"'
        elif match.group(2) is not None:  # Bracketed content
            value = match.group(2)
            delimiter_before = delimiter_before + "["
            delimiter_after = "]"
        else:  # Regular token
            value = match.group(3)
            delimiter_after = ""

        tokens.append(Token(
            value=value,
            start=start,
            end=end,
            delimiter_before=delimiter_before,
            delimiter_after=delimiter_after,
        ))
        last_end = end

    return tokens


def parse_plain(line: str) -> tuple[dict[str, str], list[str]]:
    """Parse a plain text log line into positional fields."""
    tokens = tokenize_plain(line)
    fields: dict[str, str] = {}
    raw_tokens: list[str] = []

    for i, token in enumerate(tokens):
        field_name = f"field_{i + 1}"
        fields[field_name] = token.value
        raw_tokens.append(token.value)

    return fields, raw_tokens


def parse_line(line: str, format_hint: LogFormat | None = None) -> ParsedLine:
    """Parse a log line into structured fields."""
    line = line.strip()

    if not line:
        return ParsedLine(format=LogFormat.PLAIN, fields={}, raw=line, tokens=[])

    # Detect or use hinted format
    detected_format = format_hint or detect_format(line)

    if detected_format == LogFormat.JSON:
        fields = parse_json(line)
        return ParsedLine(format=detected_format, fields=fields, raw=line)

    if detected_format == LogFormat.LOGFMT:
        fields = parse_logfmt(line)
        return ParsedLine(format=detected_format, fields=fields, raw=line)

    # Plain text
    fields, tokens = parse_plain(line)
    return ParsedLine(format=detected_format, fields=fields, raw=line, tokens=tokens)


def build_pattern_from_tokens(
    tokens: list[Token],
    field_names: list[str],
) -> str:
    """Build a pattern string from tokens and field names."""
    if not tokens:
        return ""

    parts: list[str] = []
    for i, token in enumerate(tokens):
        field_name = field_names[i] if i < len(field_names) else f"field_{i + 1}"

        # Add delimiter before (skip leading space for first token)
        if i == 0:
            delim = token.delimiter_before.lstrip()
        else:
            delim = token.delimiter_before

        parts.append(delim)
        parts.append(f"${field_name}")
        parts.append(token.delimiter_after)

    return "".join(parts)


def infer_format_from_lines(lines: list[str]) -> LogFormat:
    """Infer the most common format from multiple lines."""
    if not lines:
        return LogFormat.PLAIN

    format_counts: dict[LogFormat, int] = {
        LogFormat.JSON: 0,
        LogFormat.LOGFMT: 0,
        LogFormat.PLAIN: 0,
    }

    for line in lines[:100]:  # Sample first 100 lines
        line = line.strip()
        if not line:
            continue
        fmt = detect_format(line)
        format_counts[fmt] += 1

    # Return most common format
    return max(format_counts, key=lambda f: format_counts[f])

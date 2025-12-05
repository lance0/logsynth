"""Tests for output formatters."""

import json

import pytest

from logsynth.utils.formatter import (
    JsonFormatter,
    LogfmtFormatter,
    PlainFormatter,
    get_formatter,
)


class TestPlainFormatter:
    """Tests for plain text formatter."""

    def test_simple_substitution(self):
        """Should substitute $field placeholders."""
        formatter = PlainFormatter()
        result = formatter.format(
            "$level: $message",
            {"level": "INFO", "message": "test"}
        )
        assert result == "INFO: test"

    def test_braced_substitution(self):
        """Should substitute ${field} placeholders."""
        formatter = PlainFormatter()
        result = formatter.format(
            "${level}: ${message}",
            {"level": "INFO", "message": "test"}
        )
        assert result == "INFO: test"

    def test_mixed_substitution(self):
        """Should handle mixed placeholder styles."""
        formatter = PlainFormatter()
        result = formatter.format(
            "$level - ${message}",
            {"level": "INFO", "message": "test"}
        )
        assert result == "INFO - test"

    def test_strips_whitespace(self):
        """Should strip trailing whitespace."""
        formatter = PlainFormatter()
        result = formatter.format("$x  \n", {"x": "value"})
        assert result == "value"


class TestJsonFormatter:
    """Tests for JSON formatter."""

    def test_basic_json(self):
        """Should format as JSON object."""
        formatter = JsonFormatter()
        result = formatter.format(
            "ignored",
            {"level": "INFO", "message": "test", "code": 200}
        )
        data = json.loads(result)
        assert data["level"] == "INFO"
        assert data["message"] == "test"
        assert data["code"] == 200

    def test_json_with_message(self):
        """Should include rendered message if requested."""
        formatter = JsonFormatter(include_pattern=True)
        result = formatter.format(
            "$level: $message",
            {"level": "INFO", "message": "test"}
        )
        data = json.loads(result)
        assert data["message"] == "INFO: test"


class TestLogfmtFormatter:
    """Tests for logfmt formatter."""

    def test_basic_logfmt(self):
        """Should format as key=value pairs."""
        formatter = LogfmtFormatter()
        result = formatter.format(
            "ignored",
            {"level": "INFO", "code": 200}
        )
        assert "level=INFO" in result
        assert "code=200" in result

    def test_quotes_spaces(self):
        """Should quote values with spaces."""
        formatter = LogfmtFormatter()
        result = formatter.format(
            "ignored",
            {"message": "hello world"}
        )
        assert 'message="hello world"' in result

    def test_escapes_quotes(self):
        """Should escape quotes in values."""
        formatter = LogfmtFormatter()
        result = formatter.format(
            "ignored",
            {"message": 'say "hello"'}
        )
        assert '\\"' in result


class TestGetFormatter:
    """Tests for formatter factory."""

    def test_get_plain(self):
        """Should return PlainFormatter for 'plain'."""
        formatter = get_formatter("plain")
        assert isinstance(formatter, PlainFormatter)

    def test_get_json(self):
        """Should return JsonFormatter for 'json'."""
        formatter = get_formatter("json")
        assert isinstance(formatter, JsonFormatter)

    def test_get_logfmt(self):
        """Should return LogfmtFormatter for 'logfmt'."""
        formatter = get_formatter("logfmt")
        assert isinstance(formatter, LogfmtFormatter)

    def test_unknown_raises(self):
        """Should raise for unknown format."""
        with pytest.raises(ValueError, match="Unknown format"):
            get_formatter("unknown")

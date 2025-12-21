"""Tests for schema inference module."""

from __future__ import annotations

from pathlib import Path

import pytest

from logsynth.infer.detector import (
    DetectionResult,
    aggregate_detections,
    detect_by_pattern,
    detect_field_type,
    detect_number,
    detect_timestamp,
)
from logsynth.infer.inference import SchemaInferrer
from logsynth.infer.parser import (
    LogFormat,
    detect_format,
    parse_json,
    parse_line,
    parse_logfmt,
    tokenize_plain,
)


class TestDetector:
    """Tests for field type detection."""

    def test_detect_timestamp_iso8601(self) -> None:
        result = detect_timestamp("2024-01-15T10:30:45")
        assert result is not None
        assert result.field_type == "timestamp"
        assert result.semantic_name == "timestamp"

    def test_detect_timestamp_iso8601_with_z(self) -> None:
        result = detect_timestamp("2024-01-15T10:30:45Z")
        assert result is not None
        assert result.field_type == "timestamp"

    def test_detect_timestamp_iso8601_microseconds(self) -> None:
        result = detect_timestamp("2024-01-15T10:30:45.123456Z")
        assert result is not None
        assert result.field_type == "timestamp"
        assert ".%f" in result.config.get("format", "")

    def test_detect_timestamp_clf(self) -> None:
        result = detect_timestamp("21/Dec/2024:10:15:30 +0000")
        assert result is not None
        assert result.field_type == "timestamp"
        assert "%d/%b/%Y" in result.config.get("format", "")

    def test_detect_timestamp_datetime(self) -> None:
        result = detect_timestamp("2024-01-15 10:30:45")
        assert result is not None
        assert result.field_type == "timestamp"

    def test_detect_timestamp_epoch(self) -> None:
        result = detect_timestamp("1705312245")
        assert result is not None
        assert result.field_type == "timestamp"

    def test_detect_timestamp_invalid(self) -> None:
        result = detect_timestamp("not-a-timestamp")
        assert result is None

    def test_detect_uuid(self) -> None:
        result = detect_by_pattern("550e8400-e29b-41d4-a716-446655440000")
        assert result is not None
        assert result.field_type == "uuid"
        assert result.semantic_name == "uuid"

    def test_detect_uuid_uppercase(self) -> None:
        result = detect_by_pattern("550E8400-E29B-41D4-A716-446655440000")
        assert result is not None
        assert result.field_type == "uuid"

    def test_detect_ipv4(self) -> None:
        result = detect_by_pattern("192.168.1.100")
        assert result is not None
        assert result.field_type == "ip"
        assert result.semantic_name == "ip"

    def test_detect_ipv4_private(self) -> None:
        result = detect_by_pattern("10.0.0.1")
        assert result is not None
        assert result.field_type == "ip"

    def test_detect_http_method(self) -> None:
        for method in ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]:
            result = detect_by_pattern(method)
            assert result is not None
            assert result.field_type == "choice"
            assert result.semantic_name == "method"

    def test_detect_log_level(self) -> None:
        for level in ["DEBUG", "INFO", "WARN", "WARNING", "ERROR", "FATAL", "CRITICAL"]:
            result = detect_by_pattern(level)
            assert result is not None
            assert result.field_type == "choice"
            assert result.semantic_name == "level"

    def test_detect_http_status(self) -> None:
        for status in ["200", "201", "301", "404", "500"]:
            result = detect_by_pattern(status)
            assert result is not None
            assert result.field_type == "choice"
            assert result.semantic_name == "status"

    def test_detect_url_path(self) -> None:
        result = detect_by_pattern("/api/users/123")
        assert result is not None
        assert result.field_type == "choice"
        assert result.semantic_name == "path"

    def test_detect_integer(self) -> None:
        result = detect_number("12345")
        assert result is not None
        assert result.field_type == "int"
        assert result.config["min"] == 12345
        assert result.config["max"] == 12345

    def test_detect_negative_integer(self) -> None:
        result = detect_number("-100")
        assert result is not None
        assert result.field_type == "int"
        assert result.config["min"] == -100

    def test_detect_float(self) -> None:
        result = detect_number("3.14159")
        assert result is not None
        assert result.field_type == "float"

    def test_detect_field_type_composite(self) -> None:
        # Test full detection pipeline
        assert detect_field_type("192.168.1.1").field_type == "ip"
        assert detect_field_type("GET").field_type == "choice"
        assert detect_field_type("2024-01-15T10:30:45").field_type == "timestamp"
        assert detect_field_type("42").field_type == "int"
        assert detect_field_type("hello world").field_type == "choice"

    def test_aggregate_detections_int(self) -> None:
        detections = [
            DetectionResult("int", {"type": "int", "min": 10, "max": 10}, 0.9),
            DetectionResult("int", {"type": "int", "min": 50, "max": 50}, 0.9),
            DetectionResult("int", {"type": "int", "min": 100, "max": 100}, 0.9),
        ]
        result = aggregate_detections(detections)
        assert result["type"] == "int"
        assert result["min"] == 10
        assert result["max"] == 100

    def test_aggregate_detections_choice(self) -> None:
        detections = [
            DetectionResult("choice", {"type": "choice", "values": ["GET"]}, 0.9),
            DetectionResult("choice", {"type": "choice", "values": ["POST"]}, 0.9),
            DetectionResult("choice", {"type": "choice", "values": ["GET"]}, 0.9),
        ]
        result = aggregate_detections(detections)
        assert result["type"] == "choice"
        assert set(result["values"]) == {"GET", "POST"}


class TestParser:
    """Tests for log line parsing."""

    def test_detect_format_json(self) -> None:
        line = '{"level": "INFO", "message": "Hello"}'
        assert detect_format(line) == LogFormat.JSON

    def test_detect_format_logfmt(self) -> None:
        line = 'level=INFO message="Hello world" duration=0.5'
        assert detect_format(line) == LogFormat.LOGFMT

    def test_detect_format_plain(self) -> None:
        line = "2024-01-15 10:30:45 INFO Application started"
        assert detect_format(line) == LogFormat.PLAIN

    def test_parse_json(self) -> None:
        line = '{"level": "INFO", "message": "Hello", "count": 42}'
        result = parse_json(line)
        assert result["level"] == "INFO"
        assert result["message"] == "Hello"
        assert result["count"] == "42"

    def test_parse_logfmt(self) -> None:
        line = 'level=INFO message="Hello world" count=42'
        result = parse_logfmt(line)
        assert result["level"] == "INFO"
        assert result["message"] == "Hello world"
        assert result["count"] == "42"

    def test_tokenize_plain_simple(self) -> None:
        line = "hello world test"
        tokens = tokenize_plain(line)
        assert len(tokens) == 3
        assert tokens[0].value == "hello"
        assert tokens[1].value == "world"
        assert tokens[2].value == "test"

    def test_tokenize_plain_with_brackets(self) -> None:
        line = "[2024-01-15] INFO Hello"
        tokens = tokenize_plain(line)
        assert len(tokens) == 3
        assert tokens[0].value == "2024-01-15"
        assert tokens[1].value == "INFO"
        assert tokens[2].value == "Hello"

    def test_tokenize_plain_with_quotes(self) -> None:
        line = 'GET "/api/users" 200'
        tokens = tokenize_plain(line)
        assert len(tokens) == 3
        assert tokens[0].value == "GET"
        assert tokens[1].value == "/api/users"
        assert tokens[2].value == "200"

    def test_parse_line_json(self) -> None:
        line = '{"level": "INFO"}'
        result = parse_line(line)
        assert result.format == LogFormat.JSON
        assert result.fields["level"] == "INFO"

    def test_parse_line_logfmt(self) -> None:
        line = "level=INFO message=test"
        result = parse_line(line)
        assert result.format == LogFormat.LOGFMT
        assert result.fields["level"] == "INFO"

    def test_parse_line_plain(self) -> None:
        line = "192.168.1.1 GET /api"
        result = parse_line(line)
        assert result.format == LogFormat.PLAIN
        assert len(result.fields) == 3


class TestSchemaInferrer:
    """Tests for the main inference engine."""

    def test_infer_json_logs(self) -> None:
        lines = [
            '{"timestamp": "2024-01-15T10:30:45", "level": "INFO", "message": "Started"}',
            '{"timestamp": "2024-01-15T10:30:46", "level": "DEBUG", "message": "Processing"}',
            '{"timestamp": "2024-01-15T10:30:47", "level": "ERROR", "message": "Failed"}',
        ]
        inferrer = SchemaInferrer()
        result = inferrer.infer(lines, name="test")

        assert result["name"] == "test"
        assert result["format"] == "json"
        assert "timestamp" in result["fields"]
        assert "level" in result["fields"]
        assert "message" in result["fields"]

    def test_infer_logfmt_logs(self) -> None:
        lines = [
            'ts=2024-01-15T10:30:45 level=INFO msg="Started"',
            'ts=2024-01-15T10:30:46 level=DEBUG msg="Processing"',
            'ts=2024-01-15T10:30:47 level=ERROR msg="Failed"',
        ]
        inferrer = SchemaInferrer()
        result = inferrer.infer(lines, name="test")

        assert result["name"] == "test"
        assert result["format"] == "logfmt"
        assert "ts" in result["fields"]
        assert "level" in result["fields"]

    def test_infer_plain_nginx_logs(self) -> None:
        lines = [
            '192.168.1.50 - - [21/Dec/2024:10:15:30 +0000] "GET /api/users HTTP/1.1" 200 1234',
            '10.0.0.15 - - [21/Dec/2024:10:15:31 +0000] "POST /api/login HTTP/1.1" 201 89',
            '192.168.1.51 - - [21/Dec/2024:10:15:32 +0000] "GET /api/posts HTTP/1.1" 200 5678',
        ]
        inferrer = SchemaInferrer()
        result = inferrer.infer(lines, name="nginx-test")

        assert result["name"] == "nginx-test"
        assert result["format"] == "plain"
        assert len(result["fields"]) > 0

        # Check that IP and timestamp were detected
        fields = result["fields"]
        has_ip = any(f.get("type") == "ip" for f in fields.values())
        has_timestamp = any(f.get("type") == "timestamp" for f in fields.values())
        assert has_ip, "Should detect IP field"
        assert has_timestamp, "Should detect timestamp field"

    def test_infer_from_file(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"
        log_file.write_text(
            '{"level": "INFO", "msg": "test1"}\n'
            '{"level": "DEBUG", "msg": "test2"}\n'
            '{"level": "ERROR", "msg": "test3"}\n'
        )

        inferrer = SchemaInferrer()
        result = inferrer.infer_from_file(log_file)

        assert result["name"] == "test"
        assert result["format"] == "json"
        assert "level" in result["fields"]

    def test_infer_from_file_not_found(self) -> None:
        inferrer = SchemaInferrer()
        with pytest.raises(FileNotFoundError):
            inferrer.infer_from_file("/nonexistent/path.log")

    def test_infer_empty_lines(self) -> None:
        inferrer = SchemaInferrer()
        with pytest.raises(ValueError, match="No log lines"):
            inferrer.infer([], name="test")

    def test_infer_with_format_hint(self) -> None:
        # This could be parsed as logfmt but we force JSON
        lines = ['{"a": "1"}', '{"a": "2"}']
        inferrer = SchemaInferrer()
        result = inferrer.infer(lines, format_hint="json")
        assert result["format"] == "json"

    def test_infer_detects_semantic_names(self) -> None:
        lines = [
            "192.168.1.1 GET /api/users 200",
            "10.0.0.1 POST /api/login 201",
            "172.16.0.1 DELETE /api/users/1 204",
        ]
        inferrer = SchemaInferrer()
        result = inferrer.infer(lines)

        fields = result["fields"]
        # Should have semantic names like "ip", "method", "path", "status"
        field_names = list(fields.keys())
        assert "ip" in field_names or any(
            f.get("type") == "ip" for f in fields.values()
        )


class TestCLIIntegration:
    """Integration tests for CLI infer command."""

    def test_cli_infer_help(self) -> None:
        from typer.testing import CliRunner

        from logsynth.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["infer", "--help"])
        assert result.exit_code == 0
        assert "Infer a template schema" in result.output

    def test_cli_infer_file_not_found(self) -> None:
        from typer.testing import CliRunner

        from logsynth.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["infer", "/nonexistent/file.log"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_cli_infer_basic(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from logsynth.cli import app

        # Create test log file
        log_file = tmp_path / "test.log"
        log_file.write_text(
            '{"level": "INFO", "message": "test"}\n'
            '{"level": "DEBUG", "message": "test2"}\n'
        )

        runner = CliRunner()
        result = runner.invoke(app, ["infer", str(log_file)])
        assert result.exit_code == 0
        assert "name:" in result.output.lower() or "Inferred Template" in result.output

    def test_cli_infer_preview(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from logsynth.cli import app

        log_file = tmp_path / "test.log"
        log_file.write_text(
            '{"level": "INFO"}\n'
            '{"level": "DEBUG"}\n'
        )

        runner = CliRunner()
        result = runner.invoke(app, ["infer", str(log_file), "--preview"])
        assert result.exit_code == 0
        assert "Detected Schema" in result.output

    def test_cli_infer_output_file(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from logsynth.cli import app

        log_file = tmp_path / "test.log"
        log_file.write_text('{"level": "INFO"}\n{"level": "DEBUG"}\n')

        output_file = tmp_path / "output.yaml"

        runner = CliRunner()
        result = runner.invoke(
            app, ["infer", str(log_file), "--output", str(output_file)]
        )
        assert result.exit_code == 0
        assert output_file.exists()
        assert "name:" in output_file.read_text()

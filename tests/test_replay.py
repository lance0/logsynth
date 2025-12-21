"""Tests for replay module."""

from __future__ import annotations

import time
from pathlib import Path

from logsynth.replay.player import (
    LogPlayer,
    TimedLine,
    extract_timestamp,
    parse_log_file,
    replay_file,
)


class TestExtractTimestamp:
    """Tests for timestamp extraction."""

    def test_iso8601(self) -> None:
        line = '2024-01-15T10:30:45 INFO Starting'
        ts, raw = extract_timestamp(line)
        assert ts is not None
        assert ts.year == 2024
        assert ts.month == 1
        assert ts.day == 15

    def test_iso8601_with_z(self) -> None:
        line = '2024-01-15T10:30:45Z INFO Starting'
        ts, raw = extract_timestamp(line)
        assert ts is not None

    def test_clf_format(self) -> None:
        line = '192.168.1.1 - - [21/Dec/2024:10:15:30 +0000] "GET /" 200'
        ts, raw = extract_timestamp(line)
        assert ts is not None
        assert ts.day == 21
        assert ts.month == 12

    def test_simple_datetime(self) -> None:
        line = '2024-01-15 10:30:45 INFO message'
        ts, raw = extract_timestamp(line)
        assert ts is not None
        assert ts.hour == 10
        assert ts.minute == 30

    def test_no_timestamp(self) -> None:
        line = 'Just a plain log line'
        ts, raw = extract_timestamp(line)
        assert ts is None
        assert raw is None


class TestParseLogFile:
    """Tests for log file parsing."""

    def test_parse_file(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"
        log_file.write_text(
            "2024-01-15T10:00:00 Line 1\n"
            "2024-01-15T10:00:01 Line 2\n"
            "2024-01-15T10:00:02 Line 3\n"
        )

        lines = parse_log_file(log_file)
        assert len(lines) == 3
        assert all(line.timestamp is not None for line in lines)

    def test_parse_file_max_lines(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"
        log_file.write_text(
            "2024-01-15T10:00:00 Line 1\n"
            "2024-01-15T10:00:01 Line 2\n"
            "2024-01-15T10:00:02 Line 3\n"
        )

        lines = parse_log_file(log_file, max_lines=2)
        assert len(lines) == 2

    def test_parse_file_skips_empty(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"
        log_file.write_text(
            "2024-01-15T10:00:00 Line 1\n"
            "\n"
            "2024-01-15T10:00:01 Line 2\n"
        )

        lines = parse_log_file(log_file)
        assert len(lines) == 2


class TestLogPlayer:
    """Tests for LogPlayer class."""

    def test_play_without_timing(self) -> None:
        lines = [
            TimedLine(line="Line 1", timestamp=None, raw_timestamp=None),
            TimedLine(line="Line 2", timestamp=None, raw_timestamp=None),
        ]
        player = LogPlayer(lines)

        output: list[str] = []
        played = player.play(write=output.append)

        assert played == 2
        assert output == ["Line 1", "Line 2"]

    def test_play_with_speed(self, tmp_path: Path) -> None:
        # Create log file with 1 second gap
        log_file = tmp_path / "test.log"
        log_file.write_text(
            "2024-01-15T10:00:00 Line 1\n"
            "2024-01-15T10:00:01 Line 2\n"
        )

        lines = parse_log_file(log_file)
        player = LogPlayer(lines, speed=10.0)  # 10x speed

        output: list[str] = []
        start = time.monotonic()
        player.play(write=output.append)
        elapsed = time.monotonic() - start

        assert len(output) == 2
        # At 10x speed, 1 second gap becomes 0.1 seconds
        assert elapsed < 0.5  # Should be much faster than real-time

    def test_play_empty(self) -> None:
        player = LogPlayer([])
        played = player.play(write=lambda x: None)
        assert played == 0

    def test_stop(self) -> None:
        lines = [
            TimedLine(line=f"Line {i}", timestamp=None, raw_timestamp=None)
            for i in range(100)
        ]
        player = LogPlayer(lines)
        player.stop()

        output: list[str] = []
        played = player.play(write=output.append)

        assert played == 0


class TestReplayFile:
    """Tests for replay_file function."""

    def test_replay_file_basic(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"
        log_file.write_text(
            "2024-01-15T10:00:00 Line 1\n"
            "2024-01-15T10:00:00 Line 2\n"
        )

        output: list[str] = []
        replayed = replay_file(
            path=log_file,
            write=output.append,
            speed=100.0,  # Fast
        )

        assert replayed == 2
        assert len(output) == 2


def _strip_ansi(text: str) -> str:
    """Strip ANSI escape codes from text."""
    import re

    return re.sub(r"\x1b\[[0-9;]*m", "", text)


class TestCLIIntegration:
    """Integration tests for replay command."""

    def test_cli_replay_help(self) -> None:
        from typer.testing import CliRunner

        from logsynth.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["replay", "--help"])
        output = _strip_ansi(result.output)
        assert result.exit_code == 0
        assert "Replay" in output or "replay" in output.lower()

    def test_cli_replay_file_not_found(self) -> None:
        from typer.testing import CliRunner

        from logsynth.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["replay", "/nonexistent/file.log"])
        output = _strip_ansi(result.output)
        assert result.exit_code == 1
        assert "not found" in output.lower()

    def test_cli_replay_basic(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from logsynth.cli import app

        log_file = tmp_path / "test.log"
        log_file.write_text(
            "2024-01-15T10:00:00 Line 1\n"
            "2024-01-15T10:00:00 Line 2\n"
        )

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["replay", str(log_file), "--speed", "100"],
        )
        output = _strip_ansi(result.output)
        assert result.exit_code == 0
        assert "Replayed" in output or "replayed" in output.lower()

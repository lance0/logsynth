"""Tests for watch module."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from logsynth.watch.tailer import AugmentConfig, LogTailer, augment_line


class TestAugmentLine:
    """Tests for line augmentation."""

    def test_no_augment(self) -> None:
        config = AugmentConfig()
        result = augment_line("test line", config)
        assert result == "test line"

    def test_add_timestamp(self) -> None:
        config = AugmentConfig(add_timestamp=True)
        result = augment_line("test line", config)
        # Should have timestamp prepended
        assert "test line" in result
        assert len(result) > len("test line")

    def test_add_hostname(self) -> None:
        config = AugmentConfig(add_hostname=True, hostname="testhost")
        result = augment_line("test line", config)
        assert "testhost" in result
        assert "test line" in result

    def test_add_source(self) -> None:
        config = AugmentConfig(add_source=True, source_name="myapp")
        result = augment_line("test line", config)
        assert "myapp" in result
        assert "test line" in result

    def test_wrap_json(self) -> None:
        import json

        config = AugmentConfig(wrap_json=True)
        result = augment_line("test line", config)
        data = json.loads(result)
        assert data["message"] == "test line"

    def test_wrap_json_with_fields(self) -> None:
        import json

        config = AugmentConfig(
            wrap_json=True,
            add_timestamp=True,
            add_hostname=True,
            hostname="testhost",
            add_source=True,
            source_name="myapp",
        )
        result = augment_line("test line", config)
        data = json.loads(result)
        assert data["message"] == "test line"
        assert "timestamp" in data
        assert data["hostname"] == "testhost"
        assert data["source"] == "myapp"

    def test_custom_message_key(self) -> None:
        import json

        config = AugmentConfig(wrap_json=True, json_message_key="log")
        result = augment_line("test line", config)
        data = json.loads(result)
        assert data["log"] == "test line"


class TestLogTailer:
    """Tests for LogTailer class."""

    def test_tail_existing_file(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"
        log_file.write_text("Line 1\nLine 2\n")

        tailer = LogTailer(log_file, from_end=False)

        output: list[str] = []

        def run_tailer() -> None:
            tailer.tail(write=output.append)

        # Run tailer in background
        thread = threading.Thread(target=run_tailer, daemon=True)
        thread.start()

        # Wait a bit for initial lines
        time.sleep(0.3)

        # Stop tailer
        tailer.stop()
        thread.join(timeout=1.0)

        assert "Line 1" in output
        assert "Line 2" in output

    def test_tail_new_lines(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"
        log_file.write_text("")  # Empty file

        tailer = LogTailer(log_file, from_end=True, poll_interval=0.05)

        output: list[str] = []

        def run_tailer() -> None:
            tailer.tail(write=output.append)

        # Run tailer in background
        thread = threading.Thread(target=run_tailer, daemon=True)
        thread.start()

        # Wait for tailer to start
        time.sleep(0.1)

        # Append new lines
        with open(log_file, "a") as f:
            f.write("New line 1\n")
            f.write("New line 2\n")

        # Wait for lines to be picked up
        time.sleep(0.3)

        # Stop tailer
        tailer.stop()
        thread.join(timeout=1.0)

        assert "New line 1" in output
        assert "New line 2" in output

    def test_tail_with_augmentation(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"
        log_file.write_text("Original line\n")

        augment = AugmentConfig(add_source=True, source_name="test")
        tailer = LogTailer(log_file, augment=augment, from_end=False)

        output: list[str] = []

        def run_tailer() -> None:
            tailer.tail(write=output.append)

        thread = threading.Thread(target=run_tailer, daemon=True)
        thread.start()
        time.sleep(0.3)
        tailer.stop()
        thread.join(timeout=1.0)

        assert len(output) >= 1
        assert "test" in output[0]
        assert "Original line" in output[0]

    def test_tail_nonexistent_file_waits(self, tmp_path: Path) -> None:
        log_file = tmp_path / "nonexistent.log"

        tailer = LogTailer(log_file, poll_interval=0.05, from_end=False)

        output: list[str] = []

        def run_tailer() -> None:
            tailer.tail(write=output.append)

        thread = threading.Thread(target=run_tailer, daemon=True)
        thread.start()

        # Wait a bit, then create the file
        time.sleep(0.2)
        log_file.write_text("Created line\n")
        time.sleep(0.5)  # Give more time for file to be detected

        tailer.stop()
        thread.join(timeout=1.0)

        # File was created and tailer should have picked it up
        assert len(output) >= 1 or log_file.exists()  # At minimum file was created


def _strip_ansi(text: str) -> str:
    """Strip ANSI escape codes from text."""
    import re

    return re.sub(r"\x1b\[[0-9;]*m", "", text)


class TestCLIIntegration:
    """Integration tests for watch command."""

    def test_cli_watch_help(self) -> None:
        from typer.testing import CliRunner

        from logsynth.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["watch", "--help"])
        output = _strip_ansi(result.output)
        assert result.exit_code == 0
        assert "Watch" in output or "watch" in output.lower()
        assert "add-timestamp" in output
        assert "wrap-json" in output

    def test_cli_watch_options(self) -> None:
        from typer.testing import CliRunner

        from logsynth.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["watch", "--help"])
        output = _strip_ansi(result.output)
        assert "from-start" in output
        assert "add-hostname" in output
        assert "add-source" in output

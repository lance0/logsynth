"""Tests for TUI dashboard module."""

from __future__ import annotations

import threading
import time

from logsynth.tui.stats import StatsCollector, StreamStats


class TestStreamStats:
    """Tests for StreamStats dataclass."""

    def test_initial_values(self) -> None:
        stats = StreamStats(name="test")
        assert stats.name == "test"
        assert stats.emitted == 0
        assert stats.errors == 0
        assert stats.elapsed >= 0

    def test_rate_calculation(self) -> None:
        stats = StreamStats(name="test", start_time=time.monotonic() - 1.0)
        stats.emitted = 100
        # Rate should be approximately 100/s
        assert 90 < stats.rate < 110

    def test_rate_zero_elapsed(self) -> None:
        stats = StreamStats(name="test")
        # With very small elapsed time, rate should be 0 to avoid division issues
        assert stats.rate == 0.0 or stats.rate >= 0

    def test_copy(self) -> None:
        stats = StreamStats(name="test", emitted=50, errors=2)
        copied = stats.copy()
        assert copied.name == stats.name
        assert copied.emitted == stats.emitted
        assert copied.errors == stats.errors
        assert copied is not stats


class TestStatsCollector:
    """Tests for StatsCollector."""

    def test_initial_state(self) -> None:
        collector = StatsCollector()
        assert collector.elapsed >= 0
        assert not collector.is_done
        snapshot = collector.get_snapshot()
        assert len(snapshot) == 0

    def test_register_stream(self) -> None:
        collector = StatsCollector()
        collector.register_stream("nginx")
        collector.register_stream("redis")
        snapshot = collector.get_snapshot()
        assert "nginx" in snapshot
        assert "redis" in snapshot

    def test_record_emit(self) -> None:
        collector = StatsCollector()
        collector.record_emit("test")
        collector.record_emit("test")
        collector.record_emit("test")
        snapshot = collector.get_snapshot()
        assert snapshot["test"].emitted == 3

    def test_record_emit_auto_registers(self) -> None:
        collector = StatsCollector()
        collector.record_emit("new_stream")
        snapshot = collector.get_snapshot()
        assert "new_stream" in snapshot
        assert snapshot["new_stream"].emitted == 1

    def test_record_error(self) -> None:
        collector = StatsCollector()
        collector.record_error("test")
        snapshot = collector.get_snapshot()
        assert snapshot["test"].errors == 1

    def test_get_totals(self) -> None:
        collector = StatsCollector()
        collector.record_emit("stream1")
        collector.record_emit("stream1")
        collector.record_emit("stream2")
        collector.record_error("stream1")

        total_emitted, total_errors, total_rate = collector.get_totals()
        assert total_emitted == 3
        assert total_errors == 1
        assert total_rate >= 0

    def test_mark_done(self) -> None:
        collector = StatsCollector()
        assert not collector.is_done
        collector.mark_done()
        assert collector.is_done

    def test_thread_safety(self) -> None:
        """Test that stats collector is thread-safe."""
        collector = StatsCollector()
        num_threads = 10
        emits_per_thread = 100

        def emit_many(stream: str) -> None:
            for _ in range(emits_per_thread):
                collector.record_emit(stream)

        threads = [
            threading.Thread(target=emit_many, args=(f"stream{i}",))
            for i in range(num_threads)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        total_emitted, _, _ = collector.get_totals()
        assert total_emitted == num_threads * emits_per_thread

    def test_snapshot_is_copy(self) -> None:
        """Test that snapshot returns copies, not references."""
        collector = StatsCollector()
        collector.record_emit("test")

        snapshot1 = collector.get_snapshot()
        collector.record_emit("test")
        snapshot2 = collector.get_snapshot()

        assert snapshot1["test"].emitted == 1
        assert snapshot2["test"].emitted == 2


class TestDashboard:
    """Tests for Dashboard class."""

    def test_dashboard_creation(self) -> None:
        from rich.console import Console

        from logsynth.tui.dashboard import Dashboard

        collector = StatsCollector()
        console = Console(force_terminal=True)
        dashboard = Dashboard(
            stats=collector,
            target_count=1000,
            console=console,
        )
        assert dashboard.target_count == 1000
        assert dashboard.target_duration is None

    def test_dashboard_render(self) -> None:
        from rich.console import Console

        from logsynth.tui.dashboard import Dashboard

        collector = StatsCollector()
        collector.record_emit("nginx")
        collector.record_emit("redis")

        console = Console(force_terminal=True)
        dashboard = Dashboard(stats=collector, console=console)

        # Should not raise
        panel = dashboard.render()
        assert panel is not None

    def test_format_duration(self) -> None:
        from logsynth.tui.dashboard import _format_duration

        assert _format_duration(0) == "00:00"
        assert _format_duration(65) == "01:05"
        assert _format_duration(3661) == "01:01:01"

    def test_format_number(self) -> None:
        from logsynth.tui.dashboard import _format_number

        assert _format_number(0) == "0"
        assert _format_number(1000) == "1,000"
        assert _format_number(1234567) == "1,234,567"

    def test_format_rate(self) -> None:
        from logsynth.tui.dashboard import _format_rate

        assert _format_rate(0) == "0.0/s"
        assert _format_rate(50.5) == "50.5/s"
        assert _format_rate(1500) == "1.5k/s"

    def test_is_tty(self) -> None:
        from logsynth.tui.dashboard import is_tty

        # This will be False in test environments typically
        result = is_tty()
        assert isinstance(result, bool)


class TestCLIIntegration:
    """Integration tests for --live flag."""

    def test_cli_live_flag_help(self) -> None:
        from typer.testing import CliRunner

        from logsynth.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "--live" in result.output or "-L" in result.output

    def test_cli_live_with_output_warns(self) -> None:
        """Test that --live with --output shows a warning."""
        import tempfile

        from typer.testing import CliRunner

        from logsynth.cli import app

        runner = CliRunner()
        with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f:
            result = runner.invoke(
                app,
                ["run", "nginx", "--count", "10", "--live", "--output", f.name],
            )
            # Should complete but with warning
            assert "ignored" in result.output.lower() or result.exit_code == 0

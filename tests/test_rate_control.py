"""Tests for rate control."""

import time

import pytest

from logsynth.core.rate_control import (
    parse_burst_pattern,
    parse_duration,
    run_with_count,
    run_with_duration,
)


class TestParseDuration:
    """Tests for duration parsing."""

    def test_seconds(self):
        """Should parse seconds."""
        assert parse_duration("30s") == 30.0
        assert parse_duration("1s") == 1.0
        assert parse_duration("0.5s") == 0.5

    def test_minutes(self):
        """Should parse minutes."""
        assert parse_duration("5m") == 300.0
        assert parse_duration("1m") == 60.0

    def test_hours(self):
        """Should parse hours."""
        assert parse_duration("1h") == 3600.0
        assert parse_duration("2h") == 7200.0

    def test_invalid_format_raises(self):
        """Should raise for invalid format."""
        with pytest.raises(ValueError, match="Invalid duration"):
            parse_duration("invalid")

    def test_invalid_unit_raises(self):
        """Should raise for unknown unit."""
        with pytest.raises(ValueError, match="Invalid duration"):
            parse_duration("10d")


class TestParseBurstPattern:
    """Tests for burst pattern parsing."""

    def test_single_segment(self):
        """Should parse single segment."""
        segments = parse_burst_pattern("100:5s")
        assert len(segments) == 1
        assert segments[0].rate == 100.0
        assert segments[0].duration == 5.0

    def test_multiple_segments(self):
        """Should parse multiple segments."""
        segments = parse_burst_pattern("100:5s,10:25s")
        assert len(segments) == 2
        assert segments[0].rate == 100.0
        assert segments[0].duration == 5.0
        assert segments[1].rate == 10.0
        assert segments[1].duration == 25.0

    def test_invalid_segment_raises(self):
        """Should raise for invalid segment."""
        with pytest.raises(ValueError, match="Invalid burst segment"):
            parse_burst_pattern("invalid")

    def test_empty_raises(self):
        """Should raise for empty pattern."""
        with pytest.raises(ValueError):
            parse_burst_pattern("")


class TestRunWithCount:
    """Tests for count-based emission."""

    def test_emits_correct_count(self):
        """Should emit exactly count lines."""
        lines = []
        counter = [0]

        def generate():
            counter[0] += 1
            return f"line {counter[0]}"

        def write(line):
            lines.append(line)

        emitted = run_with_count(rate=100, count=10, generate=generate, write=write)
        assert emitted == 10
        assert len(lines) == 10

    def test_respects_rate(self):
        """Should respect rate approximately."""
        lines = []

        def generate():
            return "line"

        def write(line):
            lines.append(line)

        start = time.monotonic()
        run_with_count(rate=10, count=5, generate=generate, write=write)
        elapsed = time.monotonic() - start

        # 5 lines at 10/s should take ~0.4s (first is immediate)
        assert 0.3 < elapsed < 0.6

    def test_invalid_rate_raises(self):
        """Should raise for invalid rate."""
        with pytest.raises(ValueError, match="Rate must be positive"):
            run_with_count(rate=0, count=10, generate=lambda: "", write=lambda x: None)

    def test_invalid_count_raises(self):
        """Should raise for invalid count."""
        with pytest.raises(ValueError, match="Count must be positive"):
            run_with_count(rate=10, count=0, generate=lambda: "", write=lambda x: None)


class TestRunWithDuration:
    """Tests for duration-based emission."""

    def test_runs_for_duration(self):
        """Should run for approximately the specified duration."""
        lines = []

        def generate():
            return "line"

        def write(line):
            lines.append(line)

        start = time.monotonic()
        emitted = run_with_duration(rate=100, duration="0.5s", generate=generate, write=write)
        elapsed = time.monotonic() - start

        assert 0.4 < elapsed < 0.7
        # At 100/s for 0.5s, expect ~50 lines
        assert 40 < emitted < 60

    def test_accepts_string_duration(self):
        """Should accept duration as string."""
        lines = []
        emitted = run_with_duration(
            rate=100,
            duration="100ms",
            generate=lambda: "line",
            write=lambda x: lines.append(x)
        )
        assert emitted > 0

    def test_invalid_duration_raises(self):
        """Should raise for invalid duration."""
        with pytest.raises(ValueError, match="Duration must be positive"):
            run_with_duration(
                rate=10,
                duration=0,
                generate=lambda: "",
                write=lambda x: None
            )

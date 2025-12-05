"""Rate-controlled log emission with duration and count-based loops."""

from __future__ import annotations

import re
import signal
import time
from collections.abc import Callable
from dataclasses import dataclass

# Shutdown flag for graceful exit
_shutdown_requested = False


def _signal_handler(signum: int, frame: object) -> None:
    """Handle shutdown signals."""
    global _shutdown_requested
    _shutdown_requested = True


def _setup_signal_handlers() -> None:
    """Set up signal handlers for graceful shutdown (main thread only)."""
    import threading

    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)


def _reset_shutdown() -> None:
    """Reset shutdown flag (for testing/reuse)."""
    global _shutdown_requested
    _shutdown_requested = False


def parse_duration(duration_str: str) -> float:
    """Parse a duration string like '30s', '5m', '1h', '100ms' into seconds."""
    match = re.match(r"^(\d+(?:\.\d+)?)(ms|s|m|h)$", duration_str.strip().lower())
    if not match:
        raise ValueError(
            f"Invalid duration format: {duration_str}. Use format like '30s', '5m', '1h', '100ms'"
        )

    amount = float(match.group(1))
    unit = match.group(2)

    if unit == "ms":
        return amount / 1000.0
    elif unit == "s":
        return amount
    elif unit == "m":
        return amount * 60
    elif unit == "h":
        return amount * 3600
    else:
        raise ValueError(f"Unknown duration unit: {unit}")


@dataclass
class BurstSegment:
    """A segment of a burst pattern."""

    rate: float  # lines per second
    duration: float  # seconds


def parse_burst_pattern(pattern_str: str) -> list[BurstSegment]:
    """Parse a burst pattern string like '100:5s,10:25s' into segments.

    Format: rate:duration,rate:duration,...
    Example: 100:5s,10:25s means 100 lps for 5 seconds, then 10 lps for 25 seconds
    """
    segments = []
    for part in pattern_str.split(","):
        part = part.strip()
        if ":" not in part:
            raise ValueError(f"Invalid burst segment '{part}'. Format: rate:duration")

        rate_str, duration_str = part.split(":", 1)
        try:
            rate = float(rate_str)
        except ValueError:
            raise ValueError(f"Invalid rate '{rate_str}' in burst pattern")

        duration = parse_duration(duration_str)
        segments.append(BurstSegment(rate=rate, duration=duration))

    if not segments:
        raise ValueError("Burst pattern cannot be empty")

    return segments


GenerateFn = Callable[[], str]
WriteFn = Callable[[str], None]


def run_with_count(
    rate: float,
    count: int,
    generate: GenerateFn,
    write: WriteFn,
) -> int:
    """Emit log lines at a given rate until count is reached.

    Args:
        rate: Lines per second (can be fractional, e.g., 0.5 = 1 line per 2 seconds)
        count: Total number of lines to emit
        generate: Function that generates a single log line
        write: Function that writes a log line

    Returns:
        Number of lines actually emitted
    """
    global _shutdown_requested
    _reset_shutdown()
    _setup_signal_handlers()

    if rate <= 0:
        raise ValueError("Rate must be positive")
    if count <= 0:
        raise ValueError("Count must be positive")

    interval = 1.0 / rate
    emitted = 0
    start_time = time.monotonic()

    while emitted < count and not _shutdown_requested:
        target_time = start_time + (emitted * interval)
        now = time.monotonic()

        if now < target_time:
            sleep_time = target_time - now
            time.sleep(sleep_time)

        if _shutdown_requested:
            break

        line = generate()
        write(line)
        emitted += 1

    return emitted


def run_with_duration(
    rate: float,
    duration: float | str,
    generate: GenerateFn,
    write: WriteFn,
) -> int:
    """Emit log lines at a given rate for a duration.

    Args:
        rate: Lines per second (can be fractional)
        duration: Duration in seconds (float) or as string ('30s', '5m', '1h')
        generate: Function that generates a single log line
        write: Function that writes a log line

    Returns:
        Number of lines actually emitted
    """
    global _shutdown_requested
    _reset_shutdown()
    _setup_signal_handlers()

    if rate <= 0:
        raise ValueError("Rate must be positive")

    if isinstance(duration, str):
        duration = parse_duration(duration)

    if duration <= 0:
        raise ValueError("Duration must be positive")

    interval = 1.0 / rate
    emitted = 0
    start_time = time.monotonic()
    end_time = start_time + duration

    while time.monotonic() < end_time and not _shutdown_requested:
        target_time = start_time + (emitted * interval)
        now = time.monotonic()

        if now < target_time:
            # Don't sleep past end_time
            sleep_time = min(target_time - now, end_time - now)
            if sleep_time > 0:
                time.sleep(sleep_time)

        if time.monotonic() >= end_time or _shutdown_requested:
            break

        line = generate()
        write(line)
        emitted += 1

    return emitted


def run_with_burst(
    pattern: str | list[BurstSegment],
    duration: float | str,
    generate: GenerateFn,
    write: WriteFn,
) -> int:
    """Emit log lines following a burst pattern for a total duration.

    The pattern cycles until total duration is reached.

    Args:
        pattern: Burst pattern string or list of BurstSegments
        duration: Total duration in seconds or as string
        generate: Function that generates a single log line
        write: Function that writes a log line

    Returns:
        Number of lines actually emitted
    """
    global _shutdown_requested
    _reset_shutdown()
    _setup_signal_handlers()

    if isinstance(pattern, str):
        segments = parse_burst_pattern(pattern)
    else:
        segments = pattern

    if isinstance(duration, str):
        duration = parse_duration(duration)

    if duration <= 0:
        raise ValueError("Duration must be positive")

    emitted = 0
    start_time = time.monotonic()
    end_time = start_time + duration
    segment_idx = 0

    while time.monotonic() < end_time and not _shutdown_requested:
        segment = segments[segment_idx % len(segments)]
        segment_start = time.monotonic()
        segment_end = min(segment_start + segment.duration, end_time)

        interval = 1.0 / segment.rate if segment.rate > 0 else float("inf")
        segment_emitted = 0

        while time.monotonic() < segment_end and not _shutdown_requested:
            target_time = segment_start + (segment_emitted * interval)
            now = time.monotonic()

            if now < target_time:
                sleep_time = min(target_time - now, segment_end - now)
                if sleep_time > 0:
                    time.sleep(sleep_time)

            if time.monotonic() >= segment_end or _shutdown_requested:
                break

            line = generate()
            write(line)
            emitted += 1
            segment_emitted += 1

        segment_idx += 1

    return emitted


class RateController:
    """High-level rate controller that supports all emission modes."""

    def __init__(
        self,
        generate: GenerateFn,
        write: WriteFn,
        rate: float = 10.0,
    ) -> None:
        self.generate = generate
        self.write = write
        self.rate = rate

    def run_count(self, count: int) -> int:
        """Run until count lines are emitted."""
        return run_with_count(self.rate, count, self.generate, self.write)

    def run_duration(self, duration: float | str) -> int:
        """Run for a duration."""
        return run_with_duration(self.rate, duration, self.generate, self.write)

    def run_burst(self, pattern: str | list[BurstSegment], duration: float | str) -> int:
        """Run with a burst pattern."""
        return run_with_burst(pattern, duration, self.generate, self.write)

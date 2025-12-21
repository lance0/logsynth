"""Log replay with timing preservation."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Common timestamp patterns with their parsing formats
TIMESTAMP_PATTERNS: list[tuple[str, str]] = [
    # ISO 8601 (long pattern)
    (
        r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)",
        "%Y-%m-%dT%H:%M:%S",
    ),
    # ISO 8601 with space
    (r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?)", "%Y-%m-%d %H:%M:%S"),
    # CLF (Common Log Format) - nginx/apache
    (r"\[(\d{2}/\w{3}/\d{4}:\d{2}:\d{2}:\d{2}) [+-]\d{4}\]", "%d/%b/%Y:%H:%M:%S"),
    # Syslog
    (r"^(\w{3}\s+\d{1,2} \d{2}:\d{2}:\d{2})", "%b %d %H:%M:%S"),
    # Simple datetime
    (r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", "%Y-%m-%d %H:%M:%S"),
]


@dataclass
class TimedLine:
    """A log line with its parsed timestamp."""

    line: str
    timestamp: datetime | None
    raw_timestamp: str | None


def extract_timestamp(line: str) -> tuple[datetime | None, str | None]:
    """Extract timestamp from a log line."""
    for pattern, fmt in TIMESTAMP_PATTERNS:
        match = re.search(pattern, line)
        if match:
            ts_str = match.group(1)
            try:
                # Handle microseconds
                clean_ts = ts_str
                if "." in clean_ts:
                    # Truncate microseconds for parsing
                    base, micro = clean_ts.split(".", 1)
                    # Remove timezone if present after microseconds
                    micro = re.sub(r"[Z+-].*$", "", micro)
                    clean_ts = base

                # Handle Z suffix
                clean_ts = clean_ts.replace("Z", "")

                # Try parsing
                ts = datetime.strptime(clean_ts, fmt.replace(".%f", "").replace("%z", "").strip())
                return ts, ts_str
            except ValueError:
                continue
    return None, None


def parse_log_file(path: Path, max_lines: int | None = None) -> list[TimedLine]:
    """Parse a log file and extract timestamps."""
    lines: list[TimedLine] = []

    with open(path, encoding="utf-8", errors="ignore") as f:
        for i, line in enumerate(f):
            if max_lines and i >= max_lines:
                break

            line = line.rstrip("\n\r")
            if not line:
                continue

            ts, raw_ts = extract_timestamp(line)
            lines.append(TimedLine(line=line, timestamp=ts, raw_timestamp=raw_ts))

    return lines


class LogPlayer:
    """Replays log lines with original timing."""

    def __init__(
        self,
        lines: list[TimedLine],
        speed: float = 1.0,
        skip_gaps: float | None = None,
    ) -> None:
        """
        Initialize the log player.

        Args:
            lines: List of timed log lines
            speed: Playback speed multiplier (1.0 = real-time, 2.0 = 2x speed)
            skip_gaps: Skip gaps larger than this many seconds (None = no skip)
        """
        self.lines = lines
        self.speed = speed
        self.skip_gaps = skip_gaps
        self._stopped = False

    def stop(self) -> None:
        """Stop playback."""
        self._stopped = True

    def play(
        self,
        write: Callable[[str], None],
        on_progress: Callable[[int, int], None] | None = None,
    ) -> int:
        """
        Play back log lines with timing.

        Args:
            write: Function to write each line
            on_progress: Optional callback (current_line, total_lines)

        Returns:
            Number of lines played
        """
        if not self.lines:
            return 0

        if self._stopped:
            return 0

        total = len(self.lines)
        played = 0
        last_ts: datetime | None = None

        for i, timed_line in enumerate(self.lines):
            if self._stopped:
                break

            # Calculate delay based on timestamp difference
            if timed_line.timestamp and last_ts:
                delta = (timed_line.timestamp - last_ts).total_seconds()

                # Apply speed multiplier
                delay = delta / self.speed

                # Skip large gaps if configured
                if self.skip_gaps and delay > self.skip_gaps:
                    delay = self.skip_gaps / self.speed

                # Only sleep for positive delays
                if delay > 0:
                    time.sleep(delay)

            if self._stopped:
                break

            write(timed_line.line)
            played += 1

            if timed_line.timestamp:
                last_ts = timed_line.timestamp

            if on_progress:
                on_progress(i + 1, total)

        return played


def replay_file(
    path: Path | str,
    write: Callable[[str], None],
    speed: float = 1.0,
    skip_gaps: float | None = 60.0,
    max_lines: int | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> int:
    """
    Replay a log file with original timing.

    Args:
        path: Path to log file
        write: Function to write each line
        speed: Playback speed (1.0 = real-time)
        skip_gaps: Skip gaps larger than this (seconds), None to preserve all gaps
        max_lines: Maximum lines to replay
        on_progress: Progress callback

    Returns:
        Number of lines replayed
    """
    path = Path(path)
    lines = parse_log_file(path, max_lines)
    player = LogPlayer(lines, speed=speed, skip_gaps=skip_gaps)
    return player.play(write, on_progress)

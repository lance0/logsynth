"""Thread-safe stats collection for live dashboard."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class StreamStats:
    """Statistics for a single stream."""

    name: str
    emitted: int = 0
    errors: int = 0
    start_time: float = field(default_factory=time.monotonic)

    @property
    def elapsed(self) -> float:
        """Elapsed time in seconds."""
        return time.monotonic() - self.start_time

    @property
    def rate(self) -> float:
        """Current emission rate (lines per second)."""
        elapsed = self.elapsed
        return self.emitted / elapsed if elapsed > 0 else 0.0

    def copy(self) -> StreamStats:
        """Create a copy of this stats object."""
        return StreamStats(
            name=self.name,
            emitted=self.emitted,
            errors=self.errors,
            start_time=self.start_time,
        )


class StatsCollector:
    """Thread-safe collector for emission statistics."""

    def __init__(self) -> None:
        self._streams: dict[str, StreamStats] = {}
        self._lock = threading.Lock()
        self._start_time = time.monotonic()
        self._done = False

    @property
    def start_time(self) -> float:
        """Start time of collection."""
        return self._start_time

    @property
    def elapsed(self) -> float:
        """Total elapsed time."""
        return time.monotonic() - self._start_time

    @property
    def is_done(self) -> bool:
        """Check if collection is marked as done."""
        return self._done

    def mark_done(self) -> None:
        """Mark collection as complete."""
        self._done = True

    def register_stream(self, name: str) -> None:
        """Register a new stream for tracking."""
        with self._lock:
            if name not in self._streams:
                self._streams[name] = StreamStats(name=name, start_time=self._start_time)

    def record_emit(self, stream: str = "default") -> None:
        """Record a successful emission."""
        with self._lock:
            if stream not in self._streams:
                self._streams[stream] = StreamStats(name=stream, start_time=self._start_time)
            self._streams[stream].emitted += 1

    def record_error(self, stream: str = "default") -> None:
        """Record an error."""
        with self._lock:
            if stream not in self._streams:
                self._streams[stream] = StreamStats(name=stream, start_time=self._start_time)
            self._streams[stream].errors += 1

    def get_snapshot(self) -> dict[str, StreamStats]:
        """Get a snapshot of current stats (thread-safe copy)."""
        with self._lock:
            return {name: stats.copy() for name, stats in self._streams.items()}

    def get_totals(self) -> tuple[int, int, float]:
        """Get total emitted, errors, and rate across all streams."""
        with self._lock:
            total_emitted = sum(s.emitted for s in self._streams.values())
            total_errors = sum(s.errors for s in self._streams.values())
            elapsed = self.elapsed
            total_rate = total_emitted / elapsed if elapsed > 0 else 0.0
            return total_emitted, total_errors, total_rate

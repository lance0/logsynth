"""Parallel stream support for running multiple templates concurrently."""

from __future__ import annotations

import threading
from typing import Callable

from logsynth.core.generator import LogGenerator, create_generator
from logsynth.core.output import Sink
from logsynth.core.rate_control import run_with_count, run_with_duration


GenerateFn = Callable[[], str]
WriteFn = Callable[[str], None]


class StreamRunner:
    """Runs a single log stream in a thread."""

    def __init__(
        self,
        generator: LogGenerator,
        sink: Sink,
        rate: float,
        name: str | None = None,
    ) -> None:
        self.generator = generator
        self.sink = sink
        self.rate = rate
        self.name = name or generator.template.name
        self.emitted = 0
        self._thread: threading.Thread | None = None
        self._error: Exception | None = None

    def _run_duration(self, duration: float | str) -> None:
        """Run for a duration."""
        try:
            self.emitted = run_with_duration(
                self.rate,
                duration,
                self.generator.generate,
                self.sink.write,
            )
        except Exception as e:
            self._error = e

    def _run_count(self, count: int) -> None:
        """Run for a count."""
        try:
            self.emitted = run_with_count(
                self.rate,
                count,
                self.generator.generate,
                self.sink.write,
            )
        except Exception as e:
            self._error = e

    def start_duration(self, duration: float | str) -> None:
        """Start running in background for a duration."""
        self._thread = threading.Thread(
            target=self._run_duration,
            args=(duration,),
            daemon=True,
        )
        self._thread.start()

    def start_count(self, count: int) -> None:
        """Start running in background for a count."""
        self._thread = threading.Thread(
            target=self._run_count,
            args=(count,),
            daemon=True,
        )
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        """Wait for the stream to finish."""
        if self._thread:
            self._thread.join(timeout=timeout)

    @property
    def is_alive(self) -> bool:
        """Check if stream is still running."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def error(self) -> Exception | None:
        """Get any error that occurred."""
        return self._error


def run_parallel_streams(
    sources: list[str],
    sink: Sink,
    rate: float,
    duration: str | None = None,
    count: int | None = None,
    format_override: str | None = None,
    seed: int | None = None,
) -> dict[str, int]:
    """Run multiple template streams in parallel.

    Args:
        sources: List of template sources (preset names or file paths)
        sink: Output sink (shared between all streams)
        rate: Total rate split across all streams
        duration: Run duration (or count must be specified)
        count: Line count (or duration must be specified)
        format_override: Optional format override for all templates
        seed: Random seed

    Returns:
        Dictionary mapping template names to lines emitted
    """
    if not sources:
        raise ValueError("No template sources provided")

    # Calculate per-stream rate
    per_stream_rate = rate / len(sources)

    # Create generators and runners
    runners: list[StreamRunner] = []
    for source in sources:
        generator = create_generator(source, format_override, seed)
        runner = StreamRunner(generator, sink, per_stream_rate)
        runners.append(runner)

    # Start all streams
    if duration:
        for runner in runners:
            runner.start_duration(duration)
    elif count:
        per_stream_count = count // len(sources)
        for runner in runners:
            runner.start_count(per_stream_count)
    else:
        raise ValueError("Either duration or count must be specified")

    # Wait for all streams to finish
    for runner in runners:
        runner.join()

    # Check for errors
    errors = [(r.name, r.error) for r in runners if r.error]
    if errors:
        error_msgs = [f"{name}: {err}" for name, err in errors]
        raise RuntimeError(f"Stream errors: {'; '.join(error_msgs)}")

    # Return results
    return {runner.name: runner.emitted for runner in runners}

"""Parallel stream support for running multiple templates concurrently."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from logsynth.core.generator import LogGenerator, create_generator
from logsynth.core.output import Sink
from logsynth.core.rate_control import run_with_count, run_with_duration

if TYPE_CHECKING:
    from logsynth.tui.stats import StatsCollector

GenerateFn = Callable[[], str]
WriteFn = Callable[[str], None]


@dataclass
class StreamConfig:
    """Per-stream configuration overrides."""

    name: str
    rate: float | None = None
    format: str | None = None
    count: int | None = None


def parse_stream_config(spec: str) -> StreamConfig:
    """Parse stream config string like 'nginx:rate=50,format=json'.

    Format: name[:key=value[,key=value]...]
    """
    if ":" not in spec:
        return StreamConfig(name=spec)

    name, options_str = spec.split(":", 1)
    config = StreamConfig(name=name)

    for option in options_str.split(","):
        if "=" not in option:
            continue
        key, value = option.split("=", 1)
        key = key.strip()
        value = value.strip()

        if key == "rate":
            config.rate = float(value)
        elif key == "format":
            config.format = value
        elif key == "count":
            config.count = int(value)

    return config


class StreamRunner:
    """Runs a single log stream in a thread."""

    def __init__(
        self,
        generator: LogGenerator,
        sink: Sink,
        rate: float,
        name: str | None = None,
        stats_collector: StatsCollector | None = None,
    ) -> None:
        self.generator = generator
        self.sink = sink
        self.rate = rate
        self.name = name or generator.template.name
        self.emitted = 0
        self._thread: threading.Thread | None = None
        self._error: Exception | None = None
        self._stats_collector = stats_collector

    def _write(self, line: str) -> None:
        """Write a line and track stats."""
        self.sink.write(line)
        if self._stats_collector:
            self._stats_collector.record_emit(self.name)

    def _run_duration(self, duration: float | str) -> None:
        """Run for a duration."""
        try:
            self.emitted = run_with_duration(
                self.rate,
                duration,
                self.generator.generate,
                self._write,
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
                self._write,
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


def _get_source_name(source: str) -> str:
    """Extract template/preset name from source path."""
    path = Path(source)
    if path.exists():
        return path.stem
    return source


def run_parallel_streams(
    sources: list[str],
    sink: Sink,
    rate: float,
    duration: str | None = None,
    count: int | None = None,
    format_override: str | None = None,
    seed: int | None = None,
    stream_configs: dict[str, StreamConfig] | None = None,
    stats_collector: StatsCollector | None = None,
) -> dict[str, int]:
    """Run multiple template streams in parallel.

    Args:
        sources: List of template sources (preset names or file paths)
        sink: Output sink (shared between all streams)
        rate: Default rate (split across streams without specific rate)
        duration: Run duration (or count must be specified)
        count: Line count (or duration must be specified)
        format_override: Optional format override for all templates
        seed: Random seed
        stream_configs: Per-stream configuration overrides
        stats_collector: Optional stats collector for live dashboard

    Returns:
        Dictionary mapping template names to lines emitted
    """
    if not sources:
        raise ValueError("No template sources provided")

    stream_configs = stream_configs or {}

    # Count streams without explicit rates to split default rate
    streams_without_rate = sum(
        1 for s in sources if _get_source_name(s) not in stream_configs
        or stream_configs[_get_source_name(s)].rate is None
    )
    default_rate = rate / max(streams_without_rate, 1) if streams_without_rate else rate

    # Create generators and runners
    runners: list[StreamRunner] = []
    for source in sources:
        source_name = _get_source_name(source)
        cfg = stream_configs.get(source_name)

        # Determine stream-specific rate
        if cfg and cfg.rate is not None:
            stream_rate = cfg.rate
        else:
            stream_rate = default_rate

        # Determine stream-specific format
        stream_format = (cfg.format if cfg and cfg.format else format_override)

        generator = create_generator(source, stream_format, seed)
        runner = StreamRunner(generator, sink, stream_rate, stats_collector=stats_collector)
        runners.append(runner)

    # Start all streams
    if duration:
        for runner in runners:
            runner.start_duration(duration)
    elif count:
        # Per-stream count distribution
        for i, runner in enumerate(runners):
            source_name = _get_source_name(sources[i])
            cfg = stream_configs.get(source_name)
            if cfg and cfg.count is not None:
                stream_count = cfg.count
            else:
                stream_count = count // len(sources)
            runner.start_count(stream_count)
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

"""Output sinks for log emission."""

from __future__ import annotations

import json
import queue
import re
import socket
import sys
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import parse_qs, urlparse

import httpx


class Sink(ABC):
    """Abstract base class for output sinks."""

    @abstractmethod
    def write(self, line: str) -> None:
        """Write a single log line."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the sink and release resources."""
        pass

    def __enter__(self) -> Sink:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()


class StdoutSink(Sink):
    """Write logs to stdout."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self.stream = stream or sys.stdout

    def write(self, line: str) -> None:
        """Write line to stdout."""
        print(line, file=self.stream, flush=True)

    def close(self) -> None:
        """Nothing to close for stdout."""
        pass


class FileSink(Sink):
    """Write logs to a file."""

    def __init__(self, path: str | Path, append: bool = True) -> None:
        self.path = Path(path)
        self.mode = "a" if append else "w"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = open(self.path, self.mode)

    def write(self, line: str) -> None:
        """Write line to file."""
        self.file.write(line + "\n")
        self.file.flush()

    def close(self) -> None:
        """Close the file."""
        self.file.close()


class TcpSink(Sink):
    """Send logs over TCP."""

    def __init__(
        self,
        host: str,
        port: int,
        timeout: float = 30.0,
        reconnect: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.reconnect = reconnect
        self.socket: socket.socket | None = None
        self._connect()

    def _connect(self) -> None:
        """Establish TCP connection."""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(self.timeout)
        self.socket.connect((self.host, self.port))

    def write(self, line: str) -> None:
        """Send line over TCP."""
        data = (line + "\n").encode("utf-8")
        try:
            if self.socket:
                self.socket.sendall(data)
        except (BrokenPipeError, ConnectionResetError, OSError):
            if self.reconnect:
                self._connect()
                if self.socket:
                    self.socket.sendall(data)
            else:
                raise

    def close(self) -> None:
        """Close the TCP connection."""
        if self.socket:
            try:
                self.socket.close()
            except OSError:
                pass
            self.socket = None


class UdpSink(Sink):
    """Send logs over UDP."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def write(self, line: str) -> None:
        """Send line over UDP."""
        data = (line + "\n").encode("utf-8")
        self.socket.sendto(data, (self.host, self.port))

    def close(self) -> None:
        """Close the UDP socket."""
        self.socket.close()


class BufferedSink(Sink):
    """Wraps any sink with a bounded queue and worker thread.

    Provides non-blocking writes (unless queue is full) while the worker
    thread handles actual output to the inner sink.
    """

    def __init__(self, inner: Sink, maxsize: int = 10000) -> None:
        self.inner = inner
        self.queue: queue.Queue[str | None] = queue.Queue(maxsize=maxsize)
        self._shutdown = threading.Event()
        self._worker = threading.Thread(target=self._drain, daemon=True)
        self._worker.start()

    def _drain(self) -> None:
        """Worker thread that drains the queue to the inner sink."""
        while not self._shutdown.is_set():
            try:
                line = self.queue.get(timeout=0.1)
                if line is None:  # Shutdown sentinel
                    break
                self.inner.write(line)
                self.queue.task_done()
            except queue.Empty:
                continue

        # Drain remaining items after shutdown
        while True:
            try:
                line = self.queue.get_nowait()
                if line is not None:
                    self.inner.write(line)
                self.queue.task_done()
            except queue.Empty:
                break

    def write(self, line: str) -> None:
        """Queue a line for writing. Blocks if queue is full."""
        self.queue.put(line)

    def close(self) -> None:
        """Signal shutdown and wait for queue to drain."""
        self._shutdown.set()
        self.queue.put(None)  # Sentinel to wake up worker
        self._worker.join(timeout=5.0)
        self.inner.close()


class HttpBatchFormat(Enum):
    """Batch body formats for HTTP sink."""

    JSON = "json"  # JSON array: ["line1", "line2"]
    NDJSON = "ndjson"  # Newline-delimited: line1\nline2\n
    TEXT = "text"  # Plain text: line1\nline2\n


@dataclass
class HttpSinkConfig:
    """Configuration for HTTP sink."""

    url: str
    batch_size: int = 100
    batch_timeout: float = 5.0
    format: HttpBatchFormat = HttpBatchFormat.JSON
    headers: dict[str, str] = field(default_factory=dict)
    dead_letter_path: str | None = None

    # Retry configuration
    max_retries: int = 3
    retry_delay: float = 0.5
    retry_backoff: float = 2.0
    retry_max_delay: float = 30.0

    # HTTP client configuration
    timeout: float = 30.0
    verify_ssl: bool = True


class HttpSink(Sink):
    """Send logs to HTTP endpoint with batching and retries."""

    def __init__(self, config: HttpSinkConfig) -> None:
        self.config = config
        self._batch: list[str] = []
        self._lock = threading.Lock()
        self._last_flush = time.monotonic()
        self._shutdown = threading.Event()
        self._client = httpx.Client(
            timeout=config.timeout,
            verify=config.verify_ssl,
        )
        self._dead_letter_file: TextIO | None = None

        # Open dead letter file if configured
        if config.dead_letter_path:
            path = Path(config.dead_letter_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._dead_letter_file = open(path, "a")

        # Start background flush timer thread
        self._timer_thread = threading.Thread(
            target=self._flush_timer,
            daemon=True,
        )
        self._timer_thread.start()

    def _flush_timer(self) -> None:
        """Background thread that flushes based on timeout."""
        while not self._shutdown.wait(timeout=1.0):
            with self._lock:
                if self._batch and self._should_flush_by_time():
                    self._do_flush()

    def _should_flush_by_time(self) -> bool:
        """Check if batch timeout has elapsed."""
        return (time.monotonic() - self._last_flush) >= self.config.batch_timeout

    def write(self, line: str) -> None:
        """Add line to batch, flush if batch is full."""
        with self._lock:
            self._batch.append(line)
            if len(self._batch) >= self.config.batch_size:
                self._do_flush()

    def _do_flush(self) -> None:
        """Flush current batch to HTTP endpoint (called with lock held)."""
        if not self._batch:
            return

        batch = self._batch
        self._batch = []
        self._last_flush = time.monotonic()

        body, content_type = self._format_batch(batch)
        self._send_with_retry(body, content_type, batch)

    def _format_batch(self, batch: list[str]) -> tuple[str, str]:
        """Format batch according to configured format."""
        if self.config.format == HttpBatchFormat.JSON:
            return json.dumps(batch), "application/json"
        elif self.config.format == HttpBatchFormat.NDJSON:
            return "\n".join(batch) + "\n", "application/x-ndjson"
        else:  # TEXT
            return "\n".join(batch) + "\n", "text/plain"

    def _send_with_retry(
        self, body: str, content_type: str, batch: list[str]
    ) -> None:
        """Send batch with exponential backoff retry."""
        headers = {
            "Content-Type": content_type,
            **self.config.headers,
        }

        delay = self.config.retry_delay
        last_error: Exception | None = None

        for attempt in range(self.config.max_retries + 1):
            try:
                response = self._client.post(
                    self.config.url,
                    content=body,
                    headers=headers,
                )

                # Success or client error (4xx except 429)
                if response.status_code < 500 and response.status_code != 429:
                    if response.status_code >= 400:
                        # Client error - write to dead letter, don't retry
                        self._write_dead_letter(
                            batch, f"HTTP {response.status_code}: {response.text[:200]}"
                        )
                    return

                # Retryable server error
                last_error = Exception(f"HTTP {response.status_code}")

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_error = e

            # Don't sleep on last attempt
            if attempt < self.config.max_retries:
                time.sleep(delay)
                delay = min(
                    delay * self.config.retry_backoff, self.config.retry_max_delay
                )

        # All retries exhausted
        error_msg = str(last_error) if last_error else "Unknown error"
        self._write_dead_letter(batch, f"Retries exhausted: {error_msg}")
        print(
            f"HttpSink: failed after {self.config.max_retries + 1} attempts: {error_msg}",
            file=sys.stderr,
        )

    def _write_dead_letter(self, batch: list[str], error: str) -> None:
        """Write failed batch to dead letter file."""
        if not self._dead_letter_file:
            # Use default path if not configured
            default_path = Path("./logsynth-dead-letter.jsonl")
            self._dead_letter_file = open(default_path, "a")

        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "url": self.config.url,
            "error": error,
            "batch_size": len(batch),
            "batch": batch,
        }
        self._dead_letter_file.write(json.dumps(record) + "\n")
        self._dead_letter_file.flush()

    def flush(self) -> None:
        """Manually flush the current batch."""
        with self._lock:
            self._do_flush()

    def close(self) -> None:
        """Flush pending batch and close resources."""
        self._shutdown.set()
        self._timer_thread.join(timeout=2.0)

        with self._lock:
            self._do_flush()

        self._client.close()
        if self._dead_letter_file:
            self._dead_letter_file.close()


def parse_output_url(url: str) -> tuple[str, dict[str, Any]]:
    """Parse an output URL into type and parameters.

    Supported formats:
    - stdout (or -)
    - /path/to/file
    - tcp://host:port
    - udp://host:port
    - http://host:port/path?batch=N&timeout=T&format=F
    - https://host:port/path?...
    """
    if url in ("stdout", "-"):
        return "stdout", {}

    # TCP URL
    tcp_match = re.match(r"^tcp://([^:]+):(\d+)$", url)
    if tcp_match:
        return "tcp", {"host": tcp_match.group(1), "port": int(tcp_match.group(2))}

    # UDP URL
    udp_match = re.match(r"^udp://([^:]+):(\d+)$", url)
    if udp_match:
        return "udp", {"host": udp_match.group(1), "port": int(udp_match.group(2))}

    # HTTP/HTTPS URL
    if url.startswith("http://") or url.startswith("https://"):
        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        # Reconstruct base URL without query string
        base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

        params: dict[str, Any] = {"url": base_url}

        # Parse query parameters
        if "batch" in query:
            params["batch_size"] = int(query["batch"][0])
        if "timeout" in query:
            params["batch_timeout"] = float(query["timeout"][0])
        if "format" in query:
            fmt = query["format"][0].lower()
            params["format"] = HttpBatchFormat(fmt)
        if "dead_letter" in query:
            params["dead_letter_path"] = query["dead_letter"][0]
        if "retries" in query:
            params["max_retries"] = int(query["retries"][0])

        return "http", params

    # Treat as file path
    return "file", {"path": url}


def create_sink(
    output: str | None = None,
    buffered: bool = True,
    buffer_size: int = 10000,
    file_append: bool = True,
    http_headers: dict[str, str] | None = None,
) -> Sink:
    """Create a sink from an output specification.

    Args:
        output: Output URL/path (None or "stdout" for stdout)
        buffered: Whether to wrap in BufferedSink
        buffer_size: Buffer size for BufferedSink
        file_append: Whether to append to files (vs truncate)
        http_headers: Custom headers for HTTP sink
    """
    if output is None:
        output = "stdout"

    sink_type, params = parse_output_url(output)

    sink: Sink
    if sink_type == "stdout":
        sink = StdoutSink()
    elif sink_type == "file":
        sink = FileSink(params["path"], append=file_append)  # type: ignore
    elif sink_type == "tcp":
        sink = TcpSink(host=params["host"], port=params["port"])  # type: ignore
    elif sink_type == "udp":
        sink = UdpSink(host=params["host"], port=params["port"])  # type: ignore
    elif sink_type == "http":
        # Build config from URL params
        config = HttpSinkConfig(
            url=params["url"],
            batch_size=params.get("batch_size", 100),
            batch_timeout=params.get("batch_timeout", 5.0),
            format=params.get("format", HttpBatchFormat.JSON),
            headers=http_headers or {},
            dead_letter_path=params.get("dead_letter_path"),
            max_retries=params.get("max_retries", 3),
        )
        # HttpSink handles its own batching, skip BufferedSink
        return HttpSink(config)
    else:
        raise ValueError(f"Unknown sink type: {sink_type}")

    if buffered and sink_type != "stdout":
        sink = BufferedSink(sink, maxsize=buffer_size)

    return sink

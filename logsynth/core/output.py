"""Output sinks for log emission."""

from __future__ import annotations

import queue
import re
import socket
import sys
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TextIO


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

    def __enter__(self) -> "Sink":
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


def parse_output_url(url: str) -> tuple[str, dict[str, str | int]]:
    """Parse an output URL into type and parameters.

    Supported formats:
    - stdout (or -)
    - /path/to/file
    - tcp://host:port
    - udp://host:port
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

    # Treat as file path
    return "file", {"path": url}


def create_sink(
    output: str | None = None,
    buffered: bool = True,
    buffer_size: int = 10000,
    file_append: bool = True,
) -> Sink:
    """Create a sink from an output specification.

    Args:
        output: Output URL/path (None or "stdout" for stdout)
        buffered: Whether to wrap in BufferedSink
        buffer_size: Buffer size for BufferedSink
        file_append: Whether to append to files (vs truncate)
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
    else:
        raise ValueError(f"Unknown sink type: {sink_type}")

    if buffered and sink_type != "stdout":
        sink = BufferedSink(sink, maxsize=buffer_size)

    return sink

"""Log file tailing with optional augmentation."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class AugmentConfig:
    """Configuration for log augmentation."""

    add_timestamp: bool = False
    timestamp_format: str = "%Y-%m-%dT%H:%M:%S.%fZ"
    add_hostname: bool = False
    hostname: str | None = None
    add_source: bool = False
    source_name: str | None = None
    wrap_json: bool = False
    json_message_key: str = "message"
    extra_fields: dict[str, str] | None = None


def augment_line(line: str, config: AugmentConfig) -> str:
    """Augment a log line with additional fields."""
    if config.wrap_json:
        # Wrap in JSON object
        obj: dict[str, str] = {}

        if config.add_timestamp:
            obj["timestamp"] = datetime.now(UTC).strftime(config.timestamp_format)

        if config.add_hostname:
            obj["hostname"] = config.hostname or os.uname().nodename

        if config.add_source:
            obj["source"] = config.source_name or "logsynth"

        if config.extra_fields:
            obj.update(config.extra_fields)

        obj[config.json_message_key] = line

        return json.dumps(obj)
    else:
        # Prepend fields as text
        parts: list[str] = []

        if config.add_timestamp:
            parts.append(datetime.now(UTC).strftime(config.timestamp_format))

        if config.add_hostname:
            parts.append(config.hostname or os.uname().nodename)

        if config.add_source:
            parts.append(config.source_name or "logsynth")

        if parts:
            return " ".join(parts) + " " + line
        return line


class LogTailer:
    """Tails a log file and forwards new lines."""

    def __init__(
        self,
        path: Path | str,
        augment: AugmentConfig | None = None,
        poll_interval: float = 0.1,
        from_end: bool = True,
    ) -> None:
        """
        Initialize the log tailer.

        Args:
            path: Path to log file to tail
            augment: Optional augmentation config
            poll_interval: Seconds between file checks
            from_end: Start from end of file (True) or beginning (False)
        """
        self.path = Path(path)
        self.augment = augment
        self.poll_interval = poll_interval
        self.from_end = from_end
        self._stopped = False
        self._position = 0
        self._inode: int | None = None

    def stop(self) -> None:
        """Stop tailing."""
        self._stopped = True

    def _check_rotation(self) -> bool:
        """Check if file was rotated (different inode)."""
        try:
            stat = self.path.stat()
            if self._inode is not None and stat.st_ino != self._inode:
                return True
            self._inode = stat.st_ino
            return False
        except FileNotFoundError:
            return True

    def tail(
        self,
        write: Callable[[str], None],
        on_line: Callable[[str], None] | None = None,
    ) -> int:
        """
        Tail the log file and forward lines.

        Args:
            write: Function to write each line
            on_line: Optional callback for each raw line

        Returns:
            Number of lines forwarded
        """
        self._stopped = False
        forwarded = 0

        # Wait for file to exist
        while not self.path.exists() and not self._stopped:
            time.sleep(self.poll_interval)

        if self._stopped:
            return 0

        # Initialize position
        stat = self.path.stat()
        self._inode = stat.st_ino
        self._position = stat.st_size if self.from_end else 0

        while not self._stopped:
            try:
                # Check for rotation
                if self._check_rotation():
                    self._position = 0
                    if not self.path.exists():
                        time.sleep(self.poll_interval)
                        continue
                    self._inode = self.path.stat().st_ino

                # Check file size
                current_size = self.path.stat().st_size

                if current_size < self._position:
                    # File was truncated
                    self._position = 0

                if current_size > self._position:
                    # New data available
                    with open(self.path, encoding="utf-8", errors="ignore") as f:
                        f.seek(self._position)
                        for line in f:
                            if self._stopped:
                                break

                            line = line.rstrip("\n\r")
                            if not line:
                                continue

                            if on_line:
                                on_line(line)

                            # Apply augmentation
                            if self.augment:
                                line = augment_line(line, self.augment)

                            write(line)
                            forwarded += 1

                        self._position = f.tell()

                time.sleep(self.poll_interval)

            except FileNotFoundError:
                # File deleted, wait for it to reappear
                time.sleep(self.poll_interval)
            except Exception:
                # Other errors, continue trying
                time.sleep(self.poll_interval)

        return forwarded


def watch_file(
    path: Path | str,
    write: Callable[[str], None],
    augment: AugmentConfig | None = None,
    from_end: bool = True,
    poll_interval: float = 0.1,
) -> LogTailer:
    """
    Start watching a log file.

    Args:
        path: Path to log file
        write: Function to write each line
        augment: Optional augmentation config
        from_end: Start from end of file
        poll_interval: Seconds between checks

    Returns:
        LogTailer instance (call .stop() to stop)
    """
    tailer = LogTailer(
        path=path,
        augment=augment,
        poll_interval=poll_interval,
        from_end=from_end,
    )
    return tailer

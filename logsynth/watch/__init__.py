"""Watch module for LogSynth - tail and augment log files."""

from logsynth.watch.tailer import LogTailer, watch_file

__all__ = ["LogTailer", "watch_file"]

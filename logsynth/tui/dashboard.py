"""Live dashboard display using Rich."""

from __future__ import annotations

import sys

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table

from logsynth.tui.stats import StatsCollector


def _format_duration(seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _format_number(n: int) -> str:
    """Format number with thousands separator."""
    return f"{n:,}"


def _format_rate(rate: float) -> str:
    """Format rate as X.X/s."""
    if rate >= 1000:
        return f"{rate / 1000:.1f}k/s"
    return f"{rate:.1f}/s"


class Dashboard:
    """Live TUI dashboard for log generation stats."""

    def __init__(
        self,
        stats: StatsCollector,
        target_count: int | None = None,
        target_duration: float | None = None,
        console: Console | None = None,
    ) -> None:
        self.stats = stats
        self.target_count = target_count
        self.target_duration = target_duration
        self.console = console or Console()
        self._live: Live | None = None

    def _build_header(self) -> Table:
        """Build the header section with elapsed/target time."""
        elapsed = self.stats.elapsed
        total_emitted, total_errors, total_rate = self.stats.get_totals()

        header = Table.grid(padding=(0, 2))
        header.add_column(justify="left")
        header.add_column(justify="right")

        # Time info
        elapsed_str = f"Elapsed: [cyan]{_format_duration(elapsed)}[/cyan]"
        if self.target_duration:
            target_str = f"Target: [dim]{_format_duration(self.target_duration)}[/dim]"
            header.add_row(elapsed_str, target_str)
        elif self.target_count:
            target_str = f"Target: [dim]{_format_number(self.target_count)} lines[/dim]"
            header.add_row(elapsed_str, target_str)
        else:
            header.add_row(elapsed_str, "")

        return header

    def _build_progress(self) -> Progress | None:
        """Build progress bar if we have a target."""
        total_emitted, _, _ = self.stats.get_totals()
        elapsed = self.stats.elapsed

        if self.target_count:
            progress = Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(bar_width=40),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                console=self.console,
                expand=True,
            )
            task = progress.add_task("Progress", total=self.target_count)
            progress.update(task, completed=total_emitted)
            return progress
        elif self.target_duration:
            progress = Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(bar_width=40),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                console=self.console,
                expand=True,
            )
            task = progress.add_task("Progress", total=self.target_duration)
            progress.update(task, completed=min(elapsed, self.target_duration))
            return progress

        return None

    def _build_stats_table(self) -> Table:
        """Build the main stats table."""
        table = Table(
            show_header=True,
            header_style="bold",
            expand=True,
            box=None,
        )
        table.add_column("Stream", style="cyan", min_width=15)
        table.add_column("Rate", justify="right", min_width=10)
        table.add_column("Emitted", justify="right", min_width=12)
        table.add_column("Errors", justify="right", min_width=8)

        snapshot = self.stats.get_snapshot()

        # Sort streams by name
        for name in sorted(snapshot.keys()):
            stream_stats = snapshot[name]
            error_style = "red" if stream_stats.errors > 0 else "dim"
            table.add_row(
                name,
                _format_rate(stream_stats.rate),
                _format_number(stream_stats.emitted),
                f"[{error_style}]{stream_stats.errors}[/{error_style}]",
            )

        # Add separator and totals if multiple streams
        if len(snapshot) > 1:
            table.add_row("", "", "", "")
            total_emitted, total_errors, total_rate = self.stats.get_totals()
            error_style = "red" if total_errors > 0 else "dim"
            table.add_row(
                "[bold]Total[/bold]",
                f"[bold]{_format_rate(total_rate)}[/bold]",
                f"[bold]{_format_number(total_emitted)}[/bold]",
                f"[bold {error_style}]{total_errors}[/bold {error_style}]",
            )

        return table

    def render(self) -> Panel:
        """Render the complete dashboard."""
        components: list = []

        # Header with time info
        components.append(self._build_header())

        # Progress bar (if applicable)
        progress = self._build_progress()
        if progress:
            components.append(progress)

        # Stats table
        components.append(self._build_stats_table())

        return Panel(
            Group(*components),
            title="[bold]LogSynth Dashboard[/bold]",
            border_style="blue",
        )

    def start(self) -> Live:
        """Start the live display and return the Live context."""
        self._live = Live(
            self.render(),
            console=self.console,
            refresh_per_second=4,
            transient=True,
        )
        self._live.start()
        return self._live

    def update(self) -> None:
        """Update the live display."""
        if self._live:
            self._live.update(self.render())

    def stop(self) -> None:
        """Stop the live display."""
        if self._live:
            self._live.stop()
            self._live = None

    def print_final_stats(self) -> None:
        """Print final statistics after dashboard closes."""
        total_emitted, total_errors, total_rate = self.stats.get_totals()
        elapsed = self.stats.elapsed

        self.console.print()
        self.console.print(
            f"[green]Emitted {_format_number(total_emitted)} log lines[/green] "
            f"in {_format_duration(elapsed)} "
            f"([cyan]{_format_rate(total_rate)}[/cyan] avg)"
        )

        if total_errors > 0:
            self.console.print(f"[red]Errors: {total_errors}[/red]")

        # Per-stream breakdown if multiple
        snapshot = self.stats.get_snapshot()
        if len(snapshot) > 1:
            for name in sorted(snapshot.keys()):
                s = snapshot[name]
                self.console.print(f"  {name}: {_format_number(s.emitted)}")


def is_tty() -> bool:
    """Check if stdout is a TTY (interactive terminal)."""
    return sys.stdout.isatty()

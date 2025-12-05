"""LogSynth CLI - main entry point."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from logsynth import __version__
from logsynth.config import PRESETS_DIR, get_defaults
from logsynth.core.corruptor import create_corruptor
from logsynth.core.generator import create_generator, get_preset_path, list_presets
from logsynth.core.output import create_sink
from logsynth.core.parallel import run_parallel_streams
from logsynth.core.rate_control import (
    RateController,
    parse_burst_pattern,
    run_with_burst,
    run_with_count,
    run_with_duration,
)
from logsynth.utils.schema import ValidationError, load_template

app = typer.Typer(
    name="logsynth",
    help="Flexible synthetic log generator with YAML templates.",
    no_args_is_help=True,
)
presets_app = typer.Typer(help="Manage preset templates.")
app.add_typer(presets_app, name="presets")

console = Console()
err_console = Console(stderr=True)


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"logsynth {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        Optional[bool],
        typer.Option("--version", "-V", callback=version_callback, is_eager=True),
    ] = None,
) -> None:
    """LogSynth - Flexible synthetic log generator."""
    pass


def _resolve_template_source(
    templates: list[str] | None,
    template_path: str | None,
) -> list[str]:
    """Resolve template sources from CLI arguments."""
    sources = []

    if template_path:
        sources.append(template_path)

    if templates:
        for t in templates:
            # Check if it's a preset name or file path
            preset_path = get_preset_path(t)
            if preset_path:
                sources.append(str(preset_path))
            elif Path(t).exists():
                sources.append(t)
            else:
                # Try as preset name anyway - will error with helpful message
                sources.append(t)

    if not sources:
        err_console.print("[red]Error:[/red] No template specified. Use a preset name or --template")
        raise typer.Exit(1)

    return sources


@app.command()
def run(
    templates: Annotated[
        Optional[list[str]],
        typer.Argument(help="Preset name(s) or template file path(s)"),
    ] = None,
    template: Annotated[
        Optional[str],
        typer.Option("--template", "-t", help="Path to template YAML file"),
    ] = None,
    rate: Annotated[
        Optional[float],
        typer.Option("--rate", "-r", help="Lines per second"),
    ] = None,
    duration: Annotated[
        Optional[str],
        typer.Option("--duration", "-d", help="Duration (e.g., 30s, 5m, 1h)"),
    ] = None,
    count: Annotated[
        Optional[int],
        typer.Option("--count", "-c", help="Number of lines to generate"),
    ] = None,
    output: Annotated[
        Optional[str],
        typer.Option("--output", "-o", help="Output: file path, tcp://host:port, udp://host:port"),
    ] = None,
    corrupt: Annotated[
        float,
        typer.Option("--corrupt", help="Corruption percentage (0-100)"),
    ] = 0.0,
    seed: Annotated[
        Optional[int],
        typer.Option("--seed", "-s", help="Random seed for reproducibility"),
    ] = None,
    format_override: Annotated[
        Optional[str],
        typer.Option("--format", "-f", help="Output format override: plain, json, logfmt"),
    ] = None,
    burst: Annotated[
        Optional[str],
        typer.Option("--burst", "-b", help="Burst pattern (e.g., 100:5s,10:25s)"),
    ] = None,
    preview: Annotated[
        bool,
        typer.Option("--preview", "-p", help="Show sample line and exit"),
    ] = False,
) -> None:
    """Generate synthetic logs from templates."""
    # Get defaults
    defaults = get_defaults()
    actual_rate = rate if rate is not None else defaults.rate

    # Resolve template sources
    sources = _resolve_template_source(templates, template)

    # Handle parallel streams (multiple templates)
    if len(sources) > 1:
        sink = create_sink(output)
        try:
            if burst:
                err_console.print("[red]Error:[/red] --burst not supported with parallel streams")
                raise typer.Exit(1)

            results = run_parallel_streams(
                sources=sources,
                sink=sink,
                rate=actual_rate,
                duration=duration,
                count=count or (1000 if not duration else None),
                format_override=format_override,
                seed=seed,
            )

            total = sum(results.values())
            console.print(f"\n[green]Emitted {total} log lines[/green]")
            for name, emitted in results.items():
                console.print(f"  {name}: {emitted}")
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted[/yellow]")
        finally:
            sink.close()
        return

    # Single template mode
    source = sources[0]

    try:
        generator = create_generator(source, format_override, seed)
    except FileNotFoundError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except ValidationError as e:
        err_console.print(f"[red]Validation Error:[/red] {e.message}")
        for error in e.errors:
            err_console.print(f"  - {error}")
        raise typer.Exit(1)

    # Preview mode
    if preview:
        console.print(Panel(generator.preview(), title=f"Preview: {generator.template.name}"))
        raise typer.Exit()

    # Create corruptor if needed
    corruptor = create_corruptor(corrupt)

    # Create output sink
    sink = create_sink(output)

    # Create generate function (with optional corruption)
    def generate() -> str:
        line = generator.generate()
        if corruptor:
            line = corruptor.maybe_corrupt(line)
        return line

    # Write function
    def write(line: str) -> None:
        sink.write(line)

    try:
        # Determine run mode
        if burst:
            if not duration:
                err_console.print("[red]Error:[/red] --burst requires --duration")
                raise typer.Exit(1)
            segments = parse_burst_pattern(burst)
            emitted = run_with_burst(segments, duration, generate, write)
        elif duration:
            emitted = run_with_duration(actual_rate, duration, generate, write)
        elif count:
            emitted = run_with_count(actual_rate, count, generate, write)
        else:
            # Default: run indefinitely until Ctrl+C (using large duration)
            emitted = run_with_duration(actual_rate, "24h", generate, write)

        console.print(f"\n[green]Emitted {emitted} log lines[/green]", highlight=False)

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
    finally:
        sink.close()


@app.command()
def validate(
    template_path: Annotated[str, typer.Argument(help="Path to template YAML file")],
) -> None:
    """Validate a template YAML file."""
    path = Path(template_path)

    if not path.exists():
        err_console.print(f"[red]Error:[/red] File not found: {template_path}")
        raise typer.Exit(1)

    try:
        template = load_template(path)
        console.print(f"[green]✓[/green] Template '{template.name}' is valid")
        console.print(f"  Format: {template.format}")
        console.print(f"  Fields: {', '.join(template.field_names)}")
    except ValidationError as e:
        err_console.print(f"[red]✗[/red] Validation failed: {e.message}")
        for error in e.errors:
            err_console.print(f"  - {error}")
        raise typer.Exit(1)


@app.command()
def prompt(
    description: Annotated[str, typer.Argument(help="Natural language description of logs")],
    rate: Annotated[
        Optional[float],
        typer.Option("--rate", "-r", help="Lines per second"),
    ] = None,
    duration: Annotated[
        Optional[str],
        typer.Option("--duration", "-d", help="Duration (e.g., 30s, 5m, 1h)"),
    ] = None,
    count: Annotated[
        Optional[int],
        typer.Option("--count", "-c", help="Number of lines to generate"),
    ] = None,
    save_only: Annotated[
        bool,
        typer.Option("--save-only", help="Save template without running"),
    ] = False,
    edit: Annotated[
        bool,
        typer.Option("--edit", "-e", help="Open generated template in $EDITOR"),
    ] = False,
    output: Annotated[
        Optional[str],
        typer.Option("--output", "-o", help="Output destination"),
    ] = None,
) -> None:
    """Generate a template from natural language using LLM."""
    # Import here to avoid loading LLM dependencies unless needed
    try:
        from logsynth.llm.prompt2template import generate_template
    except ImportError as e:
        err_console.print(f"[red]Error:[/red] LLM dependencies not available: {e}")
        raise typer.Exit(1)

    console.print(f"[cyan]Generating template from:[/cyan] {description}")

    try:
        template_path = generate_template(description)
        console.print(f"[green]✓[/green] Template saved to: {template_path}")

        # Open in editor if requested
        if edit:
            import os
            import subprocess

            editor = os.environ.get("EDITOR", os.environ.get("VISUAL", "vi"))
            console.print(f"[cyan]Opening in {editor}...[/cyan]")
            subprocess.run([editor, str(template_path)])
            raise typer.Exit()

        if save_only:
            # Show the template
            with open(template_path) as f:
                content = f.read()
            syntax = Syntax(content, "yaml", theme="monokai")
            console.print(Panel(syntax, title="Generated Template"))
            raise typer.Exit()

        # Run the generated template
        defaults = get_defaults()
        actual_rate = rate if rate is not None else defaults.rate

        generator = create_generator(template_path)
        sink = create_sink(output)

        def generate_fn() -> str:
            return generator.generate()

        def write_fn(line: str) -> None:
            sink.write(line)

        try:
            if duration:
                emitted = run_with_duration(actual_rate, duration, generate_fn, write_fn)
            elif count:
                emitted = run_with_count(actual_rate, count, generate_fn, write_fn)
            else:
                # Default: 100 lines
                emitted = run_with_count(actual_rate, 100, generate_fn, write_fn)

            console.print(f"\n[green]Emitted {emitted} log lines[/green]")
        finally:
            sink.close()

    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@presets_app.command("list")
def presets_list() -> None:
    """List available preset templates."""
    presets = list_presets()

    if not presets:
        console.print("[yellow]No presets available[/yellow]")
        raise typer.Exit()

    console.print("[bold]Available Presets:[/bold]")
    for name in presets:
        preset_path = get_preset_path(name)
        if preset_path:
            template = load_template(preset_path)
            console.print(f"  [cyan]{name}[/cyan] - {template.format} format, {len(template.fields)} fields")


@presets_app.command("show")
def presets_show(
    name: Annotated[str, typer.Argument(help="Preset name")],
) -> None:
    """Show contents of a preset template."""
    preset_path = get_preset_path(name)

    if not preset_path:
        available = ", ".join(list_presets())
        err_console.print(f"[red]Error:[/red] Unknown preset '{name}'. Available: {available}")
        raise typer.Exit(1)

    with open(preset_path) as f:
        content = f.read()

    syntax = Syntax(content, "yaml", theme="monokai", line_numbers=True)
    console.print(Panel(syntax, title=f"Preset: {name}"))


if __name__ == "__main__":
    app()

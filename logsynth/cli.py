"""LogSynth CLI - main entry point."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from logsynth import __version__
from logsynth.config import (
    PROFILES_DIR,
    ProfileConfig,
    get_defaults,
    list_profiles,
    load_profile,
    save_profile,
)
from logsynth.core.corruptor import create_corruptor
from logsynth.core.generator import create_generator, get_preset_path, list_presets
from logsynth.core.output import create_sink
from logsynth.core.parallel import StreamConfig, parse_stream_config, run_parallel_streams
from logsynth.core.rate_control import (
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
profiles_app = typer.Typer(help="Manage configuration profiles.")
app.add_typer(profiles_app, name="profiles")

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
        bool | None,
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
        err_console.print(
            "[red]Error:[/red] No template specified. Use a preset name or --template"
        )
        raise typer.Exit(1)

    return sources


@app.command()
def run(
    templates: Annotated[
        list[str] | None,
        typer.Argument(help="Preset name(s) or template file path(s)"),
    ] = None,
    template: Annotated[
        str | None,
        typer.Option("--template", "-t", help="Path to template YAML file"),
    ] = None,
    rate: Annotated[
        float | None,
        typer.Option("--rate", "-r", help="Lines per second"),
    ] = None,
    duration: Annotated[
        str | None,
        typer.Option("--duration", "-d", help="Duration (e.g., 30s, 5m, 1h)"),
    ] = None,
    count: Annotated[
        int | None,
        typer.Option("--count", "-c", help="Number of lines to generate"),
    ] = None,
    output: Annotated[
        str | None,
        typer.Option("--output", "-o", help="Output: file path, tcp://host:port, udp://host:port"),
    ] = None,
    corrupt: Annotated[
        float | None,
        typer.Option("--corrupt", help="Corruption percentage (0-100)"),
    ] = None,
    seed: Annotated[
        int | None,
        typer.Option("--seed", "-s", help="Random seed for reproducibility"),
    ] = None,
    format_override: Annotated[
        str | None,
        typer.Option("--format", "-f", help="Output format override: plain, json, logfmt"),
    ] = None,
    burst: Annotated[
        str | None,
        typer.Option("--burst", "-b", help="Burst pattern (e.g., 100:5s,10:25s)"),
    ] = None,
    preview: Annotated[
        bool,
        typer.Option("--preview", "-p", help="Show sample line and exit"),
    ] = False,
    profile: Annotated[
        str | None,
        typer.Option("--profile", "-P", help="Configuration profile name"),
    ] = None,
    stream: Annotated[
        list[str] | None,
        typer.Option("--stream", "-S", help="Per-stream config: name:rate=X,format=Y"),
    ] = None,
    header: Annotated[
        list[str] | None,
        typer.Option("--header", "-H", help="HTTP header (key:value)"),
    ] = None,
) -> None:
    """Generate synthetic logs from templates."""
    # Get defaults and load profile if specified
    defaults = get_defaults()
    profile_config: ProfileConfig | None = None
    if profile:
        profile_config = load_profile(profile)
        if not profile_config:
            available = ", ".join(list_profiles()) if list_profiles() else "none"
            err_console.print(
                f"[red]Error:[/red] Unknown profile '{profile}'. Available: {available}"
            )
            raise typer.Exit(1)

    # Apply precedence: defaults < profile < CLI args
    def resolve(cli_val: any, profile_attr: str, default_val: any) -> any:
        """Resolve value with precedence: CLI > profile > defaults."""
        if cli_val is not None:
            return cli_val
        if profile_config and getattr(profile_config, profile_attr, None) is not None:
            return getattr(profile_config, profile_attr)
        return default_val

    actual_rate = resolve(rate, "rate", defaults.rate)
    actual_output = resolve(output, "output", None)
    actual_duration = resolve(duration, "duration", None)
    actual_count = resolve(count, "count", None)
    actual_corrupt = resolve(corrupt, "corrupt", 0.0)
    actual_format = resolve(format_override, "format", None)

    # Resolve template sources
    sources = _resolve_template_source(templates, template)

    # Parse stream configs if provided
    stream_configs: dict[str, StreamConfig] = {}
    if stream:
        for spec in stream:
            cfg = parse_stream_config(spec)
            stream_configs[cfg.name] = cfg

    # Parse HTTP headers if provided
    http_headers: dict[str, str] = {}
    if header:
        for h in header:
            if ":" in h:
                key, value = h.split(":", 1)
                http_headers[key.strip()] = value.strip()

    # Handle parallel streams (multiple templates)
    if len(sources) > 1:
        sink = create_sink(actual_output, http_headers=http_headers or None)
        try:
            if burst:
                err_console.print("[red]Error:[/red] --burst not supported with parallel streams")
                raise typer.Exit(1)

            results = run_parallel_streams(
                sources=sources,
                sink=sink,
                rate=actual_rate,
                duration=actual_duration,
                count=actual_count or (1000 if not actual_duration else None),
                format_override=actual_format,
                seed=seed,
                stream_configs=stream_configs if stream_configs else None,
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
        generator = create_generator(source, actual_format, seed)
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
    corruptor = create_corruptor(actual_corrupt)

    # Create output sink
    sink = create_sink(actual_output, http_headers=http_headers or None)

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
            if not actual_duration:
                err_console.print("[red]Error:[/red] --burst requires --duration")
                raise typer.Exit(1)
            segments = parse_burst_pattern(burst)
            emitted = run_with_burst(segments, actual_duration, generate, write)
        elif actual_duration:
            emitted = run_with_duration(actual_rate, actual_duration, generate, write)
        elif actual_count:
            emitted = run_with_count(actual_rate, actual_count, generate, write)
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
        float | None,
        typer.Option("--rate", "-r", help="Lines per second"),
    ] = None,
    duration: Annotated[
        str | None,
        typer.Option("--duration", "-d", help="Duration (e.g., 30s, 5m, 1h)"),
    ] = None,
    count: Annotated[
        int | None,
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
        str | None,
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
            info = f"{template.format} format, {len(template.fields)} fields"
            console.print(f"  [cyan]{name}[/cyan] - {info}")


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


# Profiles subcommands
@profiles_app.command("list")
def profiles_list_cmd() -> None:
    """List available configuration profiles."""
    profiles = list_profiles()

    if not profiles:
        console.print("[yellow]No profiles available[/yellow]")
        console.print(f"[dim]Create profiles in: {PROFILES_DIR}[/dim]")
        raise typer.Exit()

    console.print("[bold]Available Profiles:[/bold]")
    for name in profiles:
        profile_cfg = load_profile(name)
        if profile_cfg:
            attrs = []
            if profile_cfg.rate is not None:
                attrs.append(f"rate={profile_cfg.rate}")
            if profile_cfg.format is not None:
                attrs.append(f"format={profile_cfg.format}")
            if profile_cfg.duration is not None:
                attrs.append(f"duration={profile_cfg.duration}")
            if profile_cfg.count is not None:
                attrs.append(f"count={profile_cfg.count}")
            if profile_cfg.output is not None:
                attrs.append(f"output={profile_cfg.output}")
            if profile_cfg.corrupt is not None:
                attrs.append(f"corrupt={profile_cfg.corrupt}")
            attrs_str = ", ".join(attrs) if attrs else "empty"
            console.print(f"  [cyan]{name}[/cyan] - {attrs_str}")


@profiles_app.command("show")
def profiles_show(
    name: Annotated[str, typer.Argument(help="Profile name")],
) -> None:
    """Show contents of a configuration profile."""
    profile_path = PROFILES_DIR / f"{name}.yaml"

    if not profile_path.exists():
        available = ", ".join(list_profiles()) if list_profiles() else "none"
        err_console.print(f"[red]Error:[/red] Unknown profile '{name}'. Available: {available}")
        raise typer.Exit(1)

    with open(profile_path) as f:
        content = f.read()

    syntax = Syntax(content, "yaml", theme="monokai", line_numbers=True)
    console.print(Panel(syntax, title=f"Profile: {name}"))


@profiles_app.command("create")
def profiles_create(
    name: Annotated[str, typer.Argument(help="Profile name")],
    rate: Annotated[float | None, typer.Option("--rate", "-r", help="Lines per second")] = None,
    format_val: Annotated[str | None, typer.Option("--format", "-f", help="Output format")] = None,
    output: Annotated[str | None, typer.Option("--output", "-o", help="Output destination")] = None,
    duration: Annotated[str | None, typer.Option("--duration", "-d", help="Duration")] = None,
    count: Annotated[int | None, typer.Option("--count", "-c", help="Line count")] = None,
    corrupt: Annotated[float | None, typer.Option("--corrupt", help="Corruption %")] = None,
) -> None:
    """Create a new configuration profile."""
    profile = ProfileConfig(
        name=name,
        rate=rate,
        format=format_val,
        output=output,
        duration=duration,
        count=count,
        corrupt=corrupt,
    )
    path = save_profile(profile)
    console.print(f"[green]✓[/green] Profile '{name}' saved to: {path}")


if __name__ == "__main__":
    app()

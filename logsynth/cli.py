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
    parse_duration,
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
    live: Annotated[
        bool,
        typer.Option("--live", "-L", help="Show live dashboard with stats"),
    ] = False,
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

        # Check if live dashboard should be enabled
        use_dashboard = live and actual_output is None
        if live and actual_output:
            err_console.print("[yellow]Warning:[/yellow] --live ignored when output is not stdout")
            use_dashboard = False

        # Set up stats collector and dashboard if needed
        stats_collector = None
        dashboard = None
        if use_dashboard:
            from logsynth.tui import Dashboard, StatsCollector

            target_duration_secs = None
            if actual_duration:
                target_duration_secs = parse_duration(actual_duration)

            stats_collector = StatsCollector()
            # Register all streams
            for src in sources:
                name = Path(src).stem if Path(src).exists() else src
                stats_collector.register_stream(name)

            dashboard = Dashboard(
                stats=stats_collector,
                target_count=actual_count,
                target_duration=target_duration_secs,
                console=console,
            )

        try:
            if burst:
                err_console.print("[red]Error:[/red] --burst not supported with parallel streams")
                raise typer.Exit(1)

            # Start dashboard if enabled
            if dashboard:
                dashboard.start()

            results = run_parallel_streams(
                sources=sources,
                sink=sink,
                rate=actual_rate,
                duration=actual_duration,
                count=actual_count or (1000 if not actual_duration else None),
                format_override=actual_format,
                seed=seed,
                stream_configs=stream_configs if stream_configs else None,
                stats_collector=stats_collector,
            )

            # Stop dashboard and print final stats
            if dashboard:
                if stats_collector:
                    stats_collector.mark_done()
                dashboard.stop()
                dashboard.print_final_stats()
            else:
                total = sum(results.values())
                console.print(f"\n[green]Emitted {total} log lines[/green]")
                for name, emitted in results.items():
                    console.print(f"  {name}: {emitted}")
        except KeyboardInterrupt:
            if dashboard:
                if stats_collector:
                    stats_collector.mark_done()
                dashboard.stop()
                dashboard.print_final_stats()
            else:
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

    # Check if live dashboard should be enabled
    use_dashboard = live and actual_output is None  # Only for stdout
    if live and actual_output:
        err_console.print("[yellow]Warning:[/yellow] --live ignored when output is not stdout")
        use_dashboard = False

    # Create generate function (with optional corruption)
    def generate() -> str:
        line = generator.generate()
        if corruptor:
            line = corruptor.maybe_corrupt(line)
        return line

    # Set up stats collector and dashboard if needed
    stats_collector = None
    dashboard = None
    if use_dashboard:
        from logsynth.tui import Dashboard, StatsCollector

        # Parse duration to seconds for dashboard
        target_duration_secs = None
        if actual_duration:
            target_duration_secs = parse_duration(actual_duration)

        stats_collector = StatsCollector()
        stats_collector.register_stream(generator.template.name)
        dashboard = Dashboard(
            stats=stats_collector,
            target_count=actual_count,
            target_duration=target_duration_secs,
            console=console,
        )

    # Write function (with optional stats tracking)
    stream_name = generator.template.name

    def write(line: str) -> None:
        sink.write(line)
        if stats_collector:
            stats_collector.record_emit(stream_name)

    try:
        # Start dashboard if enabled
        if dashboard:
            dashboard.start()

        # Determine run mode
        if burst:
            if not actual_duration:
                if dashboard:
                    dashboard.stop()
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

        # Stop dashboard and print final stats
        if dashboard:
            if stats_collector:
                stats_collector.mark_done()
            dashboard.stop()
            dashboard.print_final_stats()
        else:
            console.print(f"\n[green]Emitted {emitted} log lines[/green]", highlight=False)

    except KeyboardInterrupt:
        if dashboard:
            if stats_collector:
                stats_collector.mark_done()
            dashboard.stop()
            dashboard.print_final_stats()
        else:
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


@app.command()
def infer(
    log_file: Annotated[str, typer.Argument(help="Path to log file to analyze")],
    output: Annotated[
        str | None,
        typer.Option("--output", "-o", help="Output file for generated template"),
    ] = None,
    name: Annotated[
        str | None,
        typer.Option("--name", "-n", help="Template name"),
    ] = None,
    lines: Annotated[
        int,
        typer.Option("--lines", "-l", help="Number of lines to analyze"),
    ] = 1000,
    format_hint: Annotated[
        str | None,
        typer.Option("--format", "-f", help="Format hint: json, logfmt, plain"),
    ] = None,
    preview: Annotated[
        bool,
        typer.Option("--preview", "-p", help="Preview detected fields without full template"),
    ] = False,
) -> None:
    """Infer a template schema from a sample log file."""
    from logsynth.infer import SchemaInferrer

    path = Path(log_file)
    if not path.exists():
        err_console.print(f"[red]Error:[/red] File not found: {log_file}")
        raise typer.Exit(1)

    try:
        inferrer = SchemaInferrer(max_lines=lines)
        template = inferrer.infer_from_file(path, name=name, format_hint=format_hint)

        if preview:
            # Show detected fields summary
            console.print(f"[bold]Detected Schema:[/bold] {template['name']}")
            console.print(f"  Format: {template['format']}")
            console.print(f"  Fields: {len(template['fields'])}")
            console.print()
            for field_name, config in template["fields"].items():
                field_type = config.get("type", "unknown")
                extra = ""
                if field_type == "choice":
                    values = config.get("values", [])
                    extra = f" ({len(values)} values)"
                elif field_type == "int":
                    extra = f" (min={config.get('min')}, max={config.get('max')})"
                elif field_type == "timestamp":
                    extra = f" (format={config.get('format', 'auto')})"
                console.print(f"  [cyan]{field_name}[/cyan]: {field_type}{extra}")
            raise typer.Exit()

        # Generate YAML
        import yaml

        yaml_content = yaml.dump(
            template,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
            width=120,
        )

        if output:
            output_path = Path(output)
            output_path.write_text(yaml_content)
            console.print(f"[green]✓[/green] Template saved to: {output_path}")
        else:
            syntax = Syntax(yaml_content, "yaml", theme="monokai")
            console.print(Panel(syntax, title=f"Inferred Template: {template['name']}"))

    except typer.Exit:
        raise
    except FileNotFoundError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except ValueError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def replay(
    log_file: Annotated[str, typer.Argument(help="Path to log file to replay")],
    output: Annotated[
        str | None,
        typer.Option("--output", "-o", help="Output destination (file, tcp://, http://)"),
    ] = None,
    speed: Annotated[
        float,
        typer.Option("--speed", "-s", help="Playback speed multiplier (1.0 = real-time)"),
    ] = 1.0,
    skip_gaps: Annotated[
        float | None,
        typer.Option("--skip-gaps", help="Skip gaps larger than N seconds"),
    ] = 60.0,
    max_lines: Annotated[
        int | None,
        typer.Option("--max-lines", "-n", help="Maximum lines to replay"),
    ] = None,
    header: Annotated[
        list[str] | None,
        typer.Option("--header", "-H", help="HTTP header (key:value)"),
    ] = None,
) -> None:
    """Replay a log file with original timing patterns."""
    from logsynth.replay import replay_file

    path = Path(log_file)
    if not path.exists():
        err_console.print(f"[red]Error:[/red] File not found: {log_file}")
        raise typer.Exit(1)

    # Parse HTTP headers
    http_headers: dict[str, str] = {}
    if header:
        for h in header:
            if ":" in h:
                key, value = h.split(":", 1)
                http_headers[key.strip()] = value.strip()

    sink = create_sink(output, http_headers=http_headers or None)

    console.print(f"[cyan]Replaying:[/cyan] {log_file}")
    console.print(f"  Speed: {speed}x")
    if skip_gaps:
        console.print(f"  Skip gaps > {skip_gaps}s")

    try:
        replayed = replay_file(
            path=path,
            write=sink.write,
            speed=speed,
            skip_gaps=skip_gaps,
            max_lines=max_lines,
        )
        console.print(f"\n[green]Replayed {replayed} log lines[/green]")
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
    finally:
        sink.close()


@app.command()
def watch(
    log_file: Annotated[str, typer.Argument(help="Path to log file to watch")],
    output: Annotated[
        str | None,
        typer.Option("--output", "-o", help="Output destination (file, tcp://, http://)"),
    ] = None,
    from_start: Annotated[
        bool,
        typer.Option("--from-start", help="Start from beginning of file"),
    ] = False,
    add_timestamp: Annotated[
        bool,
        typer.Option("--add-timestamp", help="Add timestamp to each line"),
    ] = False,
    add_hostname: Annotated[
        bool,
        typer.Option("--add-hostname", help="Add hostname to each line"),
    ] = False,
    add_source: Annotated[
        bool,
        typer.Option("--add-source", help="Add source name to each line"),
    ] = False,
    source_name: Annotated[
        str | None,
        typer.Option("--source-name", help="Source name for --add-source"),
    ] = None,
    wrap_json: Annotated[
        bool,
        typer.Option("--wrap-json", help="Wrap lines in JSON object"),
    ] = False,
    header: Annotated[
        list[str] | None,
        typer.Option("--header", "-H", help="HTTP header (key:value)"),
    ] = None,
) -> None:
    """Watch a log file and forward new lines (like tail -f)."""
    from logsynth.watch import LogTailer
    from logsynth.watch.tailer import AugmentConfig

    path = Path(log_file)

    # Parse HTTP headers
    http_headers: dict[str, str] = {}
    if header:
        for h in header:
            if ":" in h:
                key, value = h.split(":", 1)
                http_headers[key.strip()] = value.strip()

    sink = create_sink(output, http_headers=http_headers or None)

    # Build augment config if any augmentation is requested
    augment = None
    if add_timestamp or add_hostname or add_source or wrap_json:
        augment = AugmentConfig(
            add_timestamp=add_timestamp,
            add_hostname=add_hostname,
            add_source=add_source,
            source_name=source_name or path.name,
            wrap_json=wrap_json,
        )

    tailer = LogTailer(
        path=path,
        augment=augment,
        from_end=not from_start,
    )

    console.print(f"[cyan]Watching:[/cyan] {log_file}")
    if augment:
        augments = []
        if add_timestamp:
            augments.append("timestamp")
        if add_hostname:
            augments.append("hostname")
        if add_source:
            augments.append(f"source={source_name or path.name}")
        if wrap_json:
            augments.append("json")
        console.print(f"  Augment: {', '.join(augments)}")
    console.print("[dim]Press Ctrl+C to stop[/dim]")

    try:
        forwarded = tailer.tail(write=sink.write)
        console.print(f"\n[green]Forwarded {forwarded} log lines[/green]")
    except KeyboardInterrupt:
        tailer.stop()
        console.print("\n[yellow]Stopped[/yellow]")
    finally:
        sink.close()


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

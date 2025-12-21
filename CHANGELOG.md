# Changelog

All notable changes to LogSynth will be documented in this file.

## [0.3.1] - 2025-12-21

### Fixed
- TUI dashboard now updates properly during parallel stream execution
- Dashboard display no longer prints multiple copies (uses NullSink to prevent stdout interference)
- CLI tests fixed for ANSI escape code handling in CI environments

## [0.3.0] - 2025-12-21

### Added
- **Replay mode**: Replay logs with original timing patterns
  - `logsynth replay access.log` - Replay with real timestamps
  - `--speed N` - Playback speed multiplier (2.0 = 2x faster)
  - `--skip-gaps N` - Skip gaps larger than N seconds
  - Supports ISO8601, CLF (nginx/apache), syslog timestamp formats
- **Watch mode**: Tail log files and forward to outputs
  - `logsynth watch /var/log/app.log` - Like tail -f
  - `--output http://...` - Forward to HTTP endpoint
  - `--add-timestamp`, `--add-hostname`, `--add-source` - Augment lines
  - `--wrap-json` - Wrap lines in JSON objects
  - Handles log rotation automatically
- **TUI dashboard**: Real-time stats display during log generation
  - `--live` / `-L` flag to enable dashboard
  - Shows elapsed time, progress bar (for count/duration targets)
  - Per-stream stats: rate, emitted count, errors
  - Works with single and parallel streams
  - Final summary with average rate
- **Schema inference**: Auto-generate templates from sample log files
  - `logsynth infer sample.log` - Analyze logs and output YAML template
  - `--output FILE` - Save template to file
  - `--preview` - Show detected fields summary without full template
  - `--name NAME` - Set custom template name
  - `--lines N` - Number of lines to analyze (default: 1000)
  - `--format` - Force format hint (json/logfmt/plain)
- **Smart field detection**:
  - Timestamps: ISO8601, CLF (nginx/apache), syslog, epoch
  - Network: IPv4, IPv6 addresses
  - Identifiers: UUIDs, hex hashes
  - HTTP: methods, status codes, URL paths
  - Logging: log levels (DEBUG/INFO/WARN/ERROR/etc.)
  - Numbers: integers with min/max, floats with precision
  - Choice fields with auto-calculated weights
- **Format auto-detection**: JSON, logfmt, or plain text
- **Semantic field naming**: Detected types get meaningful names (ip, timestamp, method, level, status)
- 95 new tests (230 total)

## [0.2.1] - 2025-12-05

### Added
- **HTTP output sink**: POST logs to HTTP/HTTPS endpoints
  - Batching: configurable batch size and timeout
  - Retries: exponential backoff on 5xx/429/connection errors
  - Formats: JSON array, NDJSON, or plain text
  - Headers: `--header` CLI option for custom headers
  - Dead-letter: failed batches saved to JSONL file for debugging
  - URL params: `?batch=N&timeout=T&format=json&retries=N`

## [0.2.0] - 2025-12-05

### Added
- **Configuration profiles**: Named sets of defaults stored in `~/.config/logsynth/profiles/`
  - `logsynth profiles list` - List available profiles
  - `logsynth profiles show <name>` - Show profile contents
  - `logsynth profiles create <name> --rate X --format Y` - Create profiles
  - `logsynth run nginx --profile high-volume` - Use profiles
- **Plugin system**: Custom field types from `~/.config/logsynth/plugins/`
  - Load Python files with `@register("type")` decorated generators
  - Plugins loaded automatically on startup
- **Jinja2 templating**: Use `{{ field }}` and `{% if %}` syntax in patterns
  - Auto-detection: plain `$field` or Jinja2 `{{ field }}` syntax
  - Supports conditionals, loops, and filters
- **Conditional field generation**: `when:` clause for fields
  - Example: `when: "level == 'ERROR'"` - field only generated when condition is true
  - Automatic dependency ordering via topological sort
- **Per-stream rate syntax**: Different rates for parallel streams
  - `--stream nginx:rate=50 --stream redis:rate=10`
  - Per-stream format override: `--stream nginx:format=json`
- **Docker support**: Multi-stage Dockerfile for minimal image size
  - `docker build -t logsynth .`
  - `docker run --rm logsynth run nginx --count 100`
- **Example templates**: Comprehensive examples in `examples/` directory
  - Jinja2 conditional templates
  - Custom plugin examples
  - Profile configurations
  - Per-stream rate scripts
- **CLI integration tests**: 24 new tests for CLI commands (106 total)

## [0.1.1] - 2025-12-05

### Added
- 16 new preset templates:
  - Web servers: apache, nginx-error, haproxy
  - Databases: postgres, mysql, mongodb
  - Infrastructure: kubernetes, docker, terraform
  - Security: auth, sshd, firewall, audit
  - Applications: java, python, nodejs
- Total presets now: 19

## [0.1.0] - 2025-12-05

### Added
- Initial release
- YAML template engine with pattern substitution
- Field types: timestamp, choice, int, float, string, uuid, ip, sequence, literal
- Rate-controlled emission (duration and count modes)
- Output formats: plain, json, logfmt
- Output sinks: stdout, file, TCP, UDP
- BufferedSink for non-blocking output
- Corruption engine with 7 mutation types
- Built-in presets: nginx, redis, systemd

## [0.1.1] - 2025-12-05

### Added
- 16 new preset templates:
  - Web servers: apache, nginx-error, haproxy
  - Databases: postgres, mysql, mongodb
  - Infrastructure: kubernetes, docker, terraform
  - Security: auth, sshd, firewall, audit
  - Applications: java, python, nodejs
- Total presets now: 19
- LLM-powered template generation (OpenAI-compatible API)
- Parallel stream support
- Burst pattern support
- Preview mode
- Editor integration for generated templates
- CLI with Rich formatting
- 82 unit tests

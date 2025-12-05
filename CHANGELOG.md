# Changelog

All notable changes to LogSynth will be documented in this file.

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

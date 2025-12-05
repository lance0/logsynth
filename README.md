# LogSynth

Flexible synthetic log generator with YAML templates, rate control, and LLM-powered template synthesis.

## Installation

```bash
pip install logsynth
```

Or from source:

```bash
git clone https://github.com/yourname/logsynth.git
cd logsynth
pip install -e .
```

## Quick Start

```bash
# Generate nginx-style logs at 20 lines/sec for 30 seconds
logsynth run nginx --rate 20 --duration 30s

# Generate 100 redis logs
logsynth run redis --count 100

# Preview what a template generates
logsynth run nginx --preview

# Use JSON output format
logsynth run nginx --count 10 --format json
```

## Features

- **YAML-driven templates** - Define log patterns with field placeholders
- **Multiple field types** - timestamp, choice, int, float, string, uuid, ip, sequence, literal
- **Rate control** - Duration or count-based emission with fractional rates
- **Multiple formats** - Plain text, JSON, or logfmt output
- **Corruption injection** - Introduce malformed logs for testing error handling
- **Output sinks** - stdout, files, TCP, or UDP
- **LLM template generation** - Generate templates from natural language descriptions
- **Built-in presets** - 19 presets for web servers, databases, infrastructure, security, and applications
- **Parallel streams** - Run multiple templates concurrently
- **Burst patterns** - Simulate high/low traffic patterns

## CLI Reference

### Run Command

Generate logs from templates:

```bash
# Basic usage with preset
logsynth run <preset> [options]

# With custom template
logsynth run --template my-template.yaml [options]

# Parallel streams (multiple presets)
logsynth run nginx redis --rate 20 --duration 1m
```

Options:
- `--rate`, `-r` - Lines per second (default: 10)
- `--duration`, `-d` - Run duration (e.g., 30s, 5m, 1h)
- `--count`, `-c` - Number of lines to generate
- `--output`, `-o` - Output destination (file, tcp://host:port, udp://host:port)
- `--format`, `-f` - Output format override (plain, json, logfmt)
- `--corrupt` - Corruption percentage (0-100)
- `--seed`, `-s` - Random seed for reproducibility
- `--burst`, `-b` - Burst pattern (e.g., 100:5s,10:25s)
- `--preview`, `-p` - Show sample line and exit

### Preset Commands

```bash
# List available presets
logsynth presets list

# Show preset contents
logsynth presets show nginx
```

### Validate Command

```bash
# Validate a template file
logsynth validate my-template.yaml
```

### Prompt Command (LLM)

Generate templates from natural language:

```bash
# Generate and run immediately
logsynth prompt "nginx access logs with authentication failures" --duration 30s

# Generate and save only
logsynth prompt "database connection timeout errors" --save-only

# Generate and open in editor
logsynth prompt "kubernetes pod lifecycle events" --edit
```

## Template Format

Templates are YAML files with this structure:

```yaml
name: my-template
format: plain  # or json, logfmt
pattern: |
  [$ts] $level $message

fields:
  ts:
    type: timestamp
    step: 1s
    jitter: 100ms
    format: "%Y-%m-%d %H:%M:%S"
    tz: UTC

  level:
    type: choice
    values: [INFO, WARN, ERROR]
    weights: [0.8, 0.15, 0.05]

  message:
    type: choice
    values:
      - "Request processed successfully"
      - "Connection timeout"
      - "Authentication failed"
```

## Field Types

### timestamp
Generates timestamps with configurable step and jitter:
```yaml
ts:
  type: timestamp
  step: 1s          # Time between entries
  jitter: 100ms     # Random variance
  format: "%Y-%m-%d %H:%M:%S"
  tz: America/New_York  # Timezone (default: UTC)
  start: "2025-01-01T00:00:00"  # Optional start time
```

### choice
Random selection from a list with optional weights:
```yaml
method:
  type: choice
  values: [GET, POST, PUT, DELETE]
  weights: [0.7, 0.2, 0.05, 0.05]
```

### int
Random integer within a range:
```yaml
status:
  type: int
  min: 200
  max: 599
```

### float
Random float with configurable precision:
```yaml
latency:
  type: float
  min: 0.1
  max: 500.0
  precision: 2
```

### string
Random selection from string values:
```yaml
user:
  type: string
  values: [alice, bob, charlie]
```

### uuid
Random UUID generation:
```yaml
request_id:
  type: uuid
  uppercase: false
```

### ip
Random IP address, optionally from CIDR range:
```yaml
client_ip:
  type: ip
  cidr: 10.0.0.0/8   # Optional, restricts range
  ipv6: false
```

### sequence
Sequential integers:
```yaml
line_num:
  type: sequence
  start: 1
  step: 1
```

### literal
Constant value:
```yaml
version:
  type: literal
  value: "1.0.0"
```

## Output Formats

### Plain (default)
Uses pattern substitution:
```
[2025-01-15 10:30:00] INFO Request processed successfully
```

### JSON
Structured JSON output:
```json
{"ts": "2025-01-15 10:30:00", "level": "INFO", "message": "Request processed successfully"}
```

### Logfmt
Key=value pairs:
```
ts="2025-01-15 10:30:00" level=INFO message="Request processed successfully"
```

## Output Destinations

```bash
# stdout (default)
logsynth run nginx --count 10

# File
logsynth run nginx --count 1000 --output /var/log/synthetic.log

# TCP
logsynth run nginx --duration 5m --output tcp://localhost:5514

# UDP
logsynth run nginx --duration 5m --output udp://localhost:5514
```

## Corruption Modes

Inject malformed logs for testing error handling:

```bash
# 5% corruption rate
logsynth run nginx --count 1000 --corrupt 5
```

Corruption types:
- **truncate** - Random line truncation
- **garbage_timestamp** - Invalid timestamp values
- **missing_field** - Remove fields from output
- **null_byte** - Insert null bytes
- **swap_types** - Replace numbers with strings
- **duplicate_chars** - Duplicate random characters
- **case_flip** - Random case changes

## Burst Patterns

Simulate traffic spikes:

```bash
# 100 lines/sec for 5s, then 10 lines/sec for 25s, repeat
logsynth run nginx --burst 100:5s,10:25s --duration 5m
```

## LLM Configuration

Configure LLM providers in `~/.config/logsynth/config.yaml`:

```yaml
llm:
  provider: ollama  # or openai, vllm, vercel, anthropic
  base_url: http://localhost:11434/v1
  api_key: null  # Not needed for Ollama
  model: llama3.2

defaults:
  rate: 10
  format: plain
```

Supported providers (via OpenAI-compatible API):
- **Ollama** - Local LLMs
- **OpenAI** - GPT-4o, etc.
- **Anthropic** - Via gateway
- **vLLM** - Local inference server
- **Vercel AI Gateway** - Multi-provider gateway

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linting
ruff check .
```

## License

MIT

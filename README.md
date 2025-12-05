# LogSynth

Flexible synthetic log generator with YAML templates, rate control, and LLM-powered template synthesis.

## Installation

```bash
pip install logsynth
```

Or from source:

```bash
git clone https://github.com/lance0/logsynth.git
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

# Use a configuration profile
logsynth run nginx --profile high-volume

# Run parallel streams with per-stream rates
logsynth run nginx redis --stream nginx:rate=50 --stream redis:rate=10 --duration 30s
```

## Features

- **YAML-driven templates** - Define log patterns with field placeholders
- **Multiple field types** - timestamp, choice, int, float, string, uuid, ip, sequence, literal
- **Rate control** - Duration or count-based emission with fractional rates
- **Multiple formats** - Plain text, JSON, logfmt, or Jinja2 templating
- **Corruption injection** - Introduce malformed logs for testing error handling
- **Output sinks** - stdout, files, TCP, or UDP
- **LLM template generation** - Generate templates from natural language (optional)
- **Built-in presets** - 19 presets for web servers, databases, infrastructure, security, and applications
- **Parallel streams** - Run multiple templates concurrently with per-stream rates
- **Burst patterns** - Simulate high/low traffic patterns
- **Configuration profiles** - Named sets of defaults for different scenarios
- **Plugin system** - Extend with custom field types
- **Conditional fields** - Generate fields based on other field values

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

# Per-stream rate configuration
logsynth run nginx redis --stream nginx:rate=50 --stream redis:rate=10 --duration 30s
```

Options:
- `--rate`, `-r` - Lines per second (default: 10)
- `--duration`, `-d` - Run duration (e.g., 30s, 5m, 1h)
- `--count`, `-c` - Number of lines to generate
- `--output`, `-o` - Output destination (file, tcp://host:port, udp://host:port)
- `--format`, `-f` - Output format override (plain, jinja, json, logfmt)
- `--corrupt` - Corruption percentage (0-100)
- `--seed`, `-s` - Random seed for reproducibility
- `--burst`, `-b` - Burst pattern (e.g., 100:5s,10:25s)
- `--preview`, `-p` - Show sample line and exit
- `--profile`, `-P` - Configuration profile name
- `--stream`, `-S` - Per-stream config (e.g., nginx:rate=50,format=json)

### Preset Commands

```bash
# List available presets
logsynth presets list

# Show preset contents
logsynth presets show nginx
```

Available presets:
- **Web servers**: nginx, apache, nginx-error, haproxy
- **Databases**: redis, postgres, mysql, mongodb
- **Infrastructure**: systemd, kubernetes, docker, terraform
- **Security**: auth, sshd, firewall, audit
- **Applications**: java, python, nodejs

### Profile Commands

```bash
# List available profiles
logsynth profiles list

# Show profile contents
logsynth profiles show high-volume

# Create a new profile
logsynth profiles create high-volume --rate 100 --format json --count 10000
```

### Validate Command

```bash
# Validate a template file
logsynth validate my-template.yaml
```

### Prompt Command (LLM)

Generate templates from natural language (requires LLM configuration):

```bash
# Generate and run immediately
logsynth prompt "nginx access logs with authentication failures" --duration 30s

# Generate and save only
logsynth prompt "database connection timeout errors" --save-only

# Generate and open in editor
logsynth prompt "kubernetes pod lifecycle events" --edit
```

## Configuration Profiles

Profiles are named sets of defaults stored in `~/.config/logsynth/profiles/`.

### Creating Profiles

```bash
# Create via CLI
logsynth profiles create high-volume --rate 1000 --format json

# Or create manually
cat > ~/.config/logsynth/profiles/testing.yaml << 'EOF'
rate: 50
format: json
count: 1000
corrupt: 5
EOF
```

### Using Profiles

```bash
# Apply profile settings
logsynth run nginx --profile high-volume

# CLI args override profile settings
logsynth run nginx --profile high-volume --rate 500
```

Profile precedence: defaults < profile < CLI arguments

## Template Format

Templates are YAML files with this structure:

```yaml
name: my-template
format: plain  # plain, jinja, json, or logfmt
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

## Jinja2 Templating

For complex patterns, use Jinja2 syntax (auto-detected):

```yaml
name: alert-logs
format: plain
pattern: |
  {% if level == "ERROR" %}[ALERT] {% endif %}{{ ts }} {{ level }}: {{ message }}
  {% if error_code %}(code: {{ error_code }}){% endif %}

fields:
  ts:
    type: timestamp
    format: "%Y-%m-%d %H:%M:%S"
  level:
    type: choice
    values: [INFO, WARN, ERROR]
    weights: [0.6, 0.25, 0.15]
  message:
    type: choice
    values: ["Request processed", "Connection timeout", "Database error"]
  error_code:
    type: int
    min: 1000
    max: 9999
    when: "level == 'ERROR'"
```

Jinja2 features supported:
- Variable substitution: `{{ field }}`
- Conditionals: `{% if condition %}...{% endif %}`
- Filters: `{{ field | upper }}`
- Loops: `{% for item in items %}...{% endfor %}`

## Conditional Field Generation

Fields can be conditionally generated based on other field values:

```yaml
fields:
  level:
    type: choice
    values: [INFO, WARN, ERROR]

  error_code:
    type: int
    min: 1000
    max: 9999
    when: "level == 'ERROR'"  # Only generated when level is ERROR

  stack_trace:
    type: choice
    values: ["at com.app.Main...", "at org.lib.Handler..."]
    when: "level in ['ERROR', 'WARN']"  # Multiple conditions
```

Supported condition expressions:
- `field == 'value'` - Equality
- `field != 'value'` - Inequality
- `field in ['a', 'b']` - Membership
- `field >= 400` - Numeric comparisons
- `field and other_field` - Logical operators

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

## Plugin System

Extend LogSynth with custom field types by placing Python files in `~/.config/logsynth/plugins/`.

### Creating a Plugin

```python
# ~/.config/logsynth/plugins/custom_hash.py
import hashlib
import random
from logsynth.fields import FieldGenerator, register

class HashGenerator(FieldGenerator):
    """Generate random hash values."""

    def __init__(self, config: dict) -> None:
        self.algorithm = config.get("algorithm", "sha256")
        self.length = config.get("length", 16)

    def generate(self) -> str:
        data = str(random.random()).encode()
        h = hashlib.new(self.algorithm, data)
        return h.hexdigest()[:self.length]

    def reset(self) -> None:
        pass

@register("hash")
def create_hash_generator(config: dict) -> FieldGenerator:
    return HashGenerator(config)
```

### Using Custom Field Types

```yaml
name: with-hash
pattern: |
  [$ts] request_id=$hash $message

fields:
  ts:
    type: timestamp
  hash:
    type: hash  # Your custom type
    algorithm: sha256
    length: 12
  message:
    type: choice
    values: ["Request processed", "Cache miss"]
```

## Per-Stream Rate Configuration

When running multiple streams in parallel, configure each stream independently:

```bash
# Different rates per stream
logsynth run nginx redis postgres \
  --stream nginx:rate=100 \
  --stream redis:rate=20 \
  --stream postgres:rate=10 \
  --duration 1m

# Different formats per stream
logsynth run nginx redis \
  --stream nginx:rate=50,format=json \
  --stream redis:rate=25,format=plain \
  --duration 30s
```

Stream config options:
- `rate=N` - Lines per second for this stream
- `format=X` - Output format (plain, json, logfmt)
- `count=N` - Line count for this stream (with --count mode)

## Output Formats

### Plain (default)
Uses pattern substitution with `$field` or `${field}`:
```
[2025-01-15 10:30:00] INFO Request processed successfully
```

### Jinja
Uses Jinja2 templating with `{{ field }}`:
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

## LLM Configuration (Optional)

The LLM feature requires additional configuration. Configure providers in `~/.config/logsynth/config.yaml`:

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
- **Ollama** - Local LLMs (free, runs locally)
- **OpenAI** - GPT-4o, etc. (requires API key)
- **Anthropic** - Via OpenAI-compatible gateway
- **vLLM** - Local inference server
- **Vercel AI Gateway** - Multi-provider gateway

**Note**: The LLM feature is optional. All other LogSynth features work without any LLM configuration.

## Docker

```bash
# Build the image
docker build -t logsynth .

# Run with default settings
docker run --rm logsynth run nginx --count 100

# Run with custom template (mount volume)
docker run --rm -v $(pwd)/templates:/templates logsynth run /templates/custom.yaml --count 100

# Stream to external endpoint
docker run --rm logsynth run nginx --duration 1h --output tcp://host.docker.internal:5514
```

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

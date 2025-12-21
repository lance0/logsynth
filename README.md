# LogSynth

[![CI](https://github.com/lance0/logsynth/actions/workflows/ci.yml/badge.svg)](https://github.com/lance0/logsynth/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/logsynth.svg)](https://pypi.org/project/logsynth/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Generate realistic synthetic logs for testing, development, and benchmarking. Define patterns in YAML, control output rates, and stream to files, TCP, UDP, or HTTP endpoints.

## Installation

```bash
pip install logsynth
```

## Quick Start

```bash
# Generate 100 nginx access logs
logsynth run nginx --count 100

# Stream logs at 50/sec for 5 minutes
logsynth run nginx --rate 50 --duration 5m

# Output as JSON to a file
logsynth run nginx --count 1000 --format json --output /var/log/test.log

# See what's available
logsynth presets list
```

## Built-in Presets

| Category | Presets |
|----------|---------|
| Web | nginx, apache, nginx-error, haproxy |
| Database | redis, postgres, mysql, mongodb |
| Infrastructure | systemd, kubernetes, docker, terraform |
| Security | auth, sshd, firewall, audit |
| Application | java, python, nodejs |

## Common Options

```bash
logsynth run <preset> [options]

--rate, -r       Lines per second (default: 10)
--count, -c      Total lines to generate
--duration, -d   Run time (30s, 5m, 1h)
--format, -f     Output format: plain, json, logfmt
--output, -o     Destination: file, tcp://, udp://, http://, https://
--header, -H     HTTP header (key:value), can be repeated
--preview, -p    Show sample output and exit
--seed, -s       Random seed for reproducibility
--live, -L       Show live dashboard with real-time stats
```

## Custom Templates

Create YAML templates for any log format:

```yaml
name: my-app
format: plain
pattern: "[$ts] $level: $message"

fields:
  ts:
    type: timestamp
    format: "%Y-%m-%d %H:%M:%S"
  level:
    type: choice
    values: [INFO, WARN, ERROR]
    weights: [0.8, 0.15, 0.05]
  message:
    type: choice
    values:
      - "Request completed"
      - "Connection timeout"
      - "Database error"
```

```bash
logsynth run my-app.yaml --count 100
```

### Field Types

| Type | Description | Key Options |
|------|-------------|-------------|
| `timestamp` | Date/time values | `format`, `step`, `jitter`, `tz` |
| `choice` | Random from list | `values`, `weights` |
| `int` | Random integer | `min`, `max` |
| `float` | Random decimal | `min`, `max`, `precision` |
| `ip` | IP addresses | `cidr`, `ipv6` |
| `uuid` | Random UUIDs | `uppercase` |
| `sequence` | Incrementing numbers | `start`, `step` |
| `literal` | Fixed value | `value` |

## Advanced Features

### Schema Inference

Auto-generate templates from existing log files:

```bash
# Analyze a log file and output YAML template
logsynth infer /var/log/nginx/access.log

# Save to file
logsynth infer access.log --output nginx-template.yaml

# Preview detected fields
logsynth infer access.log --preview
```

Automatically detects:
- **Formats**: JSON, logfmt, plain text
- **Timestamps**: ISO8601, CLF (nginx/apache), syslog, epoch
- **Network**: IPv4/IPv6 addresses
- **HTTP**: methods, status codes, URL paths
- **Logging**: log levels (DEBUG, INFO, WARN, ERROR, etc.)
- **Identifiers**: UUIDs, hex hashes
- **Numbers**: integers (with min/max), floats

### Replay Mode

Replay existing logs with original timing patterns:

```bash
# Replay at real-time speed
logsynth replay /var/log/nginx/access.log

# 10x faster playback
logsynth replay access.log --speed 10

# Skip gaps larger than 60 seconds
logsynth replay access.log --skip-gaps 60

# Replay to HTTP endpoint
logsynth replay access.log --output http://localhost:8080/logs
```

Automatically detects timestamps in ISO8601, CLF (nginx/apache), and syslog formats.

### Watch Mode

Tail log files and forward to outputs (like `tail -f` with superpowers):

```bash
# Watch and print to stdout
logsynth watch /var/log/app.log

# Forward to HTTP endpoint
logsynth watch /var/log/app.log --output http://localhost:8080/logs

# Add metadata to each line
logsynth watch app.log --add-timestamp --add-hostname --add-source

# Wrap in JSON for structured logging
logsynth watch app.log --wrap-json --output http://elasticsearch:9200/_bulk
```

Handles log rotation automatically.

### Live Dashboard

Monitor log generation in real-time with the `--live` flag:

```bash
# Single stream with live stats
logsynth run nginx --rate 100 --duration 5m --live

# Parallel streams with per-stream breakdown
logsynth run nginx redis postgres --duration 5m --live

# Count-based with progress bar
logsynth run nginx --count 10000 --live
```

The dashboard shows:
- Elapsed time and progress (for count/duration targets)
- Per-stream emission rate, count, and errors
- Final summary with average throughput

### Parallel Streams

Run multiple log types simultaneously with independent rates:

```bash
logsynth run nginx redis postgres \
  --stream nginx:rate=100 \
  --stream redis:rate=20 \
  --stream postgres:rate=10 \
  --duration 5m
```

### Conditional Fields

Generate fields only when conditions are met:

```yaml
fields:
  level:
    type: choice
    values: [INFO, ERROR]
  error_code:
    type: int
    min: 1000
    max: 9999
    when: "level == 'ERROR'"
```

### Jinja2 Templates

Use Jinja2 for complex patterns (auto-detected):

```yaml
pattern: |
  {% if level == "ERROR" %}ALERT {% endif %}{{ ts }} {{ level }}: {{ message }}
```

### Corruption Testing

Inject malformed logs to test error handling:

```bash
logsynth run nginx --count 1000 --corrupt 5  # 5% corrupted
```

### Burst Patterns

Simulate traffic spikes:

```bash
# 100/sec for 5s, then 10/sec for 25s, repeat
logsynth run nginx --burst 100:5s,10:25s --duration 5m
```

### Configuration Profiles

Save and reuse settings:

```bash
logsynth profiles create high-volume --rate 1000 --format json
logsynth run nginx --profile high-volume
```

### HTTP Output

POST logs to HTTP endpoints with batching, retries, and dead-letter support:

```bash
# Basic HTTP POST
logsynth run nginx --output http://localhost:8080/logs --count 1000

# With batching config (batch=N lines, timeout=T seconds)
logsynth run nginx --output "http://localhost:8080/logs?batch=50&timeout=10"

# With custom headers
logsynth run nginx --output http://localhost:8080/logs \
  --header "Authorization:Bearer token" \
  --header "X-Source:logsynth"

# NDJSON format for Elasticsearch-style ingestion
logsynth run nginx --output "http://localhost:9200/_bulk?format=ndjson"
```

URL parameters: `batch`, `timeout`, `format` (json/ndjson/text), `retries`, `dead_letter`

Failed batches are written to `./logsynth-dead-letter.jsonl` for retry/debugging.

### Custom Field Plugins

Extend with Python plugins in `~/.config/logsynth/plugins/`:

```python
from logsynth.fields import FieldGenerator, register

class HashGenerator(FieldGenerator):
    def generate(self) -> str:
        return hashlib.sha256(str(random.random()).encode()).hexdigest()[:16]
    def reset(self) -> None:
        pass

@register("hash")
def create(config: dict) -> FieldGenerator:
    return HashGenerator(config)
```

## Docker

```bash
docker build -t logsynth .
docker run --rm logsynth run nginx --count 100
```

## More Examples

See the [`examples/`](examples/) directory for:
- Jinja2 conditional templates
- Custom plugin implementations
- Profile configurations
- Parallel stream scripts

## License

MIT - see [LICENSE](LICENSE)

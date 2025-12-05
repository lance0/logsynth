# LogSynth

[![CI](https://github.com/lance0/logsynth/actions/workflows/ci.yml/badge.svg)](https://github.com/lance0/logsynth/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/logsynth.svg)](https://pypi.org/project/logsynth/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Generate realistic synthetic logs for testing, development, and benchmarking. Define patterns in YAML, control output rates, and stream to files, TCP, or UDP.

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
--output, -o     Destination: file path, tcp://host:port, udp://host:port
--preview, -p    Show sample output and exit
--seed, -s       Random seed for reproducibility
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

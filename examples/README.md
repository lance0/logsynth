# LogSynth Examples

This directory contains example templates, plugins, and profiles demonstrating LogSynth v0.2.0 features.

## Templates

### jinja2-conditional.yaml
Demonstrates Jinja2 templating with:
- Conditional prefixes based on log level
- Dynamic field inclusion using `{% if %}`
- The `when:` clause for conditional field generation

```bash
logsynth run examples/jinja2-conditional.yaml --count 20
```

### with-custom-plugin.yaml
Template using custom field types from a plugin:
- `hash` - Random hash generation
- `useragent` - Realistic user agent strings

Requires plugin installation first (see below).

## Plugins

### custom-plugin.py
Example plugin adding two custom field types:

**Installation:**
```bash
mkdir -p ~/.config/logsynth/plugins
cp examples/custom-plugin.py ~/.config/logsynth/plugins/
```

**Usage:**
```bash
logsynth run examples/with-custom-plugin.yaml --count 10
```

## Profiles

Example configuration profiles in `profiles/` subdirectory:

| Profile | Description |
|---------|-------------|
| `high-volume.yaml` | 1000 lines/sec, JSON format, 100k lines |
| `testing.yaml` | 50 lines/sec with 5% corruption |
| `syslog-forwarding.yaml` | UDP output to syslog |

**Installation:**
```bash
mkdir -p ~/.config/logsynth/profiles
cp examples/profiles/*.yaml ~/.config/logsynth/profiles/
```

**Usage:**
```bash
logsynth run nginx --profile high-volume
logsynth run systemd --profile testing
```

## Per-Stream Rates

### parallel-streams.sh
Bash script demonstrating per-stream rate configuration:

```bash
# Make executable and run
chmod +x examples/parallel-streams.sh
./examples/parallel-streams.sh
```

Or run directly:
```bash
# Different rates per stream
logsynth run nginx redis \
  --stream nginx:rate=50 \
  --stream redis:rate=10 \
  --duration 5s

# Different formats per stream
logsynth run nginx postgres \
  --stream nginx:rate=20,format=json \
  --stream postgres:rate=10,format=plain \
  --duration 3s
```

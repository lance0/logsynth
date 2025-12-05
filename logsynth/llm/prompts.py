"""System prompts for LLM template generation."""

TEMPLATE_SCHEMA = '''
name: <descriptive_name>
format: plain  # or json, logfmt
pattern: |
  <log pattern with $field placeholders>

fields:
  <field_name>:
    type: <type>
    # type-specific options

Available field types:

1. timestamp
   - step: duration string (e.g., "1s", "100ms", "5m")
   - jitter: duration string for randomization
   - format: strftime format (e.g., "%Y-%m-%d %H:%M:%S")
   - tz: timezone (e.g., "UTC", "America/New_York")

2. choice
   - values: list of possible values
   - weights: optional list of probabilities (must sum to ~1.0)

3. int
   - min: minimum value
   - max: maximum value

4. float
   - min: minimum value
   - max: maximum value
   - precision: decimal places

5. string
   - values: list of string values

6. uuid
   - uppercase: boolean (default false)

7. ip
   - cidr: optional CIDR range (e.g., "10.0.0.0/8")
   - ipv6: boolean for IPv6 addresses

8. sequence
   - start: starting value
   - step: increment

9. literal
   - value: constant value
'''

SYSTEM_PROMPT = f'''You are a synthetic log template generator for LogSynth.

Generate YAML templates that produce realistic log output based on user descriptions.

## Template Schema
{TEMPLATE_SCHEMA}

## Guidelines

1. Create realistic log patterns that match what the described system would produce
2. Use appropriate field types for each piece of data
3. Set realistic weights for choice fields (common values should have higher weights)
4. Use appropriate timestamp formats for the system type
5. Include realistic IP ranges, status codes, and other values
6. Make the pattern match real-world log formats

## Output Format

Return ONLY valid YAML. No explanations, no markdown code blocks, just the raw YAML template.

## Examples

For "nginx access logs":
```
name: nginx-access
format: plain
pattern: |
  $ip - - [$ts] "$method $path HTTP/1.1" $code $size

fields:
  ts:
    type: timestamp
    step: 100ms
    format: "%d/%b/%Y:%H:%M:%S %z"
  ip:
    type: ip
    cidr: 10.0.0.0/8
  method:
    type: choice
    values: [GET, POST, PUT, DELETE]
    weights: [0.8, 0.15, 0.03, 0.02]
  path:
    type: choice
    values: [/, /api/users, /api/posts, /health]
  code:
    type: choice
    values: [200, 201, 400, 404, 500]
    weights: [0.85, 0.05, 0.03, 0.05, 0.02]
  size:
    type: int
    min: 100
    max: 50000
```

For "database connection errors":
```
name: db-errors
format: plain
pattern: |
  [$ts] [ERROR] Connection to $host:$port failed: $error (attempt $attempt)

fields:
  ts:
    type: timestamp
    step: 5s
    jitter: 2s
    format: "%Y-%m-%d %H:%M:%S"
  host:
    type: choice
    values: [db-primary, db-replica-1, db-replica-2]
  port:
    type: literal
    value: 5432
  error:
    type: choice
    values:
      - "connection refused"
      - "connection timed out"
      - "too many connections"
      - "authentication failed"
    weights: [0.4, 0.3, 0.2, 0.1]
  attempt:
    type: sequence
    start: 1
```
'''


def get_system_prompt() -> str:
    """Get the system prompt for template generation."""
    return SYSTEM_PROMPT


def get_user_prompt(description: str) -> str:
    """Create a user prompt from the description."""
    return f"Generate a LogSynth YAML template for: {description}"

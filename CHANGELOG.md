# Changelog

All notable changes to LogSynth will be documented in this file.

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
- LLM-powered template generation (OpenAI-compatible API)
- Parallel stream support
- Burst pattern support
- Preview mode
- Editor integration for generated templates
- CLI with Rich formatting
- 82 unit tests

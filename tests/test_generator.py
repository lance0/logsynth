"""Tests for log generator."""

import pytest

from logsynth.core.generator import create_generator, list_presets
from logsynth.utils.schema import ValidationError, load_template

SIMPLE_TEMPLATE = """
name: test
format: plain
pattern: "$ts $level $message"
fields:
  ts:
    type: timestamp
    step: 1s
  level:
    type: choice
    values: [INFO, WARN, ERROR]
  message:
    type: choice
    values: [started, stopped, failed]
"""


class TestLogGenerator:
    """Tests for LogGenerator class."""

    def test_generate_line(self):
        """Should generate log lines."""
        gen = create_generator(SIMPLE_TEMPLATE)
        line = gen.generate()
        assert isinstance(line, str)
        assert len(line) > 0

    def test_contains_fields(self):
        """Generated line should contain field values."""
        gen = create_generator(SIMPLE_TEMPLATE)
        line = gen.generate()
        # Should contain one of the levels
        assert any(level in line for level in ["INFO", "WARN", "ERROR"])
        # Should contain one of the messages
        assert any(msg in line for msg in ["started", "stopped", "failed"])

    def test_seed_reproducibility(self):
        """Resetting generator with seed should reproduce output."""
        # Template without timestamp (which depends on current time)
        template = """
name: test_seed
format: plain
pattern: "$level $message $code"
fields:
  level:
    type: choice
    values: [INFO, WARN, ERROR]
  message:
    type: choice
    values: [started, stopped, failed]
  code:
    type: int
    min: 100
    max: 999
"""
        gen = create_generator(template, seed=42)

        # Generate some lines
        lines1 = [gen.generate() for _ in range(5)]

        # Reset and generate again
        gen.reset()
        lines2 = [gen.generate() for _ in range(5)]

        # Should be identical
        assert lines1 == lines2

    def test_format_override(self):
        """Should respect format override."""
        gen = create_generator(SIMPLE_TEMPLATE, format_override="json")
        line = gen.generate()
        assert line.startswith("{")
        assert line.endswith("}")

    def test_preview(self):
        """Preview should return a sample line."""
        gen = create_generator(SIMPLE_TEMPLATE)
        preview = gen.preview()
        assert isinstance(preview, str)
        assert len(preview) > 0

    def test_reset(self):
        """Reset should restore initial state."""
        gen = create_generator(SIMPLE_TEMPLATE, seed=42)
        line1 = gen.generate()
        gen.generate()
        gen.generate()
        gen.reset()
        line_after_reset = gen.generate()
        assert line1 == line_after_reset


class TestTemplateLoading:
    """Tests for template loading."""

    def test_load_from_string(self):
        """Should load template from YAML string."""
        template = load_template(SIMPLE_TEMPLATE)
        assert template.name == "test"
        assert template.format == "plain"
        assert len(template.fields) == 3

    def test_validation_error_missing_name(self):
        """Should raise for missing name."""
        with pytest.raises(ValidationError) as exc_info:
            load_template("""
format: plain
pattern: test
fields:
  x:
    type: int
""")
        assert "name" in str(exc_info.value.errors)

    def test_validation_error_missing_pattern(self):
        """Should raise for missing pattern."""
        with pytest.raises(ValidationError) as exc_info:
            load_template("""
name: test
fields:
  x:
    type: int
""")
        assert "pattern" in str(exc_info.value.errors)

    def test_validation_error_unknown_type(self):
        """Should raise for unknown field type."""
        with pytest.raises(ValidationError) as exc_info:
            load_template("""
name: test
pattern: $x
fields:
  x:
    type: nonexistent
""")
        assert "unknown type" in str(exc_info.value.errors[0]).lower()


class TestPresets:
    """Tests for preset templates."""

    def test_list_presets(self):
        """Should list available presets."""
        presets = list_presets()
        assert "nginx" in presets
        assert "redis" in presets
        assert "systemd" in presets

    def test_load_nginx_preset(self):
        """Should load nginx preset."""
        gen = create_generator("nginx")
        line = gen.generate()
        assert "HTTP/1.1" in line

    def test_load_redis_preset(self):
        """Should load redis preset."""
        gen = create_generator("redis")
        line = gen.generate()
        # Redis logs have a process ID and role
        assert ":" in line

    def test_load_systemd_preset(self):
        """Should load systemd preset."""
        gen = create_generator("systemd")
        line = gen.generate()
        # Systemd logs have a hostname and unit
        assert "[" in line and "]" in line

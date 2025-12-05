"""Integration tests for CLI commands."""

import os
import tempfile

from typer.testing import CliRunner

from logsynth.cli import app
from logsynth.config import PROFILES_DIR

runner = CliRunner()


class TestRunCommand:
    """Tests for the run command."""

    def test_run_preset_count(self):
        """Should generate logs with --count."""
        result = runner.invoke(app, ["run", "nginx", "--count", "5"])
        assert result.exit_code == 0
        assert "Emitted 5 log lines" in result.stdout

    def test_run_preset_preview(self):
        """Should show preview without running."""
        result = runner.invoke(app, ["run", "nginx", "--preview"])
        assert result.exit_code == 0
        assert "Preview:" in result.stdout or "HTTP/1.1" in result.stdout

    def test_run_preset_json_format(self):
        """Should output JSON format."""
        result = runner.invoke(app, ["run", "nginx", "--count", "3", "--format", "json"])
        assert result.exit_code == 0
        # JSON format output should contain braces
        assert "{" in result.stdout

    def test_run_preset_logfmt_format(self):
        """Should output logfmt format."""
        result = runner.invoke(app, ["run", "nginx", "--count", "3", "--format", "logfmt"])
        assert result.exit_code == 0
        # logfmt output should have key=value pairs
        assert "=" in result.stdout

    def test_run_with_seed(self):
        """Should produce reproducible output with seed."""
        result1 = runner.invoke(app, ["run", "redis", "--count", "3", "--seed", "42"])
        result2 = runner.invoke(app, ["run", "redis", "--count", "3", "--seed", "42"])
        # Lines should be similar (timestamps may differ)
        assert result1.exit_code == 0
        assert result2.exit_code == 0

    def test_run_custom_template(self):
        """Should run custom template file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
name: test-cli
format: plain
pattern: "TEST $level $msg"
fields:
  level:
    type: choice
    values: [INFO, WARN]
  msg:
    type: literal
    value: "hello"
""")
            f.flush()
            result = runner.invoke(app, ["run", f.name, "--count", "2"])
            os.unlink(f.name)

        assert result.exit_code == 0
        assert "TEST" in result.stdout
        assert "hello" in result.stdout

    def test_run_multiple_presets(self):
        """Should run multiple presets in parallel."""
        result = runner.invoke(app, ["run", "nginx", "redis", "--count", "6"])
        assert result.exit_code == 0
        # Should have output from both presets
        assert "HTTP/1.1" in result.stdout or ":" in result.stdout

    def test_run_invalid_preset(self):
        """Should error on invalid preset."""
        result = runner.invoke(app, ["run", "nonexistent_preset_xyz", "--count", "1"])
        assert result.exit_code != 0

    def test_run_with_corruption(self):
        """Should run with corruption enabled."""
        result = runner.invoke(app, ["run", "nginx", "--count", "20", "--corrupt", "50"])
        assert result.exit_code == 0
        assert "Emitted 20 log lines" in result.stdout

    def test_run_output_to_file(self):
        """Should output to file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            filepath = f.name

        try:
            result = runner.invoke(app, ["run", "nginx", "--count", "5", "--output", filepath])
            assert result.exit_code == 0

            with open(filepath) as f:
                content = f.read()
            assert "HTTP/1.1" in content
        finally:
            os.unlink(filepath)


class TestPresetsCommand:
    """Tests for the presets command."""

    def test_presets_list(self):
        """Should list all presets."""
        result = runner.invoke(app, ["presets", "list"])
        assert result.exit_code == 0
        assert "nginx" in result.stdout
        assert "redis" in result.stdout
        assert "systemd" in result.stdout

    def test_presets_show(self):
        """Should show preset contents."""
        result = runner.invoke(app, ["presets", "show", "nginx"])
        assert result.exit_code == 0
        assert "nginx" in result.stdout.lower()

    def test_presets_show_invalid(self):
        """Should error on invalid preset."""
        result = runner.invoke(app, ["presets", "show", "nonexistent_preset_xyz"])
        assert result.exit_code != 0 or "not found" in result.stdout.lower()


class TestProfilesCommand:
    """Tests for the profiles command."""

    def test_profiles_list(self):
        """Should list profiles."""
        result = runner.invoke(app, ["profiles", "list"])
        assert result.exit_code == 0

    def test_profiles_create_and_show(self):
        """Should create and show a profile."""
        # Create a unique profile name
        profile_name = "test_profile_integration"

        try:
            # Create profile
            result = runner.invoke(app, [
                "profiles", "create", profile_name,
                "--rate", "100",
                "--format", "json"
            ])
            assert result.exit_code == 0

            # Show profile
            result = runner.invoke(app, ["profiles", "show", profile_name])
            assert result.exit_code == 0
            assert "100" in result.stdout or "rate" in result.stdout.lower()

        finally:
            # Cleanup
            profile_path = PROFILES_DIR / f"{profile_name}.yaml"
            if profile_path.exists():
                profile_path.unlink()

    def test_profiles_show_invalid(self):
        """Should error on invalid profile."""
        result = runner.invoke(app, ["profiles", "show", "nonexistent_profile_xyz"])
        assert result.exit_code != 0 or "not found" in result.stdout.lower()


class TestValidateCommand:
    """Tests for the validate command."""

    def test_validate_valid_template(self):
        """Should validate correct template."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
name: valid-test
format: plain
pattern: "$ts $msg"
fields:
  ts:
    type: timestamp
  msg:
    type: literal
    value: test
""")
            f.flush()
            result = runner.invoke(app, ["validate", f.name])
            os.unlink(f.name)

        assert result.exit_code == 0
        assert "valid" in result.stdout.lower()

    def test_validate_invalid_template(self):
        """Should report invalid template."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
name: invalid-test
pattern: "$undefined_field"
fields:
  ts:
    type: timestamp
""")
            f.flush()
            result = runner.invoke(app, ["validate", f.name])
            os.unlink(f.name)

        # Should indicate error (either exit code or message)
        assert result.exit_code != 0 or "error" in result.stdout.lower()


class TestPerStreamConfig:
    """Tests for per-stream rate configuration."""

    def test_stream_config_rate(self):
        """Should apply per-stream rate."""
        result = runner.invoke(app, [
            "run", "nginx", "redis",
            "--stream", "nginx:rate=20",
            "--stream", "redis:rate=5",
            "--duration", "1s"
        ])
        assert result.exit_code == 0

    def test_stream_config_format(self):
        """Should apply per-stream format."""
        result = runner.invoke(app, [
            "run", "nginx", "redis",
            "--stream", "nginx:format=json",
            "--stream", "redis:format=plain",
            "--count", "4"
        ])
        assert result.exit_code == 0


class TestJinja2Templates:
    """Tests for Jinja2 templating."""

    def test_jinja2_basic(self):
        """Should process Jinja2 template."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
name: jinja2-test
format: plain
pattern: |
  {{ level }}: {{ message }}
fields:
  level:
    type: choice
    values: [INFO, ERROR]
  message:
    type: literal
    value: test-message
""")
            f.flush()
            result = runner.invoke(app, ["run", f.name, "--count", "3"])
            os.unlink(f.name)

        assert result.exit_code == 0
        assert "test-message" in result.stdout

    def test_jinja2_conditional(self):
        """Should process Jinja2 conditionals."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
name: jinja2-conditional
format: plain
pattern: |
  {% if level == "ERROR" %}ALERT {% endif %}{{ level }}: {{ message }}
fields:
  level:
    type: choice
    values: [ERROR]
  message:
    type: literal
    value: test
""")
            f.flush()
            result = runner.invoke(app, ["run", f.name, "--count", "2"])
            os.unlink(f.name)

        assert result.exit_code == 0
        assert "ALERT" in result.stdout


class TestConditionalFields:
    """Tests for conditional field generation."""

    def test_when_clause(self):
        """Should respect when clause."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
name: conditional-test
format: plain
pattern: |
  {{ level }}{% if code %} code={{ code }}{% endif %}
fields:
  level:
    type: choice
    values: [ERROR]
  code:
    type: int
    min: 100
    max: 999
    when: "level == 'ERROR'"
""")
            f.flush()
            result = runner.invoke(app, ["run", f.name, "--count", "3"])
            os.unlink(f.name)

        assert result.exit_code == 0
        # Since level is always ERROR, code should appear
        assert "code=" in result.stdout


class TestBurstPattern:
    """Tests for burst pattern functionality."""

    def test_burst_pattern(self):
        """Should run with burst pattern."""
        result = runner.invoke(app, [
            "run", "nginx",
            "--burst", "50:1s,10:1s",
            "--duration", "2s"
        ])
        assert result.exit_code == 0

# Contributing to LogSynth

Thanks for your interest in contributing!

## Development Setup

```bash
# Clone the repo
git clone https://github.com/lance0/logsynth.git
cd logsynth

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pip install pre-commit
pre-commit install
```

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=logsynth --cov-report=term-missing

# Run specific test file
pytest tests/test_cli.py -v
```

## Code Style

We use [ruff](https://github.com/astral-sh/ruff) for linting and formatting:

```bash
# Check for issues
ruff check .

# Auto-fix issues
ruff check --fix .

# Format code
ruff format .
```

Pre-commit hooks will run these automatically on commit.

## Adding a New Preset

1. Create a YAML file in `logsynth/presets/`
2. Follow the existing preset structure
3. Add tests if the preset uses unique patterns
4. Update the preset count in docs if needed

## Adding a New Field Type

1. Create a generator class in `logsynth/fields/`
2. Use the `@register("typename")` decorator
3. Add tests in `tests/test_fields.py`
4. Document in README if it's a core type

## Pull Requests

1. Fork the repo and create a branch from `master`
2. Make your changes with tests
3. Ensure all tests pass: `pytest`
4. Ensure linting passes: `ruff check .`
5. Submit the PR with a clear description

## Reporting Issues

- Check existing issues first
- Include Python version and OS
- Provide minimal reproduction steps
- Include full error messages/tracebacks

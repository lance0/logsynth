"""Convert natural language prompts to LogSynth templates using LLM."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from logsynth.config import GENERATED_DIR, ensure_dirs
from logsynth.llm.client import ChatMessage, LLMClient, create_client
from logsynth.llm.prompts import get_system_prompt, get_user_prompt
from logsynth.utils.schema import ValidationError, load_template


class TemplateGenerationError(Exception):
    """Raised when template generation fails."""

    pass


def _extract_yaml(response: str) -> str:
    """Extract YAML from LLM response, handling markdown code blocks."""
    # Try to extract from markdown code block
    yaml_match = re.search(r"```(?:yaml|yml)?\n(.*?)```", response, re.DOTALL)
    if yaml_match:
        return yaml_match.group(1).strip()

    # Try to find YAML-like content (starts with 'name:')
    yaml_match = re.search(r"(name:\s*\S+.*)", response, re.DOTALL)
    if yaml_match:
        return yaml_match.group(1).strip()

    # Return as-is and let validation fail if it's not valid
    return response.strip()


def _sanitize_name(description: str) -> str:
    """Create a safe filename from description."""
    # Take first few words and sanitize
    words = re.findall(r"\w+", description.lower())[:4]
    name = "-".join(words) if words else "template"
    return name


def generate_template(
    description: str,
    client: LLMClient | None = None,
    validate: bool = True,
) -> Path:
    """Generate a template from natural language description.

    Args:
        description: Natural language description of desired logs
        client: Optional LLM client (creates one if not provided)
        validate: Whether to validate the generated template

    Returns:
        Path to the saved template file

    Raises:
        TemplateGenerationError: If generation or validation fails
    """
    ensure_dirs()

    # Create client if not provided
    own_client = client is None
    if own_client:
        client = create_client()

    try:
        # Create messages
        messages = [
            ChatMessage(role="system", content=get_system_prompt()),
            ChatMessage(role="user", content=get_user_prompt(description)),
        ]

        # Get response
        response = client.chat(messages, temperature=0.7)
        yaml_content = _extract_yaml(response.content)

        # Validate if requested
        if validate:
            try:
                load_template(yaml_content)  # Validates the template
            except ValidationError as e:
                raise TemplateGenerationError(
                    f"Generated template is invalid: {e.message}\n"
                    f"Errors: {', '.join(e.errors)}\n"
                    f"Raw output:\n{yaml_content}"
                )

        # Generate filename
        base_name = _sanitize_name(description)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"{base_name}-{timestamp}.yaml"
        filepath = GENERATED_DIR / filename

        # Save template
        with open(filepath, "w") as f:
            f.write(yaml_content)

        return filepath

    finally:
        if own_client and client:
            client.close()


def generate_template_string(
    description: str,
    client: LLMClient | None = None,
) -> str:
    """Generate a template from natural language description.

    Args:
        description: Natural language description of desired logs
        client: Optional LLM client (creates one if not provided)

    Returns:
        YAML template string (not saved to file)
    """
    own_client = client is None
    if own_client:
        client = create_client()

    try:
        messages = [
            ChatMessage(role="system", content=get_system_prompt()),
            ChatMessage(role="user", content=get_user_prompt(description)),
        ]

        response = client.chat(messages, temperature=0.7)
        return _extract_yaml(response.content)

    finally:
        if own_client and client:
            client.close()

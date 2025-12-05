"""LLM integration for template generation."""

from logsynth.llm.client import ChatMessage, ChatResponse, LLMClient, create_client
from logsynth.llm.prompt2template import (
    TemplateGenerationError,
    generate_template,
    generate_template_string,
)

__all__ = [
    "ChatMessage",
    "ChatResponse",
    "LLMClient",
    "create_client",
    "TemplateGenerationError",
    "generate_template",
    "generate_template_string",
]

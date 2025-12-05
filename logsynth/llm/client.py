"""OpenAI-compatible LLM client.

Supports: OpenAI, Anthropic (via gateway), Vercel AI Gateway, vLLM, Ollama
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from logsynth.config import LLMConfig, get_llm_settings


@dataclass
class ChatMessage:
    """A chat message."""

    role: str  # "system", "user", or "assistant"
    content: str


@dataclass
class ChatResponse:
    """Response from the chat API."""

    content: str
    model: str
    usage: dict[str, int] | None = None


class LLMClient:
    """OpenAI-compatible chat client."""

    def __init__(self, config: LLMConfig | None = None) -> None:
        """Initialize client with configuration.

        Args:
            config: LLM configuration. If None, loads from config file.
        """
        self.config = config or get_llm_settings()
        self._client = httpx.Client(timeout=120.0)

    @property
    def base_url(self) -> str:
        """Get the base URL for the API."""
        url = self.config.base_url.rstrip("/")
        # Ensure it ends with /v1 for OpenAI-compatible APIs
        if not url.endswith("/v1"):
            if "/v1" not in url:
                url = f"{url}/v1"
        return url

    def chat(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> ChatResponse:
        """Send a chat completion request.

        Args:
            messages: List of chat messages
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response

        Returns:
            ChatResponse with the model's response
        """
        headers = {"Content-Type": "application/json"}

        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        payload = {
            "model": self.config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        url = f"{self.base_url}/chat/completions"

        response = self._client.post(url, json=payload, headers=headers)
        response.raise_for_status()

        data = response.json()

        # Extract response content
        content = data["choices"][0]["message"]["content"]

        return ChatResponse(
            content=content,
            model=data.get("model", self.config.model),
            usage=data.get("usage"),
        )

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self) -> LLMClient:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()


def create_client(config: LLMConfig | None = None) -> LLMClient:
    """Create an LLM client."""
    return LLMClient(config)

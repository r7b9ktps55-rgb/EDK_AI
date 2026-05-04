"""Abstract base class for AI providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any


class BaseProvider(ABC):
    """Abstract base for all AI providers.

    All AI provider implementations must inherit from this class and
    implement the abstract methods/properties. The interface is designed
    around async streaming chat completions, with a non-streaming
    convenience method.
    """

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        stream: bool = True,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """Send chat request and yield response text chunks.

        Args:
            messages: Conversation history as list of {"role": "...", "content": "..."} dicts.
            model: Model identifier to use. Falls back to :pyattr:`default_model` when ``None``.
            stream: Whether to stream response chunks (``True``) or
                buffer and yield the full text (``False``).
            temperature: Sampling temperature (0.0–2.0).
            max_tokens: Maximum number of tokens to generate.

        Yields:
            Response text chunks.
        """
        ...

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        """Non-streaming completion.

        Args:
            prompt: User prompt string.
            model: Model identifier to use. Falls back to :pyattr:`default_model` when ``None``.
            temperature: Sampling temperature (0.0–2.0).
            max_tokens: Maximum number of tokens to generate.

        Returns:
            Full response text.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (machine-friendly identifier)."""
        ...

    @property
    @abstractmethod
    def available_models(self) -> list[str]:
        """List of available model identifiers."""
        ...

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Whether the provider is ready to use (e.g., API key set, service reachable)."""
        ...

    @property
    @abstractmethod
    def default_model(self) -> str:
        """Default model identifier used when none is specified."""
        ...

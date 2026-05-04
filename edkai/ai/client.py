"""Unified AI client that delegates to a provider."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from edkai.ai.exceptions import AIError
from edkai.ai.providers.base import BaseProvider


# ---------------------------------------------------------------------------
# AIClient
# ---------------------------------------------------------------------------


class AIClient:
    """Unified AI client that delegates all operations to a :class:`BaseProvider`.

    The client is intentionally thin — business logic lives in the provider
    implementations so that each can handle vendor-specific quirks (SSE
    parsing, error codes, response shape, etc.).

    Args:
        provider: The provider instance to delegate to.  May be ``None``
            during construction, but must be set before calling any
            async method.
    """

    def __init__(self, provider: BaseProvider | None = None) -> None:
        self.provider = provider

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        stream: bool = True,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """Send a chat request and yield response text chunks.

        Args:
            messages: Conversation history as list of ``{"role": ..., "content": ...}``.
            stream: Whether to stream response chunks.
            model: Model override.  When ``None``, the provider's default is used.
            temperature: Sampling temperature (0.0–2.0).
            max_tokens: Maximum tokens to generate.

        Yields:
            Response text chunks.

        Raises:
            AIError: If no provider is configured.
        """
        if not self.provider:
            raise AIError("No AI provider configured")
        async for chunk in self.provider.chat(
            messages,
            stream=stream,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            yield chunk

    async def complete(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        """Non-streaming completion for a single prompt.

        Internally calls :pyfunc:`chat` with a single user message and
        ``stream=False``, then joins all chunks.

        Args:
            prompt: The user prompt.
            model: Model override.  When ``None``, the provider's default is used.
            temperature: Sampling temperature (0.0–2.0).
            max_tokens: Maximum tokens to generate.

        Returns:
            Full response text.

        Raises:
            AIError: If no provider is configured.
        """
        if not self.provider:
            raise AIError("No AI provider configured")
        parts: list[str] = []
        async for chunk in self.provider.chat(
            [{"role": "user", "content": prompt}],
            stream=False,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            parts.append(chunk)
        return "".join(parts)

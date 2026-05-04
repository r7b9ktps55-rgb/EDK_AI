"""Auto-fallback provider that switches between providers on rate limit / error."""
from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from typing import Any

from edkai.ai.exceptions import AIError, AIAuthError, AIRateLimitError, AINetworkError
from edkai.ai.providers.base import BaseProvider


class ProviderStatus:
    """Track status of a single provider."""

    def __init__(self, provider: BaseProvider):
        self.provider = provider
        self.last_error: str = ""
        self.last_used: float = 0.0
        self.request_count: int = 0
        self.is_available: bool = True
        self.rate_limit_reset: float = 0.0

    @property
    def name(self) -> str:
        return self.provider.name

    @property
    def model(self) -> str:
        return self.provider.default_model

    @property
    def can_use(self) -> bool:
        if not self.is_available:
            return False
        if time.time() < self.rate_limit_reset:
            return False
        return True

    def mark_error(self, error: str) -> None:
        self.last_error = error
        if "rate" in error.lower() or "429" in error or "quota" in error.lower() or "limit" in error.lower():
            self.rate_limit_reset = time.time() + 60  # Wait 60s
        if "auth" in error.lower() or "401" in error or "403" in error:
            self.is_available = False

    def mark_success(self) -> None:
        self.last_error = ""
        self.last_used = time.time()
        self.request_count += 1
        self.is_available = True


class AutoFallbackProvider(BaseProvider):
    """Wraps multiple providers and auto-switches on failures.

    Usage:
        providers = [github, ollama, gemini]
        fallback = AutoFallbackProvider(providers)
        async for chunk in fallback.chat(messages):
            print(chunk, end="")
    """

    def __init__(self, providers: list[BaseProvider]) -> None:
        if not providers:
            raise AIError("No providers configured for fallback")
        self._providers = [ProviderStatus(p) for p in providers]
        self._current_index = 0
        self._last_provider: ProviderStatus | None = None

    @property
    def name(self) -> str:
        return f"fallback({self.current_provider.name})"

    @property
    def available_models(self) -> list[str]:
        models = []
        for ps in self._providers:
            models.extend(ps.provider.available_models)
        return list(dict.fromkeys(models))  # Deduplicate

    @property
    def is_configured(self) -> bool:
        return any(p.can_use for p in self._providers)

    @property
    def default_model(self) -> str:
        return self.current_provider.default_model

    @property
    def current_provider(self) -> BaseProvider:
        return self._providers[self._current_index].provider

    @property
    def current_status(self) -> ProviderStatus:
        return self._providers[self._current_index]

    @property
    def all_statuses(self) -> list[ProviderStatus]:
        return list(self._providers)

    def _find_next_available(self) -> int:
        """Find index of next available provider."""
        for offset in range(len(self._providers)):
            idx = (self._current_index + offset) % len(self._providers)
            if self._providers[idx].can_use:
                return idx
        # All unavailable, reset rate limits and try first
        for ps in self._providers:
            ps.rate_limit_reset = 0
        return 0

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        stream: bool = True,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """Chat with auto-fallback between providers."""
        last_error: Exception | None = None

        for attempt in range(len(self._providers)):
            idx = self._find_next_available()
            status = self._providers[idx]
            self._current_index = idx

            try:
                async for chunk in status.provider.chat(
                    messages,
                    model=model,
                    stream=stream,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ):
                    yield chunk
                status.mark_success()
                self._last_provider = status
                return

            except (AIRateLimitError, AIAuthError, AINetworkError) as e:
                error_msg = str(e)
                status.mark_error(error_msg)
                last_error = e

                if attempt < len(self._providers) - 1:
                    # Try next provider
                    self._current_index = (idx + 1) % len(self._providers)
                    continue

        # All providers failed
        raise AIError(
            f"All {len(self._providers)} providers failed. "
            f"Last error: {last_error}"
        )

    async def complete(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        """Complete with auto-fallback."""
        parts = []
        async for chunk in self.chat(
            [{"role": "user", "content": prompt}],
            stream=False,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            parts.append(chunk)
        return "".join(parts)

"""OpenRouter provider — unified access to hundreds of models.

OpenRouter provides a unified API for accessing models from various providers,
including free-tier models with no API key required.

* Base URL: ``https://openrouter.ai/api/v1``
* Auth: ``OPENROUTER_API_KEY`` env var (optional for free tier)
* Docs: https://openrouter.ai/docs
"""
from __future__ import annotations

import json
import os
from collections.abc import AsyncGenerator
from typing import Any

import aiohttp

from edkai.ai.exceptions import AIAuthError, AINetworkError, AIRateLimitError, AIError
from edkai.ai.providers.base import BaseProvider


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BASE_URL = "https://openrouter.ai/api/v1"
_DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct:free"
_BUILTIN_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "deepseek/deepseek-r1:free",
    "google/gemma-3-12b-it:free",
    "qwen/qwen-2.5-72b-instruct:free",
]

_HTTP_UNAUTHORIZED = 401
_HTTP_FORBIDDEN = 403
_HTTP_RATE_LIMIT = 429


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

class OpenRouterProvider(BaseProvider):
    """OpenRouter inference provider. Free tier: 50 req/day (200 with credits).

    OpenRouter's free tier works without an API key, though providing one
    increases rate limits and enables usage tracking.

    Args:
        api_key: OpenRouter API key. Falls back to the ``OPENROUTER_API_KEY``
            environment variable. Optional for free-tier models.
        base_url: Override the default base URL.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self._base_url = (base_url or _BASE_URL).rstrip("/")

    # -- BaseProvider interface ------------------------------------------

    @property
    def name(self) -> str:
        return "openrouter"

    @property
    def available_models(self) -> list[str]:
        return list(_BUILTIN_MODELS)

    @property
    def is_configured(self) -> bool:
        # OpenRouter free tier works without an API key.
        return True

    @property
    def default_model(self) -> str:
        return _DEFAULT_MODEL

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        stream: bool = True,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """Send chat request to OpenRouter and yield response text chunks via SSE."""
        request_body: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }
        if max_tokens is not None:
            request_body["max_tokens"] = max_tokens

        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if stream else "application/json",
            "HTTP-Referer": "https://edkai.ai",
            "X-Title": "EDK_AI",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        url = f"{self._base_url}/chat/completions"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=headers,
                    json=request_body,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    # ---- error handling --------------------------------
                    if resp.status == _HTTP_UNAUTHORIZED or resp.status == _HTTP_FORBIDDEN:
                        body = await resp.text()
                        raise AIAuthError(f"OpenRouter auth failed ({resp.status}): {body}")
                    if resp.status == _HTTP_RATE_LIMIT:
                        raise AIRateLimitError(
                            "OpenRouter rate limit exceeded. Free tier: 50 req/day "
                            "(200 req/day with $10+ in credits)."
                        )
                    if resp.status >= 400:
                        body = await resp.text()
                        raise AIError(f"OpenRouter HTTP {resp.status}: {body}")

                    # ---- streaming response ----------------------------
                    if stream:
                        async for line in resp.content:
                            decoded = line.decode("utf-8").strip()
                            if not decoded or not decoded.startswith("data: "):
                                continue
                            payload = decoded[6:]
                            if payload == "[DONE]":
                                break
                            try:
                                chunk = json.loads(payload)
                                # OpenRouter may return an error inside the stream
                                if chunk.get("error"):
                                    raise AIError(f"OpenRouter error: {chunk['error']}")
                                delta = (
                                    chunk.get("choices", [{}])[0]
                                    .get("delta", {})
                                    .get("content")
                                )
                                if delta:
                                    yield delta
                            except (json.JSONDecodeError, IndexError, KeyError):
                                continue
                    else:
                        body = await resp.json()
                        if body.get("error"):
                            raise AIError(f"OpenRouter error: {body['error']}")
                        content = (
                            body.get("choices", [{}])[0]
                            .get("message", {})
                            .get("content", "")
                        )
                        yield content

        except (AIAuthError, AIRateLimitError, AIError):
            raise
        except aiohttp.ClientError as exc:
            raise AINetworkError(f"OpenRouter network error: {exc}") from exc
        except TimeoutError as exc:
            raise AINetworkError(f"OpenRouter request timed out: {exc}") from exc

    async def complete(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        """Non-streaming completion."""
        parts: list[str] = []
        async for chunk in self.chat(
            [{"role": "user", "content": prompt}],
            model=model,
            stream=False,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            parts.append(chunk)
        return "".join(parts)

"""Generic OpenAI-compatible fallback provider.

Works with any inference endpoint that exposes the standard
``/chat/completions`` route using Server-Sent Events (SSE) for streaming.

Typical use cases:
* Self-hosted OpenAI-compatible proxies (LiteLLM, LocalAI, etc.)
* Direct OpenAI API access
* Azure OpenAI Service (with custom base URL)
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

_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_MODEL = "gpt-4o-mini"

_HTTP_UNAUTHORIZED = 401
_HTTP_FORBIDDEN = 403
_HTTP_RATE_LIMIT = 429


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

class OpenAICompatibleProvider(BaseProvider):
    """Generic OpenAI-compatible inference provider.

    Args:
        api_key: API key for the endpoint.  Falls back to the
            ``OPENAI_API_KEY`` environment variable.
        base_url: Provider's base API URL (default: ``https://api.openai.com/v1``).
        default_model: Default model slug (default: ``"gpt-4o-mini"``).
        models: Optional list of available model identifiers.  When empty,
            the ``default_model`` is used as the sole entry.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str | None = None,
        models: list[str] | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._base_url = (base_url or _DEFAULT_BASE_URL).rstrip("/")
        self._default_model = default_model or _DEFAULT_MODEL
        self._models = models or [self._default_model]

    # -- BaseProvider interface ------------------------------------------

    @property
    def name(self) -> str:
        return "openai_compat"

    @property
    def available_models(self) -> list[str]:
        return list(self._models)

    @property
    def is_configured(self) -> bool:
        # OpenAI-compatible endpoints generally need an API key.
        # Some local proxies (e.g., LM Studio) don't require one,
        # so we allow either a key or a non-default base_url.
        return bool(self._api_key) or self._base_url != _DEFAULT_BASE_URL

    @property
    def default_model(self) -> str:
        return self._default_model

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        stream: bool = True,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """Send chat request and yield response text chunks via SSE streaming."""
        request_body: dict[str, Any] = {
            "model": model or self._default_model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }
        if max_tokens is not None:
            request_body["max_tokens"] = max_tokens

        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if stream else "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        url = f"{self._base_url}/chat/completions"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=request_body) as resp:
                    # ---- error handling --------------------------------
                    if resp.status == _HTTP_UNAUTHORIZED or resp.status == _HTTP_FORBIDDEN:
                        body = await resp.text()
                        raise AIAuthError(
                            f"OpenAI-compatible auth failed ({resp.status}): {body}"
                        )
                    if resp.status == _HTTP_RATE_LIMIT:
                        body = await resp.text()
                        raise AIRateLimitError(
                            f"OpenAI-compatible rate limit exceeded: {body}"
                        )
                    if resp.status >= 400:
                        body = await resp.text()
                        raise AIError(
                            f"OpenAI-compatible HTTP {resp.status}: {body}"
                        )

                    # ---- streaming response ----------------------------
                    if stream:
                        async for line in resp.content:
                            decoded = line.decode("utf-8").strip()
                            if not decoded or not decoded.startswith("data: "):
                                continue
                            payload = decoded[6:]  # strip "data: " prefix
                            if payload == "[DONE]":
                                break
                            try:
                                chunk = json.loads(payload)
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
                        content = (
                            body.get("choices", [{}])[0]
                            .get("message", {})
                            .get("content", "")
                        )
                        yield content

        except (AIAuthError, AIRateLimitError, AIError):
            raise
        except aiohttp.ClientError as exc:
            raise AINetworkError(f"OpenAI-compatible network error: {exc}") from exc
        except TimeoutError as exc:
            raise AINetworkError(f"OpenAI-compatible request timed out: {exc}") from exc

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

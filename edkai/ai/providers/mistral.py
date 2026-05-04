"""Mistral AI provider — frontier-class European models.

Mistral offers a range of frontier-class models including code-specialized
and general-purpose chat models with a generous free tier.

* Base URL: ``https://api.mistral.ai/v1``
* Auth: ``MISTRAL_API_KEY`` env var
* Docs: https://docs.mistral.ai
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

_BASE_URL = "https://api.mistral.ai/v1"
_DEFAULT_MODEL = "codestral-2501"
_BUILTIN_MODELS = [
    "codestral-2501",
    "mistral-small-2501",
    "mistral-medium-3",
    "mistral-large-2411",
]

_HTTP_UNAUTHORIZED = 401
_HTTP_FORBIDDEN = 403
_HTTP_RATE_LIMIT = 429


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

class MistralProvider(BaseProvider):
    """Mistral AI inference provider. Free tier: 1B tokens/month.

    Args:
        api_key: Mistral API key. Falls back to the ``MISTRAL_API_KEY``
            environment variable.
        base_url: Override the default base URL.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("MISTRAL_API_KEY", "")
        self._base_url = (base_url or _BASE_URL).rstrip("/")

    # -- BaseProvider interface ------------------------------------------

    @property
    def name(self) -> str:
        return "mistral"

    @property
    def available_models(self) -> list[str]:
        return list(_BUILTIN_MODELS)

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

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
        """Send chat request to Mistral and yield response text chunks via SSE."""
        if not self._api_key:
            raise AIAuthError(
                "Mistral API key not configured. Set MISTRAL_API_KEY env var."
            )

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
            "Authorization": f"Bearer {self._api_key}",
        }

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
                        raise AIAuthError(f"Mistral auth failed ({resp.status}): {body}")
                    if resp.status == _HTTP_RATE_LIMIT:
                        raise AIRateLimitError(
                            "Mistral rate limit exceeded. Free tier: 1B tokens/month."
                        )
                    if resp.status >= 400:
                        body = await resp.text()
                        raise AIError(f"Mistral HTTP {resp.status}: {body}")

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
            raise AINetworkError(f"Mistral network error: {exc}") from exc
        except TimeoutError as exc:
            raise AINetworkError(f"Mistral request timed out: {exc}") from exc

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

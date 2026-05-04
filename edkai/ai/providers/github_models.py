"""GitHub Models provider — free tier (150 requests / day).

GitHub Models is an OpenAI-compatible inference endpoint hosted on Azure.
Authentication is via a ``GITHUB_TOKEN`` environment variable; the token
is optional for public repositories but increases rate limits.

* Base URL: ``https://models.inference.ai.azure.com``
* Endpoint: ``/chat/completions``
* Docs: https://docs.github.com/en/github-models
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

_BASE_URL = "https://models.inference.ai.azure.com"
_DEFAULT_MODEL = "phi-4"
_BUILTIN_MODELS = [
    "phi-4",
    "Llama-3.3-70B-Instruct",
    "Mistral-Large-2411",
    "Codestral-2501",
]

# HTTP status codes
_HTTP_UNAUTHORIZED = 401
_HTTP_FORBIDDEN = 403
_HTTP_RATE_LIMIT = 429


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

class GitHubModelsProvider(BaseProvider):
    """GitHub Models inference provider.

    Args:
        api_key: GitHub personal access token.  Falls back to the
            ``GITHUB_TOKEN`` environment variable.
        base_url: Override the default base URL (for enterprise / proxy).
        default_model: Override the default model slug.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("GITHUB_TOKEN", "")
        self._base_url = (base_url or _BASE_URL).rstrip("/")
        self._default_model = default_model or _DEFAULT_MODEL

    # -- BaseProvider interface ------------------------------------------

    @property
    def name(self) -> str:
        return "github_models"

    @property
    def available_models(self) -> list[str]:
        return list(_BUILTIN_MODELS)

    @property
    def is_configured(self) -> bool:
        # GitHub Models works without a token for public repos (lower rate).
        return True

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

        headers = {
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
                            f"GitHub Models auth failed ({resp.status}): {body}"
                        )
                    if resp.status == _HTTP_RATE_LIMIT:
                        body = await resp.text()
                        raise AIRateLimitError(
                            f"GitHub Models rate limit exceeded: {body}"
                        )
                    if resp.status >= 400:
                        body = await resp.text()
                        raise AIError(
                            f"GitHub Models HTTP {resp.status}: {body}"
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
                        # non-streaming — buffer entire response
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
            raise AINetworkError(f"GitHub Models network error: {exc}") from exc
        except TimeoutError as exc:
            raise AINetworkError(f"GitHub Models request timed out: {exc}") from exc

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

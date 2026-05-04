"""Cloudflare AI Workers provider — edge-deployed inference.

Cloudflare offers AI inference at the edge with a generous free tier
based on daily neuron allocation.

* Base URL: ``https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1``
* Auth: ``CF_API_TOKEN`` + ``CF_ACCOUNT_ID`` env vars
* Docs: https://developers.cloudflare.com/workers-ai
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

_BASE_URL_TEMPLATE = "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1"
_DEFAULT_MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8"
_BUILTIN_MODELS = [
    "@cf/meta/llama-3.1-8b-instruct",
    "@cf/meta/llama-3.3-70b-instruct-fp8",
    "@cf/qwen/qwen-32b",
    "@cf/deepseek-ai/deepseek-r1-distill-qwen-32b",
]

_HTTP_UNAUTHORIZED = 401
_HTTP_FORBIDDEN = 403
_HTTP_RATE_LIMIT = 429


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

class CloudflareProvider(BaseProvider):
    """Cloudflare Workers AI inference provider. Free tier: 10K neurons/day.

    Requires both an API token and an Account ID to construct the endpoint URL.

    Args:
        api_key: Cloudflare API token. Falls back to the ``CF_API_TOKEN``
            environment variable.
        base_url: Override the default base URL. The account ID from
            ``CF_ACCOUNT_ID`` will still be substituted.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("CF_API_TOKEN", "")
        self._account_id = os.environ.get("CF_ACCOUNT_ID", "")
        self._base_url_override = base_url

    # -- BaseProvider interface ------------------------------------------

    @property
    def name(self) -> str:
        return "cloudflare"

    @property
    def available_models(self) -> list[str]:
        return list(_BUILTIN_MODELS)

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key) and bool(self._account_id)

    @property
    def default_model(self) -> str:
        return _DEFAULT_MODEL

    def _get_base_url(self) -> str:
        """Construct the full base URL with account ID."""
        if self._base_url_override:
            return self._base_url_override.rstrip("/")
        if not self._account_id:
            raise AIError(
                "Cloudflare Account ID not configured. Set CF_ACCOUNT_ID env var."
            )
        return _BASE_URL_TEMPLATE.format(account_id=self._account_id)

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        stream: bool = True,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """Send chat request to Cloudflare AI and yield response text chunks via SSE."""
        if not self._api_key:
            raise AIAuthError(
                "Cloudflare API token not configured. Set CF_API_TOKEN env var."
            )
        if not self._account_id:
            raise AIAuthError(
                "Cloudflare Account ID not configured. Set CF_ACCOUNT_ID env var."
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

        url = f"{self._get_base_url()}/chat/completions"

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
                        raise AIAuthError(f"Cloudflare auth failed ({resp.status}): {body}")
                    if resp.status == _HTTP_RATE_LIMIT:
                        raise AIRateLimitError(
                            "Cloudflare AI rate limit exceeded. Free tier: 10K neurons/day."
                        )
                    if resp.status >= 400:
                        body = await resp.text()
                        raise AIError(f"Cloudflare AI HTTP {resp.status}: {body}")

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
            raise AINetworkError(f"Cloudflare AI network error: {exc}") from exc
        except TimeoutError as exc:
            raise AINetworkError(f"Cloudflare AI request timed out: {exc}") from exc

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

"""Google Gemini free-tier provider.

Gemini uses a request/response shape that differs from OpenAI's format.
The provider maps OpenAI-style ``messages`` to Gemini's ``contents``
schema and parses the ``streamGenerateContent`` response.

* Base URL: ``https://generativelanguage.googleapis.com/v1beta``
* Auth: ``GEMINI_API_KEY`` env var
* Endpoint: ``/models/{model}:streamGenerateContent?key={api_key}``
* Docs: https://ai.google.dev/gemini-api/docs
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

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
_DEFAULT_MODEL = "gemini-2.0-flash-lite"
_BUILTIN_MODELS = [
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
]

_HTTP_UNAUTHORIZED = 400  # Gemini returns 400 for invalid API key
_HTTP_RATE_LIMIT = 429


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _map_role(role: str) -> str:
    """Map OpenAI role names to Gemini role names.

    Args:
        role: OpenAI-style role (``user``, ``assistant``, ``system``).

    Returns:
        Gemini-compatible role string.
    """
    # Gemini only supports "user" and "model" roles.
    # System instructions are handled via the ``systemInstruction`` field.
    if role == "assistant":
        return "model"
    return "user"


def _build_contents(
    messages: list[dict[str, str]],
) -> tuple[dict[str, str] | None, list[dict[str, Any]]]:
    """Separate system prompt from user/assistant messages.

    Args:
        messages: OpenAI-style message list.

    Returns:
        A tuple of ``(system_instruction, contents)``.
    """
    system_instruction: dict[str, str] | None = None
    contents: list[dict[str, Any]] = []

    for msg in messages:
        role = msg.get("role", "user")
        text = msg.get("content", "")
        if role == "system":
            system_instruction = {"parts": [{"text": text}]}
        else:
            contents.append({
                "role": _map_role(role),
                "parts": [{"text": text}],
            })

    return system_instruction, contents


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

class GeminiProvider(BaseProvider):
    """Google Gemini inference provider (free tier).

    Args:
        api_key: Gemini API key.  Falls back to the ``GEMINI_API_KEY``
            environment variable.
        base_url: Override the default base URL.
        default_model: Override the default model.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self._base_url = (base_url or _BASE_URL).rstrip("/")
        self._default_model = default_model or _DEFAULT_MODEL

    # -- BaseProvider interface ------------------------------------------

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def available_models(self) -> list[str]:
        return list(_BUILTIN_MODELS)

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

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
        """Send chat request and yield response text chunks.

        The Gemini ``streamGenerateContent`` endpoint returns a stream of
        JSON objects (one per line).  Each object contains nested
        ``candidates -> content -> parts`` arrays where text lives in
        ``parts[*].text``.
        """
        model_name = model or self._default_model
        system_instruction, contents = _build_contents(messages)

        request_body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "text/plain",
            },
        }
        if system_instruction is not None:
            request_body["systemInstruction"] = system_instruction
        if max_tokens is not None:
            request_body["generationConfig"]["maxOutputTokens"] = max_tokens

        if not self._api_key:
            raise AIAuthError("Gemini API key is required. Set GEMINI_API_KEY env var.")

        endpoint = f"models/{model_name}:streamGenerateContent"
        url = f"{self._base_url}/{endpoint}?key={self._api_key}"
        headers = {"Content-Type": "application/json"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=request_body) as resp:
                    # ---- error handling --------------------------------
                    if resp.status == _HTTP_UNAUTHORIZED:
                        body = await resp.text()
                        raise AIAuthError(
                            f"Gemini auth failed ({resp.status}): {body}"
                        )
                    if resp.status == _HTTP_RATE_LIMIT:
                        body = await resp.text()
                        raise AIRateLimitError(
                            f"Gemini rate limit exceeded: {body}"
                        )
                    if resp.status >= 400:
                        body = await resp.text()
                        raise AIError(f"Gemini HTTP {resp.status}: {body}")

                    # ---- streaming response ----------------------------
                    # Gemini returns one JSON object per line (NDJSON)
                    buffer = b""
                    async for chunk_bytes in resp.content:
                        buffer += chunk_bytes
                        # Process complete lines
                        while b"\n" in buffer:
                            line, buffer = buffer.split(b"\n", 1)
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                data = json.loads(line.decode("utf-8"))
                                for candidate in data.get("candidates", []):
                                    content = candidate.get("content", {})
                                    for part in content.get("parts", []):
                                        text = part.get("text")
                                        if text:
                                            yield text
                            except (json.JSONDecodeError, UnicodeDecodeError):
                                continue

        except (AIAuthError, AIRateLimitError, AIError):
            raise
        except aiohttp.ClientError as exc:
            raise AINetworkError(f"Gemini network error: {exc}") from exc
        except TimeoutError as exc:
            raise AINetworkError(f"Gemini request timed out: {exc}") from exc

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
            stream=True,  # Gemini always streams; we buffer
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            parts.append(chunk)
        return "".join(parts)

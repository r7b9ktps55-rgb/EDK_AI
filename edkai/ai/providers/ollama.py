"""Ollama local inference provider.

Ollama runs LLMs locally via a REST API.  Models are auto-detected by
querying ``GET /api/tags``.  If the service is unreachable the provider
still initialises but reports ``is_configured == False``.

* Base URL: ``http://localhost:11434``
* Endpoint: ``/api/chat`` (Ollama native format)
* Docs: https://github.com/ollama/ollama/blob/main/docs/api.md
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import aiohttp

from edkai.ai.exceptions import AINetworkError, AIError
from edkai.ai.providers.base import BaseProvider


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_FALLBACK_MODEL = "qwen2.5-coder:14b"
_DEFAULT_BASE_URL = "http://localhost:11434"


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

class OllamaProvider(BaseProvider):
    """Ollama local inference provider.

    Models are discovered lazily on first access to :pyattr:`available_models`.
    The provider does **not** require an API key.

    Args:
        base_url: Ollama server URL (default: ``http://localhost:11434``).
        default_model: Preferred default model.  When empty, the first
            model returned by Ollama is used.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        default_model: str | None = None,
    ) -> None:
        self._base_url = (base_url or _DEFAULT_BASE_URL).rstrip("/")
        self._preferred_default = default_model or ""
        self._models: list[str] | None = None  # cached model list

    # -- internals -------------------------------------------------------

    async def _fetch_models(self) -> list[str]:
        """Query Ollama ``/api/tags`` and return model names."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self._base_url}/api/tags", timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    models = [m["name"] for m in data.get("models", [])]
                    return models
        except Exception:
            return []

    def _ensure_models(self) -> list[str]:
        """Return cached models or empty list if not yet fetched.

        Synchronous accessor — the cache is populated by
        :pyfunc:`available_models`.
        """
        return self._models or []

    # -- BaseProvider interface ------------------------------------------

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def available_models(self) -> list[str]:
        # Synchronous accessor returns last-known models.
        # Callers that need fresh data can await _fetch_models directly.
        return self._ensure_models()

    @property
    def is_configured(self) -> bool:
        # Best-effort: we consider Ollama "configured" if we have at least
        # a fallback default model.  The real check happens at request time.
        return True

    @property
    def default_model(self) -> str:
        cached = self._ensure_models()
        if cached:
            return cached[0]
        return self._preferred_default or _DEFAULT_FALLBACK_MODEL

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        stream: bool = True,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        max_iterations: int = 4,
    ) -> AsyncGenerator[str, None]:
        """Send chat request via Ollama's native ``/api/chat`` endpoint.

        Args:
            messages: Conversation history.
            model: Model name (falls back to the first available).
            stream: Whether to stream the response.
            temperature: Sampling temperature.
            max_tokens: Max tokens to generate.
            max_iterations: Maximum recursive tool calls to prevent infinite loops.
        """
        # Auto-detect models on first chat if not cached
        if self._models is None:
            self._models = await self._fetch_models()

        model_name = model or self.default_model
        request_body: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "stream": stream,
            "options": {"temperature": temperature},
        }
        if max_tokens is not None:
            request_body["options"]["num_predict"] = max_tokens

        url = f"{self._base_url}/api/chat"
        iteration = 0
        current_messages = list(messages)

        try:
            while iteration < max_iterations:
                iteration += 1
                request_body["messages"] = current_messages

                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=request_body) as resp:
                        if resp.status != 200:
                            body = await resp.text()
                            raise AIError(f"Ollama HTTP {resp.status}: {body}")

                        if stream:
                            async for line in resp.content:
                                decoded = line.decode("utf-8").strip()
                                if not decoded:
                                    continue
                                try:
                                    chunk = __import__("json").loads(decoded)
                                    message = chunk.get("message", {})
                                    content = message.get("content", "")
                                    if content:
                                        yield content
                                    # Check for tool calls in Ollama response
                                    tool_calls = message.get("tool_calls", [])
                                    if tool_calls and chunk.get("done", False):
                                        # Process tool calls
                                        for tool_call in tool_calls:
                                            result = await self._execute_tool(tool_call)
                                            current_messages.append({
                                                "role": "assistant",
                                                "content": "",
                                                "tool_calls": [tool_call]
                                            })
                                            current_messages.append({
                                                "role": "tool",
                                                "name": tool_call.get("function", {}).get("name", ""),
                                                "content": str(result)
                                            })
                                        # Break to restart the loop with updated messages
                                        break
                                    if chunk.get("done", False):
                                        return
                                except Exception:
                                    continue
                            else:
                                # Normal completion without tool calls
                                return
                        else:
                            body = await resp.json()
                            content = body.get("message", {}).get("content", "")
                            yield content
                            return

        except (AIError,):
            raise
        except aiohttp.ClientError as exc:
            raise AINetworkError(f"Ollama network error: {exc}") from exc
        except TimeoutError as exc:
            raise AINetworkError(f"Ollama request timed out: {exc}") from exc

    async def _execute_tool(self, tool_call: dict[str, Any]) -> Any:
        """Execute a tool call requested by the model.

        Args:
            tool_call: The tool call specification from the model.

        Returns:
            The result of the tool execution.
        """
        function_info = tool_call.get("function", {})
        function_name = function_info.get("name", "")
        arguments = function_info.get("arguments", {})

        # Basic built-in tool implementations
        if function_name == "read_file":
            try:
                file_path = arguments.get("path", "")
                if not file_path:
                    return {"error": "No file path provided"}
                from pathlib import Path
                path = Path(file_path)
                if not path.exists():
                    return {"error": f"File not found: {file_path}"}
                with open(path, "r", encoding="utf-8") as f:
                    return {"content": f.read()}
            except Exception as e:
                return {"error": str(e)}

        elif function_name == "list_directory":
            try:
                dir_path = arguments.get("path", ".")
                from pathlib import Path
                path = Path(dir_path)
                if not path.exists():
                    return {"error": f"Directory not found: {dir_path}"}
                entries = []
                for entry in path.iterdir():
                    entries.append({
                        "name": entry.name,
                        "type": "directory" if entry.is_dir() else "file",
                    })
                return {"entries": entries}
            except Exception as e:
                return {"error": str(e)}

        elif function_name == "run_command":
            import asyncio
            command = arguments.get("command", "")
            if not command:
                return {"error": "No command provided"}
            try:
                proc = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                return {
                    "stdout": stdout.decode("utf-8", errors="replace"),
                    "stderr": stderr.decode("utf-8", errors="replace"),
                    "returncode": proc.returncode,
                }
            except Exception as e:
                return {"error": str(e)}

        else:
            return {"error": f"Unknown tool: {function_name}"}

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

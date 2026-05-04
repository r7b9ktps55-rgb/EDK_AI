"""Inline Generator — code from natural-language descriptions.

Converts inline human descriptions (e.g. "function to validate email")
into complete code blocks, and provides code-explanation capabilities.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from edkai.ai.client import AIClient, AIError, AINetworkError
from edkai.ai import prompts

logger = logging.getLogger(__name__)


class InlineGenerator:
    """Generates code from inline natural language descriptions.

    Attributes:
        client: The :class:`AIClient` used for completions.
    """

    def __init__(self, client: AIClient) -> None:
        """Initialise the inline generator.

        Args:
            client: An initialised :class:`AIClient`.
        """
        self.client = client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_from_description(
        self,
        description: str,
        language: str,
        file_context: Optional[str] = None,
    ) -> str:
        """Generate a code block from a natural-language description.

        Example::

            code = await generator.generate_from_description(
                "function to validate email with regex",
                "python",
            )

        Args:
            description: Human-readable task description.
            language: Target programming language.
            file_context: Optional surrounding file content for context.

        Returns:
            The generated code block, or an empty string on error.
        """
        prompt = prompts.inline_description_prompt(description, language, file_context)
        return await self._safe_complete(prompt, max_tokens=1200)

    async def explain_selection(
        self,
        code: str,
        language: str,
    ) -> str:
        """Return a human-readable explanation of selected code.

        Args:
            code: The selected source code snippet.
            language: Programming language.

        Returns:
            A plain-English explanation, or an empty string on error.
        """
        prompt = prompts.explain_selection_prompt(code, language)
        return await self._safe_complete(prompt, max_tokens=600)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _safe_complete(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Call ``client.complete`` with uniform error handling.

        Args:
            prompt: Prompt text.
            max_tokens: Optional token ceiling.

        Returns:
            Response text, or an empty string on any AI or network error.
        """
        try:
            return await self.client.complete(
                prompt,
                temperature=0.3,
                max_tokens=max_tokens,
            )
        except (AINetworkError, AIError) as exc:
            logger.warning("InlineGenerator completion error: %s", exc)
            return ""

"""AI-powered code refactoring engine.

Provides :class:`RefactorEngine` which applies high-level instructions
such as "extract to function" or "convert to list comprehension" to a
code snippet, as well as automatic optimisation.
"""

from __future__ import annotations
from typing import Optional

import logging

from edkai.ai.client import AIClient, AIError, AINetworkError
from edkai.ai import prompts

logger = logging.getLogger(__name__)


class RefactorEngine:
    """AI-powered code refactoring.

    Attributes:
        client: The :class:`AIClient` used for completions.
    """

    def __init__(self, client: AIClient) -> None:
        """Initialise the refactoring engine.

        Args:
            client: An initialised :class:`AIClient`.
        """
        self.client = client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def refactor_selection(
        self,
        code: str,
        instruction: str,
        language: str,
    ) -> str:
        """Refactor *code* according to a natural-language instruction.

        Supported instructions (examples)::

            - "extract to function"
            - "convert to list comprehension"
            - "add type hints"
            - "rename variables to snake_case"

        Args:
            code: The source code to refactor.
            instruction: Human-readable refactoring instruction.
            language: Programming language.

        Returns:
            The refactored code, or an empty string on error.
        """
        prompt = prompts.refactor_prompt(code, instruction, language)
        return await self._safe_complete(prompt, max_tokens=1200)

    async def optimize(
        self,
        code: str,
        language: str,
    ) -> str:
        """Return an optimised version of *code*.

        The LLM is asked to improve performance and clarity while
        preserving exact external behaviour.

        Args:
            code: The source code to optimise.
            language: Programming language.

        Returns:
            The optimised code, or an empty string on error.
        """
        prompt = prompts.optimize_prompt(code, language)
        return await self._safe_complete(prompt, max_tokens=1200)

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
                temperature=0.2,
                max_tokens=max_tokens,
            )
        except (AINetworkError, AIError) as exc:
            logger.warning("RefactorEngine completion error: %s", exc)
            return ""

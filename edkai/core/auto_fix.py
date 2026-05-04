"""Auto-fix engine for Terminal Studio.

Detects errors from test output or compilation, sends them to the AI for
diagnosis, and returns corrected code together with an explanation.
"""

from __future__ import annotations

import re
from typing import Any, List

from edkai.ai.client import AIClient, AIError
from edkai.ai import prompts


class AutoFixEngine:
    """Detects errors, sends to AI, applies fixes automatically.

    The engine works on source code plus an error output (traceback,
    compiler message, linter report, etc.) and leverages the
    :class:`AIClient` to produce corrected code or explanations.

    Attributes:
        client: The :class:`AIClient` instance used for completions.
    """

    def __init__(self, client: AIClient | None = None) -> None:
        """Initialise the auto-fix engine.

        Args:
            client: An :class:`AIClient` instance. If ``None``, a new default
                client is created.
        """
        self.client = client or AIClient()

    # ------------------------------------------------------------------
    # Core methods
    # ------------------------------------------------------------------

    async def diagnose_and_fix(
        self,
        code: str,
        error_output: str,
        language: str,
    ) -> tuple[str, str]:
        """Diagnose an error and return fixed code plus explanation.

        Args:
            code: The source code that produced the error.
            error_output: Error traceback, compiler output, or test failure.
            language: Programming language of *code*.

        Returns:
            A tuple of ``(fixed_code, explanation)``.

        Raises:
            AIError: On API or network failures.
        """
        prompt_text = prompts.auto_fix_prompt(code, error_output, language)

        try:
            response = await self.client.complete(
                prompt_text,
                temperature=0.3,
                max_tokens=4096,
            )
        except AIError:
            raise
        except Exception as exc:
            raise AIError(f"Unexpected error in diagnose_and_fix: {exc}") from exc

        fixed_code = self._extract_code_block(response)
        explanation = self._extract_explanation(response)
        return fixed_code, explanation

    async def diagnose_only(
        self,
        code: str,
        error_output: str,
        language: str,
    ) -> str:
        """Return an explanation of what's wrong without providing fixed code.

        Args:
            code: The source code that produced the error.
            error_output: Error traceback, compiler output, or test failure.
            language: Programming language of *code*.

        Returns:
            A human-readable diagnosis string.

        Raises:
            AIError: On API or network failures.
        """
        prompt_text = prompts.diagnose_only_prompt(code, error_output, language)

        try:
            response = await self.client.complete(
                prompt_text,
                temperature=0.3,
                max_tokens=2048,
            )
        except AIError:
            raise
        except Exception as exc:
            raise AIError(f"Unexpected error in diagnose_only: {exc}") from exc

        return response.strip()

    async def lint_and_fix(
        self,
        code: str,
        language: str,
    ) -> tuple[str, List[str]]:
        """Lint *code* and return cleaned code plus a list of issues.

        Args:
            code: The source code to lint.
            language: Programming language of *code*.

        Returns:
            A tuple of ``(fixed_code, list_of_issues)``.

        Raises:
            AIError: On API or network failures.
        """
        prompt_text = prompts.lint_fix_prompt(code, language)

        try:
            response = await self.client.complete(
                prompt_text,
                temperature=0.3,
                max_tokens=4096,
            )
        except AIError:
            raise
        except Exception as exc:
            raise AIError(f"Unexpected error in lint_and_fix: {exc}") from exc

        fixed_code = self._extract_code_block(response)
        issues = self._parse_bullet_list(response)
        return fixed_code, issues

    # ------------------------------------------------------------------
    # Response extraction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_code_block(text: str) -> str:
        """Extract the first fenced code block from *text*.

        Args:
            text: Raw text potentially containing markdown code fences.

        Returns:
            Code content without fences, or the original *text* stripped if
            no block is found.
        """
        pattern = re.compile(r"```(?:\w+)?\n(.*?)\n```", re.DOTALL)
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
        return text.strip()

    @staticmethod
    def _extract_explanation(text: str) -> str:
        """Extract the prose explanation that follows the code block.

        Args:
            text: Raw AI response.

        Returns:
            The trailing prose after the first code fence, or the entire
            *text* if no code block is present.
        """
        pattern = re.compile(r"```(?:\w+)?\n.*?\n```\s*(.*)", re.DOTALL)
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
        return text.strip()

    @staticmethod
    def _parse_bullet_list(text: str) -> List[str]:
        """Parse bullet lines from *text*.

        Args:
            text: Raw text with bullet lists.

        Returns:
            A list of bullet content strings.
        """
        lines: List[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("- "):
                lines.append(stripped[2:].strip())
            elif stripped.startswith("* "):
                lines.append(stripped[2:].strip())
        return lines

    def __repr__(self) -> str:
        """Return a developer-friendly representation."""
        return f"<{type(self).__name__} client={self.client!r}>"

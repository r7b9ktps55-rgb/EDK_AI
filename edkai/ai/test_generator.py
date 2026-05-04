"""AI-powered test generator for Terminal Studio.

Generates unit tests and edge-case descriptions for source code by leveraging
the :class:`AIClient` and structured prompts in :mod:`edkai.ai.prompts`.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from edkai.ai.client import AIClient, AIError
from edkai.ai import prompts


# Default test framework mapped by language.
DEFAULT_FRAMEWORKS: Dict[str, str] = {
    "python": "pytest",
    "javascript": "jest",
    "typescript": "jest",
    "rust": "cargo test",
    "go": "go test",
    "cpp": "googletest",
    "c": "googletest",
    "java": "junit",
}


class TestGenerator:
    """Generates unit tests for code using AI.

    Uses the :class:`AIClient` to send structured prompts and receives
    complete test-file content or edge-case descriptions.

    Attributes:
        client: The :class:`AIClient` instance used for completions.
    """

    def __init__(self, client: AIClient | None = None) -> None:
        """Initialise the test generator.

        Args:
            client: An :class:`AIClient` instance. If ``None``, a new default
                client is created.
        """
        self.client = client or AIClient()

    # ------------------------------------------------------------------
    # Framework helpers
    # ------------------------------------------------------------------

    @staticmethod
    def detect_framework(language: str, framework: Optional[str] = None) -> str:
        """Return the test framework for *language*.

        If *framework* is explicitly supplied it is returned unchanged.
        Otherwise the default framework for *language* is used.

        Args:
            language: Programming language name (e.g. ``"python"``).
            framework: Optional explicit framework override.

        Returns:
            The resolved test framework name.
        """
        if framework:
            return framework
        return DEFAULT_FRAMEWORKS.get(language.lower(), "pytest")

    # ------------------------------------------------------------------
    # Core generation methods
    # ------------------------------------------------------------------

    async def generate_tests(
        self,
        code: str,
        language: str,
        framework: Optional[str] = None,
    ) -> str:
        """Generate a complete test file for *code*.

        The method builds a prompt, sends it to the AI, and returns the
        raw response.  Callers should extract the fenced code block if
        they need pure test code.

        Args:
            code: Source code to test.
            language: Programming language of *code*.
            framework: Target test framework (auto-detected when omitted).

        Returns:
            Complete test file content as a string.

        Raises:
            AIError: On API or network failures.
        """
        resolved_fw = self.detect_framework(language, framework)
        prompt_text = prompts.generate_tests_prompt(code, language, resolved_fw)

        try:
            response = await self.client.complete(
                prompt_text,
                temperature=0.3,
                max_tokens=4096,
            )
        except AIError:
            raise
        except Exception as exc:
            raise AIError(f"Unexpected error generating tests: {exc}") from exc

        return response

    async def generate_edge_cases(
        self,
        code: str,
        language: str,
    ) -> List[str]:
        """Generate a list of edge-case descriptions for *code*.

        Args:
            code: Source code to analyse.
            language: Programming language of *code*.

        Returns:
            A list of edge-case description strings.

        Raises:
            AIError: On API or network failures.
        """
        prompt_text = prompts.generate_edge_cases_prompt(code, language)

        try:
            response = await self.client.complete(
                prompt_text,
                temperature=0.4,
                max_tokens=2048,
            )
        except AIError:
            raise
        except Exception as exc:
            raise AIError(f"Unexpected error generating edge cases: {exc}") from exc

        return self._parse_bullet_list(response)

    # ------------------------------------------------------------------
    # Response helpers
    # ------------------------------------------------------------------

    @staticmethod
    def extract_code_block(response: str) -> str:
        """Extract the first fenced code block from an AI response.

        Args:
            response: Raw AI response text.

        Returns:
            Code content without fences, or the original *response* if no
            block is found.
        """
        pattern = re.compile(r"```(?:\w+)?\n(.*?)\n```", re.DOTALL)
        match = pattern.search(response)
        if match:
            return match.group(1).strip()
        return response.strip()

    @staticmethod
    def _parse_bullet_list(response: str) -> List[str]:
        """Parse bullet lines from an AI response.

        Args:
            response: Raw AI response text.

        Returns:
            A list of bullet strings with the leading dash and whitespace
            stripped.
        """
        lines: List[str] = []
        for line in response.splitlines():
            stripped = line.strip()
            if stripped.startswith("- "):
                lines.append(stripped[2:].strip())
            elif stripped.startswith("* "):
                lines.append(stripped[2:].strip())
        return lines

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    async def generate_tests_clean(
        self,
        code: str,
        language: str,
        framework: Optional[str] = None,
    ) -> str:
        """Like :meth:`generate_tests` but extracts only the code block.

        Args:
            code: Source code to test.
            language: Programming language of *code*.
            framework: Target test framework (auto-detected when omitted).

        Returns:
            Clean test code without markdown fences.
        """
        raw = await self.generate_tests(code, language, framework)
        return self.extract_code_block(raw)

    def __repr__(self) -> str:
        """Return a developer-friendly representation."""
        return f"<{type(self).__name__} client={self.client!r}>"

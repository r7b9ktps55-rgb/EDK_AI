"""AI Ghost Engine for predictive inline code completions.

Provides :class:`GhostEngine` which sends contextual code snippets to an
LLM and returns short continuation strings (1-5 lines) that can be rendered
as dim "ghost" text after the cursor.
"""

from __future__ import annotations
from typing import Optional

import logging

from edkai.ai.client import AIClient, AIError, AINetworkError
from edkai.ai import prompts

logger = logging.getLogger(__name__)

# How many lines of context to send before the cursor.
_MAX_CONTEXT_LINES = 200
# Hard limit on returned suggestion length (lines).
_MAX_SUGGESTION_LINES = 5


class GhostEngine:
    """Provides predictive inline code completions using an LLM.

    Attributes:
        client: The :class:`AIClient` used for non-streaming completions.
    """

    def __init__(self, client: AIClient) -> None:
        """Initialise the ghost engine.

        Args:
            client: An initialised :class:`AIClient` instance.
        """
        self.client = client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def suggest(
        self,
        editor_text: str,
        cursor_line: int,
        cursor_col: int,
        language: str,
    ) -> Optional[str]:
        """Request a short code continuation from the LLM.

        The method extracts up to ``_MAX_CONTEXT_LINES`` before *cursor_line*
        and asks the model to continue the code with at most 5 lines.

        Args:
            editor_text: Full text of the editor buffer.
            cursor_line: 0-based line index of the cursor.
            cursor_col: 0-based column index of the cursor.
            language: Programming language label (e.g. ``"python"``).

        Returns:
            The suggested continuation text (1-5 lines), or ``None`` if the
            LLM returns nothing or an error occurs.
        """
        context = self._extract_context(editor_text, cursor_line, cursor_col)
        if not context.strip():
            return None

        prompt = prompts.ghost_suggestion_prompt(context, language)

        try:
            raw = await self.client.complete(
                prompt,
                temperature=0.3,
                max_tokens=120,
            )
        except AINetworkError as exc:
            logger.warning("Ghost suggestion network error: %s", exc)
            return None
        except AIError as exc:
            logger.warning("Ghost suggestion AI error: %s", exc)
            return None

        suggestion = self._clean_suggestion(raw)
        if not suggestion:
            return None

        return suggestion

    async def generate_from_comment(
        self,
        comment: str,
        language: str,
        context: Optional[str] = None,
    ) -> str:
        """Generate a full function/class from a comment description.

        Example::

            comment = "# parse CSV and return list of dicts"
            result  = await engine.generate_from_comment(comment, "python")

        Args:
            comment: Natural-language description (may include a comment
                token like ``#`` or ``//``).
            language: Target programming language.
            context: Optional surrounding file context.

        Returns:
            The generated code block, or an empty string on error.
        """
        prompt = prompts.generate_from_comment_prompt(comment, language, context)
        return await self._safe_complete(prompt, max_tokens=800)

    async def generate_docstring(
        self,
        code: str,
        language: str,
    ) -> str:
        """Generate a Google/NumPy style docstring for a function/class.

        Args:
            code: Function or class body (including signature).
            language: Programming language.

        Returns:
            The generated docstring text, or an empty string on error.
        """
        prompt = prompts.generate_docstring_prompt(code, language)
        return await self._safe_complete(prompt, max_tokens=300)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_context(
        self,
        editor_text: str,
        cursor_line: int,
        cursor_col: int,
    ) -> str:
        """Return code before the cursor, truncated to the last *N* lines.

        Args:
            editor_text: Full buffer text.
            cursor_line: 0-based line index.
            cursor_col: 0-based column index.

        Returns:
            The context string ending exactly at the cursor position.
        """
        lines = editor_text.splitlines()
        if not lines:
            return ""

        # Clamp cursor_line to valid range.
        cursor_line = max(0, min(cursor_line, len(lines) - 1))

        # Slice up to and including cursor_line.
        prefix_lines = lines[: cursor_line + 1]

        # Truncate the last line at cursor_col.
        last = prefix_lines[cursor_line]
        cursor_col = max(0, min(cursor_col, len(last)))
        prefix_lines[cursor_line] = last[:cursor_col]

        # Keep only the last N lines to stay within token budget.
        if len(prefix_lines) > _MAX_CONTEXT_LINES:
            prefix_lines = prefix_lines[-_MAX_CONTEXT_LINES:]

        return "\n".join(prefix_lines)

    def _clean_suggestion(self, raw: str) -> Optional[str]:
        """Sanitise the LLM raw output for ghost text.

        Strips markdown fences, trailing whitespace, and enforces the
        line-count ceiling.

        Args:
            raw: Raw text from the LLM.

        Returns:
            Cleaned suggestion or ``None`` if nothing usable remains.
        """
        text = raw.strip()
        # Remove leading markdown fences if present.
        for prefix in ("```python", "```py", "```js", "```ts", "```go", "```rust", "```c", "```cpp", "```"):
            if text.startswith(prefix):
                text = text[len(prefix):].lstrip()
                break
        # Remove trailing fence.
        if text.endswith("```"):
            text = text[:-3].rstrip()

        lines = text.splitlines()
        if not lines:
            return None

        # Enforce max suggestion length.
        if len(lines) > _MAX_SUGGESTION_LINES:
            lines = lines[:_MAX_SUGGESTION_LINES]
            text = "\n".join(lines)

        # Ensure we do not return only whitespace.
        if not any(line.strip() for line in lines):
            return None

        return text

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
            logger.warning("Ghost engine completion error: %s", exc)
            return ""

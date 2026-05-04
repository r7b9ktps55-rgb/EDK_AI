"""Natural language command engine for Terminal Studio.

Converts free-form natural language into structured editor actions using a
two-tier approach: fast keyword matching followed by an AI fallback for
complex or ambiguous input.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from edkai.ai.client import AIClient


@dataclass
class EditorAction:
    """A structured editor action parsed from natural language.

    Attributes:
        type: The action category, e.g. ``"insert_code"``, ``"goto_line"``,
            ``"search"``, ``"rename"``, ``"run"``, ``"open"``, ``"save"``,
            ``"explain"``, ``"generate"``.
        params: Arbitrary keyword parameters for the action.
        confidence: A float between ``0.0`` and ``1.0`` representing the
            parser's confidence in this interpretation.
    """

    type: str
    params: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0


class NLCommandEngine:
    """Converts natural language to editor actions.

    Uses keyword matching for known commands and falls back to the AI
    client for complex natural language that does not match a built-in
    pattern.

    Attributes:
        client: Optional :class:`AIClient` for AI-based parsing fallback.
    """

    def __init__(self, client: AIClient | None = None) -> None:
        """Initialise the NL command engine.

        Args:
            client: An AI client for fallback parsing.
        """
        self.client = client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def parse(self, command: str, context: Dict[str, Any]) -> EditorAction:
        """Parse a natural language command into an :class:`EditorAction`.

        The engine tries keyword matching first and falls back to the AI
        client when no pattern matches.

        Args:
            command: The natural language input, e.g.
                ``"create a function called sort"``.
            context: Additional editor context such as ``{"language": "python"}``.

        Returns:
            A structured :class:`EditorAction`.
        """
        action = self._keyword_parse(command, context)
        if action is not None:
            return action

        if self.client is not None:
            return await self._ai_parse(command, context)

        return EditorAction(
            type="unknown",
            params={"raw": command},
            confidence=0.0,
        )

    # ------------------------------------------------------------------
    # Keyword matching tier
    # ------------------------------------------------------------------

    def _keyword_parse(
        self, command: str, context: Dict[str, Any]
    ) -> Optional[EditorAction]:
        """Fast keyword-based parser.

        Args:
            command: Lower-cased natural language input.
            context: Editor context.

        Returns:
            An :class:`EditorAction` if a pattern matched, otherwise ``None``.
        """
        lowered = command.lower().strip()

        # Go to line
        m = re.search(r"(?:go to |goto |jump to |line )(\d+)", lowered)
        if m:
            return EditorAction(
                type="goto_line",
                params={"line": int(m.group(1))},
                confidence=1.0,
            )

        # Find / search
        if any(kw in lowered for kw in ("find", "search", "look for")):
            query = self._extract_quoted_or_rest(lowered, ("find", "search", "look for"))
            return EditorAction(
                type="search",
                params={"query": query},
                confidence=0.95,
            )

        # Replace / rename variable
        m = re.search(
            r"rename\s+(?:variable\s+)?['\"`]?(\w+)['\"`]?\s+to\s+['\"`]?(\w+)['\"`]?",
            lowered,
        )
        if m:
            return EditorAction(
                type="rename",
                params={"old": m.group(1), "new": m.group(2)},
                confidence=1.0,
            )

        # Run
        if any(lowered.startswith(kw) for kw in ("run", "execute", "start", "launch")):
            return EditorAction(
                type="run",
                params={"target": self._extract_quoted_or_rest(lowered, ("run", "execute", "start", "launch"))},
                confidence=0.9,
            )

        # Save
        if any(kw in lowered for kw in ("save", "write")):
            return EditorAction(type="save", confidence=1.0)

        # Open file
        m = re.search(
            r"(?:open|show)\s+(?:file\s+)?['\"`]?(.+?)['\"`]?(?:\s+file)?$",
            lowered,
        )
        if m:
            return EditorAction(
                type="open",
                params={"path": m.group(1).strip()},
                confidence=0.9,
            )

        # Create / insert code (function)
        m = re.search(
            r"create\s+(?:a\s+)?(?:function|method|def)\s+(?:called\s+)?['\"`]?(\w+)['\"`]?",
            lowered,
        )
        if m:
            func_name = m.group(1)
            language = context.get("language", "python")
            signature = self._build_function_signature(func_name, lowered, language)
            return EditorAction(
                type="insert_code",
                params={
                    "code": signature,
                    "language": language,
                },
                confidence=0.85,
            )

        # Create class
        m = re.search(
            r"create\s+(?:a\s+)?class\s+(?:called\s+)?['\"`]?(\w+)['\"`]?",
            lowered,
        )
        if m:
            class_name = m.group(1)
            language = context.get("language", "python")
            code = self._build_class_stub(class_name, language)
            return EditorAction(
                type="insert_code",
                params={"code": code, "language": language},
                confidence=0.85,
            )

        # Explain code
        if any(kw in lowered for kw in ("explain", "what does", "describe")):
            return EditorAction(type="explain", confidence=0.8)

        # Generate / implement
        if any(kw in lowered for kw in ("generate", "implement", "write")):
            return EditorAction(
                type="generate",
                params={
                    "task": command,
                    "language": context.get("language", "python"),
                },
                confidence=0.7,
            )

        # Toggle sidebar / terminal / ai panel
        if "toggle sidebar" in lowered:
            return EditorAction(type="toggle_sidebar", confidence=1.0)
        if any(kw in lowered for kw in ("toggle terminal", "show terminal", "hide terminal")):
            return EditorAction(type="toggle_terminal", confidence=1.0)
        if any(kw in lowered for kw in ("toggle ai", "show ai", "hide ai")):
            return EditorAction(type="toggle_ai", confidence=1.0)

        return None

    # ------------------------------------------------------------------
    # AI fallback tier
    # ------------------------------------------------------------------

    async def _ai_parse(
        self, command: str, context: Dict[str, Any]
    ) -> EditorAction:
        """Ask the AI to interpret a natural language command.

        Args:
            command: The raw user input.
            context: Editor context.

        Returns:
            A parsed :class:`EditorAction`.
        """
        language = context.get("language", "python")
        prompt = (
            "You are a natural-language command parser for a code editor.\n"
            "Convert the user's command into a JSON object with these keys:\n"
            "  type: one of [goto_line, search, insert_code, rename, run, open, save, explain, generate, unknown]\n"
            "  params: a flat dictionary of parameters\n"
            "Respond with ONLY the JSON object, no markdown fences.\n\n"
            f"Language context: {language}\n"
            f"Command: {command}\n"
        )
        try:
            result = await self.client.complete(  # type: ignore[union-attr]
                prompt,
                temperature=0.1,
                max_tokens=256,
            )
            result = result.strip()
            import json

            data = json.loads(result)
            return EditorAction(
                type=data.get("type", "unknown"),
                params=data.get("params", {}),
                confidence=0.75,
            )
        except Exception:  # noqa: BLE001
            return EditorAction(
                type="unknown",
                params={"raw": command},
                confidence=0.0,
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_quoted_or_rest(text: str, prefixes: tuple[str, ...]) -> str:
        """Remove known prefixes and return the remainder as a query.

        Strips surrounding quotes if present.
        """
        lower = text.lower()
        for prefix in prefixes:
            if lower.startswith(prefix):
                remainder = text[len(prefix):].strip()
                break
        else:
            # find first occurrence anywhere
            for prefix in prefixes:
                idx = lower.find(prefix)
                if idx != -1:
                    remainder = text[idx + len(prefix):].strip()
                    break
            else:
                remainder = text
        # Strip quotes
        if (remainder.startswith('"') and remainder.endswith('"')) or \
           (remainder.startswith("'") and remainder.endswith("'")) or \
           (remainder.startswith("`") and remainder.endswith("`")):
            remainder = remainder[1:-1]
        return remainder.strip()

    @staticmethod
    def _build_function_signature(name: str, text: str, language: str) -> str:
        """Generate a minimal function signature stub.

        Args:
            name: Function name.
            text: The original natural language text (to guess args).
            language: Target programming language.

        Returns:
            A short code stub.
        """
        if language in ("python", "py"):
            # Try to guess arguments from "that takes a list" etc.
            args = ""
            if "takes a list" in text.lower() or "takes an list" in text.lower():
                args = "items"
            elif "takes a string" in text.lower():
                args = "text"
            elif "takes a number" in text.lower() or "takes an int" in text.lower():
                args = "n"
            elif "takes" in text.lower():
                # Generic arg
                args = "*args"
            return f"def {name}({args}):\n    ...\n"
        if language in ("javascript", "js", "typescript", "ts"):
            return f"function {name}() {{\n    // TODO\n}}\n"
        if language in ("go",):
            return f"func {name}() {{\n    // TODO\n}}\n"
        if language in ("rust", "rs"):
            return f"fn {name}() {{\n    // TODO\n}}\n"
        if language in ("c", "cpp", "cc"):
            return f"void {name}() {{\n    // TODO\n}}\n"
        return f"function {name}() {{\n    // TODO\n}}\n"

    @staticmethod
    def _build_class_stub(name: str, language: str) -> str:
        """Generate a minimal class stub.

        Args:
            name: Class name.
            language: Target programming language.

        Returns:
            A short code stub.
        """
        if language in ("python", "py"):
            return (
                f"class {name}:\n"
                "    def __init__(self):\n"
                "        ...\n"
            )
        if language in ("javascript", "js", "typescript", "ts"):
            return (
                f"class {name} {{\n"
                "    constructor() {\n"
                "        // TODO\n"
                "    }\n"
                "}\n"
            )
        if language in ("java",):
            return (
                f"public class {name} {{\n"
                "    public {name}() {\n"
                "        // TODO\n"
                "    }\n"
                "}\n"
            )
        if language in ("go",):
            return (
                f"type {name} struct {{\n"
                "    // TODO\n"
                "}\n"
            )
        if language in ("rust", "rs"):
            return (
                f"pub struct {name};\n\n"
                f"impl {name} {{\n"
                "    // TODO\n"
                "}\n"
            )
        return f"class {name} {{\n    // TODO\n}}\n"

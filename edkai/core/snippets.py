"""Tab-triggered code templates with variable substitution for Terminal Studio.

The :class:`SnippetEngine` provides language-aware built-in snippets,
user-defined custom snippets, and AI-powered snippet generation for
unknown triggers.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from edkai.ai.client import AIClient

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

DEFAULT_SNIPPET_DIR = Path.home() / ".config" / "edkai" / "snippets"
DEFAULT_SNIPPET_PATH = DEFAULT_SNIPPET_DIR / "user_snippets.json"


# ---------------------------------------------------------------------------
# Type helpers
# ---------------------------------------------------------------------------

SnippetTemplate = Dict[str, Any]
MacroStep = Dict[str, Any]


# ---------------------------------------------------------------------------
# SnippetEngine
# ---------------------------------------------------------------------------

class SnippetEngine:
    """Tab-triggered code templates with variable substitution.

    Features:
    * Built-in language-aware snippets for common patterns.
    * Variable substitution (``$NAME``, ``$DATE``, ``$1``, ``$2``, …).
    * User-defined custom snippets loaded from JSON.
    * AI-powered expansion for unknown triggers.

    Example:
        >>> engine = SnippetEngine()
        >>> engine.expand("class", "python", {"FILENAME": "widget.py"})
        'class $NAME:\\n    def __init__(self):\n        ...\n'
    """

    _VAR_RE = re.compile(r"\$(\w+|\d+)")

    def __init__(self, ai_client: AIClient | None = None) -> None:
        """Initialise the snippet engine.

        Args:
            ai_client: Optional AI client for generating unknown snippets.
        """
        self._ai_client = ai_client
        self._builtins: Dict[str, dict[str, str]] = self._load_builtins()
        self._custom: Dict[str, dict[str, str]] = {}
        self._user_path: Path = DEFAULT_SNIPPET_PATH
        self.load_user_snippets(str(DEFAULT_SNIPPET_PATH))

    # ------------------------------------------------------------------
    # Built-in snippets
    # ------------------------------------------------------------------

    def _load_builtins(self) -> Dict[str, dict[str, str]]:
        """Return the hard-coded built-in snippet map.

        The top-level key is the trigger word.  Each trigger maps to a
        dict of ``{language: template_string}``.
        """
        return {
            "class": {
                "python": (
                    "class $NAME:\n"
                    "    def __init__(self):\n"
                    "        $1\n"
                    "\n"
                    "    def __repr__(self) -> str:\n"
                    "        return f\"$NAME()\"\n"
                ),
                "javascript": (
                    "class $NAME {\n"
                    "    constructor() {\n"
                    "        $1\n"
                    "    }\n"
                    "}\n"
                ),
                "typescript": (
                    "class $NAME {\n"
                    "    constructor() {\n"
                    "        $1\n"
                    "    }\n"
                    "}\n"
                ),
                "java": (
                    "public class $NAME {\n"
                    "    public $NAME() {\n"
                    "        $1\n"
                    "    }\n"
                    "}\n"
                ),
                "go": (
                    "type $NAME struct {\n"
                    "    $1\n"
                    "}\n"
                    "\n"
                    "func New$NAME() *$NAME {\n"
                    "    return &$NAME{}\n"
                    "}\n"
                ),
                "rust": (
                    "pub struct $NAME;\n"
                    "\n"
                    "impl $NAME {\n"
                    "    pub fn new() -> Self {\n"
                    "        $1\n"
                    "    }\n"
                    "}\n"
                ),
            },
            "func": {
                "python": (
                    "def $NAME($1):\n"
                    "    \"\"\"$2\"\"\"\n"
                    "    $3\n"
                ),
                "javascript": (
                    "function $NAME($1) {\n"
                    "    $2\n"
                    "}\n"
                ),
                "typescript": (
                    "function $NAME($1): $2 {\n"
                    "    $3\n"
                    "}\n"
                ),
                "go": (
                    "func $NAME($1) $2 {\n"
                    "    $3\n"
                    "}\n"
                ),
                "rust": (
                    "pub fn $NAME($1) -> $2 {\n"
                    "    $3\n"
                    "}\n"
                ),
                "java": (
                    "public $2 $NAME($1) {\n"
                    "    $3\n"
                    "}\n"
                ),
            },
            "def": {
                "python": (
                    "def $NAME($1):\n"
                    "    \"\"\"$2\"\"\"\n"
                    "    $3\n"
                ),
            },
            "for": {
                "python": (
                    "for $ITEM in $ITERABLE:\n"
                    "    $1\n"
                ),
                "javascript": (
                    "for (const $ITEM of $ITERABLE) {\n"
                    "    $1\n"
                    "}\n"
                ),
                "typescript": (
                    "for (const $ITEM of $ITERABLE) {\n"
                    "    $1\n"
                    "}\n"
                ),
                "go": (
                    "for _, $ITEM := range $ITERABLE {\n"
                    "    $1\n"
                    "}\n"
                ),
                "rust": (
                    "for $ITEM in $ITERABLE {\n"
                    "    $1\n"
                    "}\n"
                ),
                "java": (
                    "for ($TYPE $ITEM : $ITERABLE) {\n"
                    "    $1\n"
                    "}\n"
                ),
            },
            "ifmain": {
                "python": (
                    'if __name__ == "__main__":\n'
                    "    $1\n"
                ),
            },
            "try": {
                "python": (
                    "try:\n"
                    "    $1\n"
                    "except $EXCEPTION as e:\n"
                    "    $2\n"
                ),
                "javascript": (
                    "try {\n"
                    "    $1\n"
                    "} catch (e) {\n"
                    "    $2\n"
                    "}\n"
                ),
                "typescript": (
                    "try {\n"
                    "    $1\n"
                    "} catch (e: $EXCEPTION) {\n"
                    "    $2\n"
                    "}\n"
                ),
                "go": (
                    "if err != nil {\n"
                    "    $1\n"
                    "}\n"
                ),
                "rust": (
                    "match $EXPR {\n"
                    "    Ok($ITEM) => $1,\n"
                    "    Err(e) => $2,\n"
                    "}\n"
                ),
                "java": (
                    "try {\n"
                    "    $1\n"
                    "} catch ($EXCEPTION e) {\n"
                    "    $2\n"
                    "}\n"
                ),
            },
            "api": {
                "python": (
                    "@app.$METHOD(\"/$PATH\")\n"
                    "async def $NAME(request: Request):\n"
                    "    $1\n"
                    "    return JSONResponse({\"status\": \"ok\"})\n"
                ),
                "javascript": (
                    "app.$METHOD('/$PATH', async (req, res) => {\n"
                    "    $1\n"
                    "    res.json({ status: 'ok' });\n"
                    "});\n"
                ),
                "go": (
                    "func $NAME(w http.ResponseWriter, r *http.Request) {\n"
                    "    $1\n"
                    "    w.WriteHeader(http.StatusOK)\n"
                    "}\n"
                ),
            },
            "test": {
                "python": (
                    "def test_$NAME():\n"
                    "    # Arrange\n"
                    "    $1\n"
                    "    # Act\n"
                    "    result = $2\n"
                    "    # Assert\n"
                    "    assert result == $3\n"
                ),
                "javascript": (
                    "describe('$NAME', () => {\n"
                    "    it('should work', () => {\n"
                    "        $1\n"
                    "    });\n"
                    "});\n"
                ),
                "typescript": (
                    "describe('$NAME', () => {\n"
                    "    it('should work', () => {\n"
                    "        $1\n"
                    "    });\n"
                    "});\n"
                ),
                "go": (
                    "func Test$NAME(t *testing.T) {\n"
                    "    $1\n"
                    "}\n"
                ),
                "rust": (
                    "#[test]\n"
                    "fn test_$NAME() {\n"
                    "    $1\n"
                    "}\n"
                ),
            },
            "import": {
                "python": (
                    "import os\n"
                    "import sys\n"
                    "from pathlib import Path\n"
                    "\n"
                    "$1\n"
                ),
                "javascript": (
                    "import fs from 'fs';\n"
                    "import path from 'path';\n"
                    "\n"
                    "$1\n"
                ),
                "go": (
                    "import (\n"
                    '    "fmt"\n'
                    '    "os"\n'
                    ")\n"
                    "\n"
                    "$1\n"
                ),
                "rust": (
                    "use std::fs;\n"
                    "use std::path::PathBuf;\n"
                    "\n"
                    "$1\n"
                ),
            },
            "log": {
                "python": (
                    "import logging\n"
                    "\n"
                    "logger = logging.getLogger(__name__)\n"
                    "logging.basicConfig(\n"
                    '    level=logging.INFO,\n'
                    '    format="%(asctime)s [%(levelname)s] %(message)s",\n'
                    ")\n"
                    "\n"
                    "logger.info(\"$1\")\n"
                ),
                "javascript": (
                    "const logger = {\n"
                    "    info: (msg) => console.log(`[INFO] ${msg}`),\n"
                    "    error: (msg) => console.error(`[ERR] ${msg}`),\n"
                    "};\n"
                    "\n"
                    "logger.info('$1');\n"
                ),
                "go": (
                    "package main\n"
                    "\n"
                    'import "log"\n'
                    "\n"
                    "func main() {\n"
                    "    log.Println(\"$1\")\n"
                    "}\n"
                ),
            },
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def expand(
        self, trigger: str, language: str, context: Dict[str, str] | None = None
    ) -> Optional[str]:
        """Expand a trigger word into its snippet body.

        Resolution order:
        1. User custom snippets for the specific language.
        2. User custom snippets with ``language=None`` (global).
        3. Built-in snippets for the specific language.
        4. Built-in snippets for ``"python"`` (fallback).

        Variable substitution is applied after a template is resolved.

        Args:
            trigger: The trigger word typed by the user (e.g. ``"class"``).
            language: Programming language of the current file.
            context: Optional extra values for variable substitution.

        Returns:
            The expanded snippet text, or ``None`` if no template exists.
        """
        template = self._resolve_template(trigger, language)
        if template is None:
            return None
        return self._substitute_variables(template, language, context or {})

    def register_custom(
        self,
        trigger: str,
        template: str,
        language: Optional[str] = None,
    ) -> None:
        """Register a user-defined snippet.

        Args:
            trigger: The tab-trigger word.
            template: Snippet body with optional variables.
            language: Language scope, or ``None`` for global.
        """
        if trigger not in self._custom:
            self._custom[trigger] = {}
        key = language if language is not None else "__global__"
        self._custom[trigger][key] = template
        self._save_user_snippets()

    def load_user_snippets(self, path: str) -> None:
        """Load user snippets from a JSON file.

        The JSON format is::

            {
                "trigger": {
                    "language": "template",
                    "__global__": "fallback template"
                }
            }

        Args:
            path: Path to the JSON file. Parent directories are created
                if missing.
        """
        file_path = Path(path)
        self._user_path = file_path
        if not file_path.exists():
            return
        try:
            with open(file_path, "r", encoding="utf-8") as fh:
                data: Dict[str, Any] = json.load(fh)
            self._custom = {
                trigger: {
                    lang: tmpl for lang, tmpl in langs.items() if isinstance(tmpl, str)
                }
                for trigger, langs in data.items()
                if isinstance(langs, dict)
            }
        except (json.JSONDecodeError, OSError):
            self._custom = {}

    def list_snippets(self, language: str) -> List[tuple[str, str, str]]:
        """Return all available snippets for a language.

        Each tuple is ``(trigger, source, preview)`` where *source* is
        ``"builtin"`` or ``"custom"``.

        Args:
            language: Language filter.

        Returns:
            Sorted list of snippet descriptors.
        """
        results: List[tuple[str, str, str]] = []
        seen: set[str] = set()

        # Built-ins
        for trigger, lang_map in self._builtins.items():
            if language in lang_map or "python" in lang_map:
                seen.add(trigger)
                preview = self._preview(lang_map.get(language, lang_map.get("python", "")))
                results.append((trigger, "builtin", preview))

        # Custom (override or extend)
        for trigger, lang_map in self._custom.items():
            if language in lang_map or "__global__" in lang_map:
                seen.add(trigger)
                preview = self._preview(
                    lang_map.get(language, lang_map.get("__global__", ""))
                )
                # Replace previous entry if it existed
                results = [r for r in results if r[0] != trigger]
                results.append((trigger, "custom", preview))

        return sorted(results, key=lambda t: t[0])

    async def ai_expand(
        self, trigger: str, description: str, language: str
    ) -> str:
        """Generate a snippet via AI for an unknown trigger.

        Args:
            trigger: The trigger word the user typed.
            description: A short description of what the snippet should do.
            language: Target programming language.

        Returns:
            AI-generated snippet body.

        Raises:
            RuntimeError: If no AI client is configured.
        """
        if self._ai_client is None:
            raise RuntimeError("No AI client configured for snippet expansion")
        prompt = (
            f"Generate a single code snippet template for the trigger '{trigger}' "
            f"in {language}. The snippet should: {description}. "
            "Use $1, $2, etc. as tab stops and $NAME as a named variable. "
            "Return ONLY the snippet body with no markdown fences or explanation."
        )
        return await self._ai_client.complete(prompt, temperature=0.3, max_tokens=512)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_template(self, trigger: str, language: str) -> Optional[str]:
        """Return the raw template string for *trigger* and *language*."""
        # 1. Custom language-specific
        custom_map = self._custom.get(trigger, {})
        if language in custom_map:
            return custom_map[language]
        # 2. Custom global
        if "__global__" in custom_map:
            return custom_map["__global__"]
        # 3. Built-in language-specific
        builtin_map = self._builtins.get(trigger, {})
        if language in builtin_map:
            return builtin_map[language]
        # 4. Fallback to python or first available
        if "python" in builtin_map:
            return builtin_map["python"]
        if builtin_map:
            return next(iter(builtin_map.values()))
        return None

    def _substitute_variables(
        self, template: str, language: str, context: Dict[str, str]
    ) -> str:
        """Replace ``$VAR`` placeholders in *template*.

        Builtin variables (always available):
        * ``$DATE`` → ``YYYY-MM-DD``
        * ``$TIME`` → ``HH:MM:SS``
        * ``$DATETIME`` → ``YYYY-MM-DD HH:MM:SS``
        * ``$FILENAME`` → value from *context* or ``"untitled"``
        * ``$AUTHOR`` → value from *context* or ``""``

        Tab stops ``$1``, ``$2`` … are left as-is so the editor can
        navigate them.

        Args:
            template: Raw snippet body.
            language: Current language (used for some context hints).
            context: User-supplied variable overrides.

        Returns:
            Template with all named variables replaced.
        """
        now = datetime.now()
        builtins: Dict[str, str] = {
            "DATE": now.strftime("%Y-%m-%d"),
            "TIME": now.strftime("%H:%M:%S"),
            "DATETIME": now.strftime("%Y-%m-%d %H:%M:%S"),
            "FILENAME": context.get("FILENAME", "untitled"),
            "AUTHOR": context.get("AUTHOR", ""),
            "YEAR": str(now.year),
        }

        def replacer(match: re.Match[str]) -> str:
            key = match.group(1)
            if key.isdigit():
                return f"${key}"  # leave tab stops intact
            if key in context:
                return context[key]
            if key in builtins:
                return builtins[key]
            return match.group(0)  # keep unknown vars as-is

        return self._VAR_RE.sub(replacer, template)

    def _save_user_snippets(self) -> None:
        """Persist the current custom snippets to disk."""
        self._user_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._user_path, "w", encoding="utf-8") as fh:
            json.dump(self._custom, fh, indent=2)

    @staticmethod
    def _preview(template: str, max_len: int = 40) -> str:
        """Return a short one-line preview of *template*."""
        first = template.splitlines()[0] if template else ""
        first = first.strip()
        if len(first) > max_len:
            first = first[: max_len - 3] + "..."
        return first

    def get_tab_stops(self, text: str) -> List[tuple[int, int]]:
        """Find all ``$N`` tab-stop positions in *text*.

        Returns a list of ``(row, col)`` 0-based positions, sorted by
        tab-stop number.

        Args:
            text: Snippet body that may contain ``$1``, ``$2`` …

        Returns:
            Positions of each tab stop in document order.
        """
        stops: List[tuple[int, int, int]] = []  # (num, row, col)
        for row, line in enumerate(text.splitlines()):
            for match in re.finditer(r"\$(\d+)", line):
                num = int(match.group(1))
                col = match.start()
                stops.append((num, row, col))
        stops.sort(key=lambda t: (t[0], t[1], t[2]))
        return [(r, c) for _n, r, c in stops]

    def remove_tab_stop_markers(self, text: str) -> str:
        """Strip ``$N`` markers from *text*, leaving clean code.

        Args:
            text: Snippet body with tab-stop markers.

        Returns:
            Clean code without tab-stop markers.
        """
        return re.sub(r"\$(\d+)", "", text)

    def parse_named_vars(self, text: str) -> List[str]:
        """Return a list of named variable names used in *text*.

        Named variables are words that follow a ``$`` and are **not**
        numeric tab stops, e.g. ``$NAME`` → ``"NAME"``.

        Args:
            text: Snippet body to scan.

        Returns:
            Unique list of named variable identifiers in document order.
        """
        seen: set[str] = set()
        result: List[str] = []
        for match in self._VAR_RE.finditer(text):
            key = match.group(1)
            if not key.isdigit() and key not in seen:
                seen.add(key)
                result.append(key)
        return result

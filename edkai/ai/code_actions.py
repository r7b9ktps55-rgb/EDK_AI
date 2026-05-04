"""Context-aware code actions powered by AI.

Provides intelligent, cursor-context code actions such as generating
docstrings, tests, type hints, and refactoring suggestions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List

from edkai.ai.client import AIClient


@dataclass
class CodeAction:
    """A single context-aware code action.

    Attributes:
        name: Human-readable action label, e.g. ``"Generate Docstring"``.
        action_id: Machine-friendly identifier, e.g. ``"gen_docstring"``.
        kind: Category: ``"generate"``, ``"refactor"``, ``"fix"``, ``"organize"``.
        cursor_line: The 0-based line this action applies to.
        language: Programming language of the code.
    """

    name: str
    action_id: str
    kind: str
    cursor_line: int
    language: str


class CodeActionsEngine:
    """Context-aware code actions powered by AI.

    Scans the code around the cursor to infer what actions are relevant,
    then optionally uses the :class:`AIClient` to generate the actual
    code modifications.

    Attributes:
        client: Optional AI client for generative actions.
    """

    def __init__(self, client: AIClient | None = None) -> None:
        """Initialise the code-actions engine.

        Args:
            client: An AI client for generative actions.
        """
        self.client = client

    # ------------------------------------------------------------------
    # Action discovery
    # ------------------------------------------------------------------

    def get_actions(
        self, cursor_line: int, code: str, language: str
    ) -> List[CodeAction]:
        """Return context-aware actions for the cursor position.

        Inspects the line at *cursor_line* and nearby lines to decide
        which actions are applicable.

        Args:
            cursor_line: 0-based line index of the cursor.
            code: Full source code of the file.
            language: Programming language identifier.

        Returns:
            A list of :class:`CodeAction` objects.
        """
        lines = code.splitlines()
        actions: List[CodeAction] = []

        if not (0 <= cursor_line < len(lines)):
            return actions

        current = lines[cursor_line]
        stripped = current.strip()

        # --- Python-specific actions ---
        if language in ("python", "py"):
            # Function definition
            if stripped.startswith("def "):
                actions.extend([
                    CodeAction(
                        "Generate Docstring",
                        "gen_docstring",
                        "generate",
                        cursor_line,
                        language,
                    ),
                    CodeAction(
                        "Generate Tests",
                        "gen_tests",
                        "generate",
                        cursor_line,
                        language,
                    ),
                    CodeAction(
                        "Add Type Hints",
                        "add_types",
                        "generate",
                        cursor_line,
                        language,
                    ),
                ])
            # Class definition
            elif stripped.startswith("class "):
                actions.extend([
                    CodeAction(
                        "Generate __repr__",
                        "gen_repr",
                        "generate",
                        cursor_line,
                        language,
                    ),
                    CodeAction(
                        "Generate __eq__",
                        "gen_eq",
                        "generate",
                        cursor_line,
                        language,
                    ),
                    CodeAction(
                        "Generate Factory Method",
                        "gen_factory",
                        "generate",
                        cursor_line,
                        language,
                    ),
                ])
            # Import line
            elif stripped.startswith(("import ", "from ")):
                actions.extend([
                    CodeAction(
                        "Sort Imports",
                        "sort_imports",
                        "organize",
                        cursor_line,
                        language,
                    ),
                    CodeAction(
                        "Remove Unused Imports",
                        "remove_unused",
                        "organize",
                        cursor_line,
                        language,
                    ),
                ])
            # Variable / assignment
            elif "=" in stripped and not stripped.startswith("=="):
                actions.extend([
                    CodeAction(
                        "Extract Constant",
                        "extract_constant",
                        "refactor",
                        cursor_line,
                        language,
                    ),
                    CodeAction(
                        "Rename Variable",
                        "rename_var",
                        "refactor",
                        cursor_line,
                        language,
                    ),
                ])
            # Error patterns (simple heuristics)
            if any(kw in stripped.lower() for kw in ("raise", "except", "error", "todo", "fixme")):
                actions.extend([
                    CodeAction(
                        "Fix Error",
                        "fix_error",
                        "fix",
                        cursor_line,
                        language,
                    ),
                    CodeAction(
                        "Explain Error",
                        "explain_error",
                        "fix",
                        cursor_line,
                        language,
                    ),
                ])

        # --- JavaScript / TypeScript actions ---
        elif language in ("javascript", "js", "typescript", "ts"):
            if re.match(r"^\s*(?:function|const\s+\w+\s*=\s*(?:async\s+)?function|async\s+function)", stripped):
                actions.extend([
                    CodeAction("Generate JSDoc", "gen_jsdoc", "generate", cursor_line, language),
                    CodeAction("Generate Tests", "gen_tests", "generate", cursor_line, language),
                ])
            elif re.match(r"^\s*class\s+\w+", stripped):
                actions.extend([
                    CodeAction("Generate toString", "gen_tostring", "generate", cursor_line, language),
                    CodeAction("Generate Constructor", "gen_constructor", "generate", cursor_line, language),
                ])
            elif re.match(r"^\s*(?:import|const|let|var)\s+", stripped):
                actions.extend([
                    CodeAction("Organize Imports", "sort_imports", "organize", cursor_line, language),
                    CodeAction("Remove Unused", "remove_unused", "organize", cursor_line, language),
                ])

        # --- Rust actions ---
        elif language in ("rust", "rs"):
            if re.match(r"^\s*(?:fn|pub fn|async fn)", stripped):
                actions.extend([
                    CodeAction("Generate Documentation", "gen_docs", "generate", cursor_line, language),
                    CodeAction("Generate Tests", "gen_tests", "generate", cursor_line, language),
                ])
            elif re.match(r"^\s*(?:struct|pub struct|enum|pub enum)", stripped):
                actions.extend([
                    CodeAction("Generate Default impl", "gen_default", "generate", cursor_line, language),
                    CodeAction("Generate Debug", "gen_debug", "generate", cursor_line, language),
                ])

        # --- Generic actions (available for all languages) ---
        # If the line is empty or a comment, offer formatting.
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            actions.append(CodeAction(
                "Format Document", "format_doc", "organize", cursor_line, language
            ))

        return actions

    # ------------------------------------------------------------------
    # Action execution
    # ------------------------------------------------------------------

    async def execute_action(
        self, action: CodeAction, code: str
    ) -> str:
        """Execute a code action and return the modified code.

        Args:
            action: The :class:`CodeAction` to execute.
            code: Full source code of the file.

        Returns:
            The modified source code.
        """
        handler = self._get_handler(action.action_id)
        if handler is not None:
            return handler(action, code)

        # Fallback: use AI for generative actions when no built-in handler exists.
        if self.client is not None and action.kind == "generate":
            return await self._ai_generate(action, code)

        return code

    # ------------------------------------------------------------------
    # Built-in handlers
    # ------------------------------------------------------------------

    def _get_handler(
        self, action_id: str
    ) -> Any:
        """Return a handler function for a built-in action ID."""
        handlers: Dict[str, Any] = {
            "gen_docstring": self._gen_docstring,
            "gen_repr": self._gen_repr,
            "gen_eq": self._gen_eq,
            "sort_imports": self._sort_imports,
            "format_doc": self._format_doc,
        }
        return handlers.get(action_id)

    def _gen_docstring(self, action: CodeAction, code: str) -> str:
        """Insert a basic docstring under a Python function definition."""
        lines = code.splitlines()
        idx = action.cursor_line
        indent = self._get_indent(lines[idx])
        # Find the end of the signature (might span multiple lines).
        sig_end = idx
        while sig_end < len(lines) and ")" not in lines[sig_end]:
            sig_end += 1
        # Insert docstring after the signature line.
        insert_idx = sig_end + 1
        docstring = f'{indent}    """TODO: Document this function."""'
        lines.insert(insert_idx, docstring)
        return "\n".join(lines)

    def _gen_repr(self, action: CodeAction, code: str) -> str:
        """Insert a basic __repr__ into a Python class."""
        lines = code.splitlines()
        idx = action.cursor_line
        indent = self._get_indent(lines[idx])
        # Find class name.
        match = re.search(r"class\s+(\w+)", lines[idx])
        class_name = match.group(1) if match else "Class"
        method = [
            "",
            f'{indent}    def __repr__(self) -> str:',
            f'{indent}        return f"<{class_name}(...)>"',
        ]
        insert_idx = self._find_class_body_start(lines, idx)
        for i, line in enumerate(method):
            lines.insert(insert_idx + i, line)
        return "\n".join(lines)

    def _gen_eq(self, action: CodeAction, code: str) -> str:
        """Insert a basic __eq__ into a Python class."""
        lines = code.splitlines()
        idx = action.cursor_line
        indent = self._get_indent(lines[idx])
        method = [
            "",
            f'{indent}    def __eq__(self, other: object) -> bool:',
            f'{indent}        if not isinstance(other, self.__class__):',
            f'{indent}            return NotImplemented',
            f'{indent}        return self.__dict__ == other.__dict__',
        ]
        insert_idx = self._find_class_body_start(lines, idx)
        for i, line in enumerate(method):
            lines.insert(insert_idx + i, line)
        return "\n".join(lines)

    def _sort_imports(self, action: CodeAction, code: str) -> str:
        """Sort Python import lines alphabetically (builtin heuristic)."""
        lines = code.splitlines()
        import_lines: List[str] = []
        other_lines: List[str] = []
        for line in lines:
            if line.strip().startswith(("import ", "from ")):
                import_lines.append(line)
            else:
                other_lines.append(line)
        import_lines.sort(key=lambda s: s.strip().lower())
        return "\n".join(import_lines + [""] + other_lines)

    def _format_doc(self, action: CodeAction, code: str) -> str:
        """Basic formatting: strip trailing whitespace, ensure final newline."""
        lines = [r.rstrip() for r in code.splitlines()]
        result = "\n".join(lines)
        if not result.endswith("\n"):
            result += "\n"
        return result

    # ------------------------------------------------------------------
    # AI fallback
    # ------------------------------------------------------------------

    async def _ai_generate(self, action: CodeAction, code: str) -> str:
        """Use the AI client to generate code modifications.

        Args:
            action: The requested action.
            code: The full source file.

        Returns:
            Modified source code.
        """
        if self.client is None:
            return code
        prompt = (
            f"You are an expert {action.language} developer.\n"
            f"Perform the following code action: {action.name} ({action.action_id})\n"
            "Return the COMPLETE modified file. Do not omit any lines.\n\n"
            f"```\n{code}\n```"
        )
        try:
            result = await self.client.complete(
                prompt,
                temperature=0.2,
                max_tokens=2048,
            )
            # Extract code block if present.
            if "```" in result:
                parts = result.split("```")
                if len(parts) >= 3:
                    return parts[1].strip()
            return result.strip()
        except Exception:  # noqa: BLE001
            return code

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_indent(line: str) -> str:
        """Return the leading whitespace of a line."""
        return line[: len(line) - len(line.lstrip())]

    @staticmethod
    def _find_class_body_start(lines: List[str], class_line: int) -> int:
        """Return the index after the class definition line (and any docstring).

        Args:
            lines: Source lines.
            class_line: Line index where the class is defined.

        Returns:
            The index to insert a new method.
        """
        idx = class_line + 1
        # Skip the colon and any blank lines.
        while idx < len(lines) and not lines[idx].strip():
            idx += 1
        # If next line is a docstring, skip it.
        if idx < len(lines) and (lines[idx].strip().startswith('"""') or lines[idx].strip().startswith("'''")):
            # Simple single-line docstring skip; could be multi-line.
            idx += 1
            while idx < len(lines) and not (lines[idx].strip().endswith('"""') or lines[idx].strip().endswith("'''")):
                idx += 1
            idx += 1
        return idx

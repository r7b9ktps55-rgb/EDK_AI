"""Natural Language to Commands Router.

Converts plain language requests into structured tool commands.
Supports both Russian and English.

Examples:
    "покажи мне main.py" → ToolCall("read_file", {"path": "main.py"})
    "найди все TODO" → ToolCall("search_code", {"pattern": "TODO"})
    "запусти тесты" → ToolCall("shell", {"command": "pytest"})
    "сделай коммит с сообщением обновление" → ToolCall("git_commit", {"message": "обновление"})
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolCall:
    """A parsed tool call from natural language."""

    tool: str
    args: dict[str, Any]
    confidence: float = 1.0  # 1.0 = regex match, 0.5 = AI parsed
    explanation: str = ""  # What the user asked in plain words


# Common patterns that map directly to tools (FAST — no AI needed)
QUICK_PATTERNS: list[tuple[list[str], str, dict]] = [
    # Read file patterns — anchored with ^ to avoid matching suffixes
    # Extensions ordered longest-first to prevent partial matches (json before js, md before m)
    (
        [
            r"^(?:покажи мне|покажи|открой|прочитай|где)\s+(.+\.(?:jsx|tsx|json|toml|yaml|yml|css|scss|html|xml|sql|dockerfile|Makefile|py|js|ts|go|rs|java|c|cpp|h|hpp|rb|php|swift|kt|scala|sh|bash|zsh|fish|md|r|m|txt))",
            r"^(?:покажи мне|покажи|открой|прочитай|где)\s+(dockerfile|makefile)",
            r"^(?:show|open|read|view|display|cat)\s+(?:me\s+)?(.+\.(?:jsx|tsx|json|toml|yaml|yml|css|scss|html|xml|sql|dockerfile|Makefile|py|js|ts|go|rs|java|c|cpp|h|hpp|rb|php|swift|kt|scala|sh|bash|zsh|fish|md|r|m|txt))",
            r"^(?:show|open|read|view|display|cat)\s+(?:me\s+)?(dockerfile|makefile)",
            r"^what['']?s in\s+(.+\.(?:jsx|json|toml|yaml|yml|py|js|ts|go|rs|java|c|cpp|rb|php|md|r|m|txt))",
            r"^what['']?s in\s+(dockerfile|makefile)",
        ],
        "read_file",
        {},
    ),
    # Search code — more specific patterns first
    (
        [
            r"^find\s+(?:all\s+)?(?:instances? of|occurrences? of)\s+(.+)",
            r"^(?:найди|поищи|где|искать)\s+(?:вс[ёео]\s+)?(.+)",
            r"^(?:search for|find all|find|grep|locate|where is)\s+(.+)",
        ],
        "search_code",
        {},
    ),
    # List directory
    (
        [
            r"(?:список файлов|покажи файлы|что тут|что здесь|ls|dir)",
            r"(?:list files|show files|what['']?s here|directory listing|ls|dir)",
        ],
        "list_dir",
        {"path": "."},
    ),
    # Git status
    (
        [
            r"^(?:статус гита|гит статус|что изменилось)$",
            r"^(?:git status|what changed|any changes)$",
        ],
        "git_status",
        {},
    ),
    # Run tests
    (
        [
            r"(?:запусти|прогони)\s+(?:тесты|pytest|тестирование)",
            r"(?:run|execute)\s+(?:tests?|pytest|test suite)",
        ],
        "shell",
        {"command": "pytest -xvs"},
    ),
    # Run current file (Python)
    (
        [
            r"(?:запусти|выполни|run)\s+(?:этот\s+)?(?:файл|скрипт|file|script)",
            r"(?:run|execute)\s+(?:this\s+)?(?:file|script|program)",
        ],
        "shell",
        {"command": "python {current_file}"},
    ),
    # Run make
    (
        [
            r"(?:собери|сборка|make|build)",
            r"(?:build|compile|make)",
        ],
        "shell",
        {"command": "make"},
    ),
    # Git commit
    (
        [
            r"^(?:сделай коммит|закоммить|commit)(?:\s+с сообщением\s+(.+))?$",
            r"^(?:сделай коммит|закоммить|commit)\s+(.+)$",
            r"^(?:git\s+)?commit(?:\s+with message\s+(.+?))?$",
            r"^(?:git\s+)?commit\s+(.+)$",
        ],
        "git_commit",
        {},
    ),
    # Git push
    (
        [
            r"(?:пуш|запуш|push)",
            r"(?:git\s+)?push",
        ],
        "shell",
        {"command": "git push"},
    ),
    # Git pull
    (
        [
            r"(?:пулл|pull|обнови|update)",
            r"(?:git\s+)?pull",
        ],
        "shell",
        {"command": "git pull"},
    ),
    # Git log
    (
        [
            r"(?:история|лог|commits|log)",
            r"(?:git\s+)?(?:log|history)",
        ],
        "shell",
        {"command": "git log --oneline -10"},
    ),
    # Git add all
    (
        [
            r"(?:добавь все|git add|stage all)",
            r"(?:git\s+)?add\s+(?:all|\.|everything)",
        ],
        "shell",
        {"command": "git add -A"},
    ),
    # Git diff
    (
        [
            r"(?:разница|diff|что изменилось|изменения)",
            r"(?:git\s+)?diff",
        ],
        "shell",
        {"command": "git diff"},
    ),
    # Create file
    (
        [
            r"(?:создай файл|новый файл|touch)\s+(.+)",
            r"(?:create|new|touch)\s+(?:file\s+)?(.+)",
        ],
        "write_file",
        {"content": "# Created by Terminal Studio Agent\n"},
    ),
    # Delete file
    (
        [
            r"^(?:удали|remove|delete)\s+(?:(?:файл|file)\s+)?(.+)",
            r"^(?:delete|remove|rm)\s+(?:file\s+)?(.+)",
        ],
        "shell",
        {},
    ),
    # Install dependencies
    (
        [
            r"(?:установи|install)\s+(?:зависимости|deps|dependencies|requirements)",
            r"(?:install|pip install)\s+(?:deps|dependencies|requirements)",
        ],
        "shell",
        {"command": "pip install -r requirements.txt"},
    ),
    # Format code
    (
        [
            r"(?:форматируй|format|black| pretty)",
            r"(?:format|black|prettier)\s+(?:code)?",
        ],
        "shell",
        {"command": "black ."},
    ),
    # Lint
    (
        [
            r"(?:lint|проверь|flake|mypy|ruff)",
            r"(?:lint|check|flake8|mypy|ruff)",
        ],
        "shell",
        {"command": "ruff check ."},
    ),
    # Help
    (
        [
            r"(?:что ты умеешь|помощь|help|команды|умеешь)\??",
            r"(?:what can you do|help|commands|capabilities)\??",
        ],
        "help",
        {},
    ),
]


class NLRouter:
    """Routes natural language requests to tool commands."""

    def __init__(self, project_root: str = ".") -> None:
        self.project_root = project_root
        self.patterns = self._compile_patterns()

    def _compile_patterns(self) -> list[tuple[re.Pattern, str, dict]]:
        """Compile regex patterns for fast matching."""
        compiled = []
        for patterns, tool, default_args in QUICK_PATTERNS:
            for pattern in patterns:
                try:
                    compiled.append((re.compile(pattern, re.IGNORECASE), tool, default_args))
                except re.error:
                    continue
        return compiled

    def parse(self, user_input: str, context: dict[str, Any] | None = None) -> ToolCall | None:
        """Parse user input into a tool call.

        Returns ToolCall if matched, None if no pattern matched.

        Args:
            user_input: Raw user input text
            context: Optional context (current_file, project_root, etc.)

        Returns:
            ToolCall or None
        """
        ctx = context or {}
        user_input_lower = user_input.lower().strip()

        for regex, tool, defaults in self.patterns:
            match = regex.search(user_input)
            if match:
                args = dict(defaults)

                # Resolve {current_file} placeholder in default commands
                if tool == "shell" and "command" in args:
                    cmd = args["command"]
                    if "{current_file}" in cmd:
                        args["command"] = cmd.replace("{current_file}", ctx.get("current_file", ""))

                # Extract captured groups into args
                groups = match.groups()
                if groups and groups[0]:
                    captured = groups[0].strip().strip("\"'")

                    # Map capture to appropriate arg based on tool
                    if tool == "read_file":
                        args["path"] = captured
                    elif tool == "search_code":
                        args["pattern"] = captured
                    elif tool == "write_file":
                        args["path"] = captured
                    elif tool == "git_commit":
                        args["message"] = captured or "Update from Terminal Studio Agent"
                    elif tool == "shell":
                        args["command"] = f"rm {captured}"

                # Build explanation
                explanation = self._build_explanation(tool, args)

                return ToolCall(
                    tool=tool,
                    args=args,
                    confidence=1.0,
                    explanation=explanation,
                )

        return None

    def _build_explanation(self, tool: str, args: dict) -> str:
        """Build human-readable explanation of what will be done."""
        if tool == "read_file":
            return f"Read file: {args.get('path', '')}"
        elif tool == "search_code":
            return f"Search for: {args.get('pattern', '')}"
        elif tool == "shell":
            return f"Run: {args.get('command', '')}"
        elif tool == "git_commit":
            return f"Commit: {args.get('message', '')}"
        elif tool == "git_status":
            return f"Git status"
        elif tool == "list_dir":
            return f"List files in {args.get('path', '.')}"
        elif tool == "write_file":
            return f"Create file: {args.get('path', '')}"
        elif tool == "edit_file":
            return f"Edit file: {args.get('path', '')}"
        elif tool == "help":
            return f"Show help"
        return f"{tool}"

    async def parse_with_ai(
        self,
        user_input: str,
        ai_client: Any,
        context: dict[str, Any] | None = None,
    ) -> ToolCall | None:
        """Use AI to parse complex natural language requests.

        Only called when regex patterns don't match.

        Args:
            user_input: Raw user input
            ai_client: AI client for parsing
            context: Optional context

        Returns:
            ToolCall or None
        """
        ctx = context or {}

        system_prompt = """You are a command parser. Convert the user's request into a JSON tool call.
Available tools:
- read_file(path, offset, limit) — Read file contents
- write_file(path, content) — Write/create file
- edit_file(path, old_string, new_string) — Replace text in file
- shell(command, timeout) — Run shell command
- search_code(pattern, path) — Search in code
- search_files(pattern, path) — Find files by name
- list_dir(path) — List directory
- git_status() — Git status
- git_commit(message, files) — Git commit

Respond ONLY with valid JSON:
{"tool": "tool_name", "args": {"param": "value"}}

If no tool matches, respond: {"tool": "chat", "args": {"message": "..."}}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Parse this request: {user_input}\nContext: current_file={ctx.get('current_file', 'unknown')}",
            },
        ]

        try:
            response = ""
            async for chunk in ai_client.chat(messages, stream=False):
                response += chunk

            result = json.loads(response.strip())
            tool = result.get("tool", "chat")
            args = result.get("args", {})

            if tool == "chat":
                return ToolCall(
                    tool="chat",
                    args=args,
                    confidence=0.5,
                    explanation=args.get("message", user_input),
                )

            return ToolCall(
                tool=tool,
                args=args,
                confidence=0.5,
                explanation=self._build_explanation(tool, args),
            )
        except Exception:
            return None


def get_help_text() -> str:
    """Return help text showing available NL commands."""
    return """
I understand these commands (English + Russian):

Files:
  "покажи main.py" / "show me app.py" — Read file
  "создай файл test.py" / "create file" — Create file
  "удали old.py" / "delete temp.txt" — Delete file
  "список файлов" / "list files" — List directory

Search:
  "найди TODO" / "search for function" — Search code
  "где класс App" / "where is class App" — Find in code

Run:
  "запусти тесты" / "run tests" — Run pytest
  "запусти файл" / "run this file" — Run current file
  "собери" / "build" — Run make
  "установи зависимости" / "install deps" — pip install

Git:
  "статус гита" / "git status" — Git status
  "сделай коммит обновление" / "commit update" — Commit
  "пуш" / "push" — Git push
  "пулл" / "pull" — Git pull
  "история" / "log" — Git log
  "разница" / "diff" — Git diff

Other:
  "форматируй" / "format" — Format code
  "lint" — Lint code
  "что ты умеешь" / "help" — This help

Or just ask me anything in natural language!
"""

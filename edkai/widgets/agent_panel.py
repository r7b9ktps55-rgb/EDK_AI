"""Beautiful Agent REPL panel for Terminal Studio.

A gorgeous, feature-rich AI agent chat interface with syntax highlighting,
rich message formatting, model switching, and provider status display.

Example:
    >>> from edkai.widgets.agent_panel import AgentPanel
    >>> agent = AgentPanel(orchestrator=my_orchestrator)
    >>> await agent.mount()  # Panel renders beautifully in the TUI
"""
from __future__ import annotations

import asyncio
import re
import time
from collections.abc import AsyncGenerator
from typing import Any

from rich.console import Group
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from textual.app import ComposeResult
from textual.color import Color
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Button, Input, Label, ProgressBar, RichLog, Select, Static


class AgentPanel(Static):
    """Beautiful Agent REPL panel with provider status and model switching.

    Provides a rich chat interface for interacting with AI agents, featuring
    syntax-highlighted code blocks, tool call display, and beautiful styling.

    Args:
        agent_orchestrator: Optional orchestrator that handles AI message processing.
        **kwargs: Additional arguments passed to Static.

    Attributes:
        provider_name: Currently selected AI provider (reactive).
        model_name: Currently selected model identifier (reactive).
        is_processing: Whether the agent is currently generating a response (reactive).
        messages: List of conversation messages as dictionaries (reactive).
    """

    # ── Styling ──────────────────────────────────────────────────────────

    CSS = """
    /* ═══════════════════════════════════════════════════════════════
       AgentPanel — Main Container
       ═══════════════════════════════════════════════════════════════ */
    AgentPanel {
        width: 100%;
        height: 100%;
        background: $surface-darken-1;
        border: solid $primary 60%;
        padding: 0;
    }

    /* ── Header Bar ─────────────────────────────────────────────── */
    #agent-header {
        width: 100%;
        height: 3;
        background: $primary-darken-2 80%;
        color: $text;
        padding: 0 2;
        content-align: center middle;
        border-bottom: solid $primary 40%;
    }

    #agent-title {
        width: auto;
        text-style: bold;
        color: $text-accent;
        content-align: left middle;
    }

    #agent-status-dot {
        width: auto;
        color: $success;
        text-style: bold;
        content-align: center middle;
        padding: 0 1;
    }

    #agent-provider {
        width: auto;
        color: $success;
        text-style: bold;
        content-align: center middle;
    }

    #agent-at {
        width: auto;
        color: $text-disabled;
        text-style: dim;
        content-align: center middle;
        padding: 0 1;
    }

    #agent-model {
        width: auto;
        color: $warning;
        text-style: italic;
        content-align: center middle;
    }

    #agent-progress {
        width: auto;
        height: 1;
        padding: 0 1;
        display: none;
        content-align: center middle;
    }

    #agent-progress.visible {
        display: block;
    }

    /* ── Chat History (RichLog) ─────────────────────────────────── */
    #agent-chat {
        width: 100%;
        height: 1fr;
        background: $surface-darken-1;
        border: none;
        padding: 0 1;
        scrollbar-size: 1 1;
        scrollbar-background: $surface;
        scrollbar-color: $primary-darken-2;
    }

    /* ── Input Row ──────────────────────────────────────────────── */
    #agent-input-row {
        width: 100%;
        height: auto;
        min-height: 3;
        max-height: 8;
        dock: bottom;
        border-top: solid $primary 50%;
        padding: 0 1;
        background: $surface-darken-2;
    }

    #agent-prompt {
        width: 3;
        color: $success;
        text-style: bold;
        content-align: center middle;
    }

    #agent-input {
        width: 1fr;
        height: auto;
        min-height: 3;
        border: none;
        background: $surface-darken-1;
    }

    /* ── Toolbar ────────────────────────────────────────────────── */
    #agent-toolbar {
        width: 100%;
        height: 1;
        dock: bottom;
        background: $surface-darken-2;
        padding: 0 2;
        color: $text-disabled;
    }

    #toolbar-help {
        color: $text-disabled;
        text-style: dim;
        content-align: center middle;
    }

    #toolbar-shortcuts {
        color: $text-disabled 60%;
        text-style: dim italic;
        content-align: right middle;
    }

    /* ── Status Variants ────────────────────────────────────────── */
    .agent-status-idle {
        color: $success;
    }

    .agent-status-busy {
        color: $warning;
    }

    .agent-status-error {
        color: $error;
    }
    """

    # ── Reactive State ───────────────────────────────────────────────────

    provider_name: reactive[str] = reactive("GitHub")
    model_name: reactive[str] = reactive("phi-4")
    is_processing: reactive[bool] = reactive(False)
    messages: reactive[list[dict]] = reactive(list)

    # ── Color Palette for Message Styling ────────────────────────────────

    _COLOR_USER = "bold bright_green"
    _COLOR_AI = "bold bright_blue"
    _COLOR_SYSTEM = "bold bright_yellow"
    _COLOR_TOOL = "bold bright_cyan"
    _COLOR_ERROR = "bold bright_red"
    _COLOR_CODE_LANG = "bold magenta"
    _COLOR_TIMESTAMP = "dim grey50"
    _COLOR_DIM = "dim grey42"
    _COLOR_SEPARATOR = "dim grey35"
    _COLOR_HEADER = "bold bright_magenta"
    _COLOR_ACCENT = "bold bright_cyan"

    _SYNTAX_THEME = "monokai"

    # ── Initialization ───────────────────────────────────────────────────

    def __init__(self, agent_orchestrator: Any = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._orchestrator = agent_orchestrator
        self._start_time: float = 0.0
        self._message_count: int = 0

    # ── Composition ──────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        """Build the widget tree.

        Layout (top to bottom):
            1. Header bar — title, status dot, provider, model
            2. Chat history — RichLog for scrollable message display
            3. Input row — prompt symbol + text input
            4. Toolbar — command help and keyboard shortcuts
        """
        # ── Header ─────────────────────────────────────────────────────
        with Horizontal(id="agent-header"):
            yield Label("Terminal Studio Agent", id="agent-title")
            yield Label("●", id="agent-status-dot")
            yield Label(self.provider_name, id="agent-provider")
            yield Label("@", id="agent-at")
            yield Label(self.model_name, id="agent-model")

        # ── Chat History ───────────────────────────────────────────────
        yield RichLog(id="agent-chat", highlight=True, markup=True, wrap=True)

        # ── Input ──────────────────────────────────────────────────────
        with Horizontal(id="agent-input-row"):
            yield Label("❯", id="agent-prompt")
            yield Input(
                placeholder="Ask anything...  Ctrl+Enter to submit  ·  /help for commands",
                id="agent-input",
            )

        # ── Toolbar ────────────────────────────────────────────────────
        with Horizontal(id="agent-toolbar"):
            yield Label(
                "/help  ·  /reset  ·  /models  ·  /providers  ·  /exit",
                id="toolbar-help",
            )
            yield Label(
                "Ctrl+Enter submit  ·  Ctrl+L clear  ·  ↑↓ history",
                id="toolbar-shortcuts",
            )

    # ── Lifecycle ────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        """Initialize the panel on mount with a beautiful welcome banner."""
        chat = self.query_one("#agent-chat", RichLog)
        self._print_banner(chat)
        self._print_welcome(chat)

    def _print_banner(self, chat: RichLog) -> None:
        """Print the decorative welcome banner."""
        width = 56
        top = "╔" + "═" * (width - 2) + "╗"
        mid = "║" + "  Terminal Studio Agent v5.1 — AI Code Agent".ljust(width - 2) + "║"
        bot = "╚" + "═" * (width - 2) + "╝"
        chat.write(Text(top, style=self._COLOR_HEADER))
        chat.write(Text(mid, style=self._COLOR_HEADER))
        chat.write(Text(bot, style=self._COLOR_HEADER))
        chat.write(Text(""))

    def _print_welcome(self, chat: RichLog) -> None:
        """Print welcome messages."""
        self._print_system("Welcome! I'm your AI coding assistant.")
        self._print_system("Commands: /help, /reset, /models, /providers, /exit")
        self._print_system("I can read files, run commands, search code, and write code for you.")
        chat.write(Text(""))

    # ── Message Printing ─────────────────────────────────────────────────

    def _print_user(self, message: str) -> None:
        """Print a user message to the chat log.

        Args:
            message: The user's message text.
        """
        chat = self.query_one("#agent-chat", RichLog)
        text = Text()
        text.append("  You ", style=self._COLOR_USER)
        text.append("▸  ", style=self._COLOR_DIM)
        text.append(message, style="white")
        chat.write(text)
        self._message_count += 1

    def _print_ai(self, message: str) -> None:
        """Print an AI text response to the chat log.

        Args:
            message: The AI's message text.
        """
        chat = self.query_one("#agent-chat", RichLog)
        text = Text()
        text.append("  AI   ", style=self._COLOR_AI)
        text.append("▸  ", style=self._COLOR_DIM)
        text.append(message, style="white")
        chat.write(text)

    def _print_system(self, message: str) -> None:
        """Print a system message to the chat log.

        Args:
            message: The system message text.
        """
        chat = self.query_one("#agent-chat", RichLog)
        text = Text("  ◆  ", style=self._COLOR_SYSTEM)
        text.append(message, style="italic grey70")
        chat.write(text)

    def _print_error(self, message: str) -> None:
        """Print an error message to the chat log.

        Args:
            message: The error message text.
        """
        chat = self.query_one("#agent-chat", RichLog)
        text = Text("  ✗  ", style=self._COLOR_ERROR)
        text.append(message, style="bold bright_red")
        chat.write(text)

    def _print_tool(self, tool_name: str, args: dict[str, Any] | None = None) -> None:
        """Print a tool call to the chat log.

        Args:
            tool_name: The name of the tool being called.
            args: Optional dictionary of tool arguments.
        """
        chat = self.query_one("#agent-chat", RichLog)
        text = Text()
        text.append("  ⚡  ", style=self._COLOR_TOOL)
        text.append(f"{tool_name}", style="bold bright_cyan underline")
        if args:
            # Show first 3 args, truncated
            items = list(args.items())[:3]
            params = ", ".join(f"{k}={self._truncate_repr(v)}" for k, v in items)
            if len(args) > 3:
                params += f", ... (+{len(args) - 3} more)"
            text.append(f"  ({params})", style="cyan")
        chat.write(text)

    def _print_tool_result(self, tool_name: str, result: str) -> None:
        """Print a tool execution result to the chat log.

        Args:
            tool_name: The name of the tool that was called.
            result: The result string from the tool.
        """
        chat = self.query_one("#agent-chat", RichLog)
        text = Text()
        text.append("  ✓  ", style="bold bright_green")
        text.append(f"{tool_name}", style="bold green")
        # Truncate long results
        display = result[:300] + "…" if len(result) > 300 else result
        text.append(f"  →  {display}", style="grey70")
        chat.write(text)

    def _print_code(
        self, code: str, language: str = "python", filename: str | None = None
    ) -> None:
        """Print a syntax-highlighted code block to the chat log.

        Args:
            code: The source code to display.
            language: The programming language for syntax highlighting.
            filename: Optional filename to display above the code block.
        """
        chat = self.query_one("#agent-chat", RichLog)

        # Optional filename header
        if filename:
            header = Text(f"  📄 {filename} ", style=self._COLOR_CODE_LANG)
            chat.write(header)

        # Syntax-highlighted code
        syntax = Syntax(
            code,
            language,
            theme=self._SYNTAX_THEME,
            line_numbers=True,
            indent_guides=True,
            word_wrap=True,
        )
        chat.write(syntax)

    def _print_separator(self) -> None:
        """Print a horizontal separator line."""
        chat = self.query_one("#agent-chat", RichLog)
        chat.write(Text("  " + "─" * 50, style=self._COLOR_SEPARATOR))

    def _print_elapsed(self, elapsed: float) -> None:
        """Print elapsed time indicator.

        Args:
            elapsed: Time in seconds.
        """
        chat = self.query_one("#agent-chat", RichLog)
        time_str = f"{elapsed:.2f}s" if elapsed < 60 else f"{elapsed / 60:.1f}m"
        text = Text()
        text.append("  ⏱  ", style=self._COLOR_DIM)
        text.append(f"Response time: {time_str}", style=self._COLOR_TIMESTAMP)
        chat.write(text)

    # ── AI Response Parsing ──────────────────────────────────────────────

    def _print_ai_response(self, text: str, elapsed: float | None = None) -> None:
        """Parse and pretty-print an AI response.

        Extracts and renders code blocks with syntax highlighting,
        tool calls with argument display, and plain text with proper
        formatting.

        Args:
            text: The raw AI response text.
            elapsed: Optional response time in seconds.
        """
        # Split on code blocks first
        parts = re.split(r"(```\w*\n.*?```)", text, flags=re.DOTALL)

        for part in parts:
            stripped = part.strip()
            if not stripped:
                continue

            if part.startswith("```"):
                self._handle_code_block(part)
            elif "<tool>" in part:
                self._handle_tool_calls(part)
            else:
                self._print_ai(stripped)

        # Print timing if available
        if elapsed is not None:
            self._print_elapsed(elapsed)

        self._print_separator()

    def _handle_code_block(self, block: str) -> None:
        """Parse and render a fenced code block.

        Args:
            block: The code block text including fences.
        """
        match = re.match(r"```(\w+)?\n(.*?)```", block, re.DOTALL)
        if match:
            lang = match.group(1) or "text"
            code = match.group(2)
        else:
            lang = "text"
            code = block[3:-3]

        self._print_code(code.strip(), lang)

    def _handle_tool_calls(self, text: str) -> None:
        """Parse tool calls and render remaining text.

        Supports formats:
            <tool>name</tool><args>{...}</args>
            <tool>name</tool>

        Args:
            text: Text potentially containing tool call markup.
        """
        # Pattern: <tool>name</tool> with optional <args>{...}</args>
        tool_pattern = re.compile(
            r"<tool>(\w+)</tool>\s*(?:<args>(.*?)</args>)?", re.DOTALL
        )

        # Extract all tool calls
        last_end = 0
        for match in tool_pattern.finditer(text):
            # Print text before this tool call
            before = text[last_end:match.start()].strip()
            if before:
                self._print_ai(before)

            tool_name = match.group(1)
            args_str = match.group(2)

            # Parse args if present
            args: dict[str, Any] = {}
            if args_str:
                args = self._parse_tool_args(args_str)

            self._print_tool(tool_name, args)
            last_end = match.end()

        # Print remaining text after last tool call
        after = text[last_end:].strip()
        if after:
            self._print_ai(after)

    # ── Utility Methods ──────────────────────────────────────────────────

    @staticmethod
    def _truncate_repr(value: Any, max_len: int = 40) -> str:
        """Return a truncated repr of a value.

        Args:
            value: The value to stringify.
            max_len: Maximum length before truncation.

        Returns:
            Truncated string representation.
        """
        s = repr(value)
        if len(s) > max_len:
            return s[: max_len - 1] + "…"
        return s

    @staticmethod
    def _parse_tool_args(args_str: str) -> dict[str, Any]:
        """Best-effort parse of tool arguments string.

        Handles simple key=value, JSON-like, or plain string args.

        Args:
            args_str: Raw argument string.

        Returns:
            Dictionary of parsed arguments.
        """
        args: dict[str, Any] = {}
        args_str = args_str.strip()
        if not args_str:
            return args

        # Try JSON parsing
        if args_str.startswith("{") and args_str.endswith("}"):
            try:
                import json

                return json.loads(args_str)
            except json.JSONDecodeError:
                pass

        # Simple key=value parsing
        for pair in re.split(r",\s*(?=[a-zA-Z_][a-zA-Z0-9_]*\s*=)", args_str):
            if "=" in pair:
                key, _, val = pair.partition("=")
                args[key.strip()] = val.strip().strip('"\'')
            elif pair.strip():
                args["arg"] = pair.strip()

        return args

    # ── Event Handlers ───────────────────────────────────────────────────

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle user input submission.

        Processes commands (starting with /) or sends messages to the
        orchestrator for AI processing.

        Args:
            event: The Input.Submitted event from Textual.
        """
        text = event.value.strip()
        if not text:
            return

        # Clear input
        event.input.value = ""

        # Handle slash commands
        if text.startswith("/"):
            await self._handle_command(text)
            return

        # Print user message
        self._print_user(text)

        # Start processing
        self.is_processing = True
        self._start_time = time.time()

        try:
            if self._orchestrator is not None:
                response_text = ""
                async for chunk in self._orchestrator.process_message(text):
                    response_text += chunk
                elapsed = time.time() - self._start_time
                self._print_ai_response(response_text, elapsed)
            else:
                self._print_ai(
                    "Agent engine not connected. "
                    "Run with: edkai --agent  "
                    "Or set AGENT_PROVIDER in your environment."
                )
        except Exception as exc:
            self._print_error(f"Agent error: {exc}")
        finally:
            self.is_processing = False

    # ── Command Handling ─────────────────────────────────────────────────

    async def _handle_command(self, cmd: str) -> None:
        """Process a slash command.

        Supported commands:
            /help       — Show available commands
            /reset      — Clear conversation history
            /models     — Show available AI models
            /providers  — Show configured providers
            /clear      — Clear chat display
            /exit, /quit— Exit agent mode

        Args:
            cmd: The full command string (e.g., "/help").
        """
        parts = cmd.split(maxsplit=1)
        command = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if command in ("/exit", "/quit"):
            self._print_system("Goodbye! 👋")
            self.app.exit()

        elif command == "/reset":
            if self._orchestrator is not None and hasattr(
                self._orchestrator, "history"
            ):
                self._orchestrator.history.clear()
            self.messages = []
            self._message_count = 0
            self._print_system("Conversation history cleared. 🗑")

        elif command == "/clear":
            chat = self.query_one("#agent-chat", RichLog)
            chat.clear()
            self._print_banner(chat)
            self._print_system("Chat display cleared.")

        elif command == "/help":
            self._print_help()

        elif command == "/models":
            self._print_models()

        elif command == "/providers":
            self._print_providers()

        elif command == "/status":
            self._print_status()

        elif command == "/info":
            self._print_info()

        else:
            self._print_system(
                f"Unknown command: {command}. "
                "Type /help for available commands."
            )

    # ── Help Display ─────────────────────────────────────────────────────

    def _print_help(self) -> None:
        """Print the comprehensive help panel."""
        chat = self.query_one("#agent-chat", RichLog)

        # Header
        chat.write(Text(""))
        chat.write(Text("  ┌─ 📋  Available Commands  ─────────────────────┐", style="bold yellow"))

        commands = [
            ("  │   /help      ", "— Show this help message"),
            ("  │   /reset     ", "— Clear conversation history"),
            ("  │   /clear     ", "— Clear chat display"),
            ("  │   /models    ", "— Show available AI models"),
            ("  │   /providers ", "— Show configured providers"),
            ("  │   /status    ", "— Show agent status"),
            ("  │   /info      ", "— Show version info"),
            ("  │   /exit      ", "— Exit agent mode"),
        ]

        for label, desc in commands:
            line = Text()
            line.append(label, style="bold bright_yellow")
            line.append(desc, style="grey70")
            chat.write(line)

        chat.write(Text("  └────────────────────────────────────────────────┘", style="bold yellow"))
        chat.write(Text(""))

        # Capabilities
        chat.write(Text("  ┌─ 💡  What I Can Do  ───────────────────────────┐", style="bold bright_cyan"))

        capabilities = [
            "  │   • Read files     —  \"Show me main.py\"",
            "  │   • Write code     —  \"Create a FastAPI endpoint\"",
            "  │   • Run commands   —  \"Run the tests\"",
            "  │   • Search code    —  \"Find all TODO comments\"",
            "  │   • Git help       —  \"Commit these changes\"",
            "  │   • Explain code   —  \"What does this function do?\"",
            "  │   • Refactor       —  \"Refactor this class\"",
        ]

        for cap in capabilities:
            chat.write(Text(cap, style="grey70"))

        chat.write(Text("  └────────────────────────────────────────────────┘", style="bold bright_cyan"))
        chat.write(Text(""))

    def _print_models(self) -> None:
        """Print available models information."""
        chat = self.query_one("#agent-chat", RichLog)
        chat.write(Text(""))
        chat.write(Text("  ┌─ 🤖  Available Models  ───────────────────────┐", style="bold bright_magenta"))
        chat.write(Text("  │                                                │", style="grey70"))
        chat.write(Text("  │   Models depend on your configured providers.  │", style="grey70"))
        chat.write(Text("  │                                                │", style="grey70"))
        chat.write(Text("  │   Set models in:                               │", style="grey70"))
        chat.write(Text("  │   ~/.config/edkai/config.json                │", style="bold bright_cyan"))
        chat.write(Text("  │                                                │", style="grey70"))
        chat.write(Text("  └────────────────────────────────────────────────┘", style="bold bright_magenta"))
        chat.write(Text(""))

    def _print_providers(self) -> None:
        """Print configured providers information."""
        chat = self.query_one("#agent-chat", RichLog)
        chat.write(Text(""))
        chat.write(Text("  ┌─ 🔌  Configured Providers  ───────────────────┐", style="bold bright_green"))
        chat.write(Text("  │                                                │", style="grey70"))
        chat.write(Text("  │   • GitHub Models        —  github             │", style="grey70"))
        chat.write(Text("  │   • Ollama (local)       —  ollama             │", style="grey70"))
        chat.write(Text("  │   • Google Gemini        —  gemini             │", style="grey70"))
        chat.write(Text("  │   • OpenAI-compatible    —  openai             │", style="grey70"))
        chat.write(Text("  │                                                │", style="grey70"))
        chat.write(Text("  │   Set provider in:                             │", style="grey70"))
        chat.write(Text("  │   ~/.config/edkai/config.json                │", style="bold bright_cyan"))
        chat.write(Text("  │                                                │", style="grey70"))
        chat.write(Text("  └────────────────────────────────────────────────┘", style="bold bright_green"))
        chat.write(Text(""))

    def _print_status(self) -> None:
        """Print current agent status."""
        chat = self.query_one("#agent-chat", RichLog)
        chat.write(Text(""))
        chat.write(Text("  ┌─ 📊  Agent Status  ───────────────────────────┐", style="bold bright_blue"))

        status_lines = [
            ("  │   Provider:  ", self.provider_name),
            ("  │   Model:     ", self.model_name),
            ("  │   Status:    ", "Processing…" if self.is_processing else "Ready"),
            ("  │   Messages:  ", str(self._message_count)),
            ("  │   Connected: ", "Yes" if self._orchestrator else "No"),
        ]

        for label, value in status_lines:
            line = Text()
            line.append(label, style="grey70")
            line.append(value, style="bold white")
            chat.write(line)

        chat.write(Text("  └────────────────────────────────────────────────┘", style="bold bright_blue"))
        chat.write(Text(""))

    def _print_info(self) -> None:
        """Print version and system information."""
        chat = self.query_one("#agent-chat", RichLog)
        chat.write(Text(""))
        chat.write(Text("  ┌─ ℹ️   Terminal Studio Agent  ─────────────────┐", style="bold bright_cyan"))
        chat.write(Text("  │                                                │", style="grey70"))
        chat.write(Text("  │   Version:     5.1.0                           │", style="grey70"))
        chat.write(Text("  │   Framework:   Textual TUI                     │", style="grey70"))
        chat.write(Text("  │   Syntax:      Pygments (monokai)              │", style="grey70"))
        chat.write(Text("  │   Rich Log:    Syntax Highlighting Enabled     │", style="grey70"))
        chat.write(Text("  │                                                │", style="grey70"))
        chat.write(Text("  └────────────────────────────────────────────────┘", style="bold bright_cyan"))
        chat.write(Text(""))

    # ── Reactive Watchers ────────────────────────────────────────────────

    def watch_provider_name(self, name: str) -> None:
        """React to provider name changes.

        Args:
            name: The new provider name.
        """
        try:
            label = self.query_one("#agent-provider", Label)
            label.update(name)
        except Exception:
            pass  # Widget may not be mounted yet

    def watch_model_name(self, name: str) -> None:
        """React to model name changes.

        Args:
            name: The new model name.
        """
        try:
            label = self.query_one("#agent-model", Label)
            label.update(name)
        except Exception:
            pass  # Widget may not be mounted yet

    def watch_is_processing(self, processing: bool) -> None:
        """React to processing state changes.

        Updates the status dot and prompt character to reflect
        whether the agent is busy generating a response.

        Args:
            processing: True if the agent is processing, False otherwise.
        """
        try:
            dot = self.query_one("#agent-status-dot", Label)
            prompt = self.query_one("#agent-prompt", Label)

            if processing:
                dot.update("◐")
                dot.styles.color = Color.parse("#FFD700")  # Gold
                prompt.update("⏳")
                prompt.styles.color = Color.parse("#FFD700")
            else:
                dot.update("●")
                dot.styles.color = Color.parse("#32CD32")  # Lime green
                prompt.update("❯")
                prompt.styles.color = Color.parse("#32CD32")
        except Exception:
            pass  # Widgets may not be mounted yet

    # ── Public API ───────────────────────────────────────────────────────

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the conversation and display it.

        Args:
            role: Message role — "user", "assistant", "system", or "tool".
            content: The message content.
        """
        self.messages = [*self.messages, {"role": role, "content": content}]

        if role == "user":
            self._print_user(content)
        elif role == "assistant":
            self._print_ai_response(content)
        elif role == "system":
            self._print_system(content)
        elif role == "tool":
            self._print_tool(content, {})

    def clear_chat(self) -> None:
        """Clear the chat display (does not reset history)."""
        chat = self.query_one("#agent-chat", RichLog)
        chat.clear()
        self._print_banner(chat)

    def set_provider(self, name: str) -> None:
        """Update the displayed provider name.

        Args:
            name: The new provider name.
        """
        self.provider_name = name

    def set_model(self, name: str) -> None:
        """Update the displayed model name.

        Args:
            name: The new model identifier.
        """
        self.model_name = name

    def focus_input(self) -> None:
        """Set focus to the input field."""
        try:
            inp = self.query_one("#agent-input", Input)
            inp.focus()
        except Exception:
            pass

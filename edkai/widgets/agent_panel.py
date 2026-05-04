"""
AgentPanel -- Beautiful Terminal AI Agent Interface

Inspired by:
- Claude Code -- clean status bar, minimal design
- Warp -- modern terminal with blocks
- Aider -- clear command/response separation
- Vim -- keyboard-focused efficiency

Dark theme inspired by GitHub Dark (bg #0d1117).
"""

from __future__ import annotations

import re
import time
import asyncio
from typing import Callable, Iterable, Optional
from dataclasses import dataclass, field
from enum import Enum, auto

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Input, RichLog, Static, Label, LoadingIndicator
from textual.message import Message as TextualMessage

from rich.syntax import Syntax
from rich.markdown import Markdown
from rich.text import Text
from rich.console import Console
from rich.panel import Panel

from edkai.widgets.typing_indicator import TypingIndicator

# Deferred import to avoid circular dependency
try:
    from edkai.widgets.project_dashboard import ProjectDashboard
except ImportError:
    ProjectDashboard = None  # type: ignore


# ---------------------------------------------------------------------------
# Constants & Colour Palette (GitHub Dark inspired)
# ---------------------------------------------------------------------------

C_BG = "#0d1117"           # main background
C_BG_SECONDARY = "#161b22"  # secondary background
C_BORDER = "#30363d"        # borders
C_TEXT = "#e6edf3"          # primary text
C_TEXT_MUTED = "#8b949e"    # muted text
C_TEXT_DIM = "#484f58"      # dim text

C_BLUE = "#58a6ff"          # links, model name
C_GREEN = "#3fb950"         # success, active, user
C_YELLOW = "#d29922"        # warnings, system
C_RED = "#f85149"           # errors
C_PURPLE = "#bc8cff"        # accents
C_CYAN = "#39c5cf"          # tool calls, info

ICON_USER = ">"
ICON_AI = "◆"
ICON_SYSTEM = "⚡"
ICON_TOOL = "🔧"
ICON_ERROR = "✗"
ICON_SUCCESS = "✓"
ICON_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
ICON_PROVIDER_ACTIVE = "●"
ICON_PROVIDER_INACTIVE = "○"


class MsgType(Enum):
    """Message type for styling."""
    USER = auto()
    AI = auto()
    SYSTEM = auto()
    TOOL = auto()
    ERROR = auto()
    SUCCESS = auto()
    CODE = auto()


@dataclass
class Message:
    """A chat message."""
    content: str
    msg_type: MsgType = MsgType.USER
    timestamp: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Syntax Highlighting Language Map
# ---------------------------------------------------------------------------

COMMON_LANGUAGES = {
    "python": "python", "py": "python",
    "javascript": "javascript", "js": "javascript",
    "typescript": "typescript", "ts": "typescript",
    "bash": "bash", "sh": "bash", "shell": "bash", "zsh": "bash",
    "json": "json", "yaml": "yaml", "yml": "yaml", "toml": "toml",
    "rust": "rust", "go": "go", "c": "c", "cpp": "cpp", "c++": "cpp",
    "java": "java", "html": "html", "css": "css", "sql": "sql",
    "dockerfile": "dockerfile", "md": "markdown", "markdown": "markdown",
    "diff": "diff", "ruby": "ruby", "rb": "ruby",
}


# ---------------------------------------------------------------------------
# TCSS Stylesheet
# ---------------------------------------------------------------------------

CSS = """
/* ================================================================
   AgentPanel -- Main Container
   ================================================================ */
AgentPanel {
    width: 100%;
    height: 100%;
    background: #0d1117;
    border: none;
    padding: 0;
    layout: vertical;
}

/* -- Status Bar (top) ------------------------------------------ */
#status-bar {
    width: 100%;
    height: 1;
    background: #161b22;
    color: #8b949e;
    padding: 0 1;
    border-bottom: solid #30363d;
    content-align: left middle;
}
#status-left  { width: auto; height: 1; background: transparent; }
#status-center {
    width: 1fr; height: 1; background: transparent;
    content-align: center middle;
}
#status-right {
    width: auto; height: 1; background: transparent;
    content-align: right middle;
}
#status-app-name { color: #58a6ff; text-style: bold; }
#status-model    { color: #bc8cff; text-style: bold; }
#status-provider { color: #3fb950; }
#status-time     { color: #8b949e; text-style: dim; }
#status-dot-active   { color: #3fb950; }
#status-dot-inactive { color: #484f58; }
#status-dot-error    { color: #f85149; }
#status-dot-loading  { color: #d29922; }

/* -- Chat Area ------------------------------------------------- */
#chat-log {
    width: 100%;
    height: 1fr;
    background: #0d1117;
    border: none;
    padding: 0 1;
    scrollbar-size: 1 1;
    scrollbar-background: #0d1117;
    scrollbar-color: #30363d;
    scrollbar-color-active: #484f58;
    scrollbar-color-hover: #58a6ff;
}

/* -- Processing Indicator -------------------------------------- */
#processing-indicator {
    width: 100%;
    height: 1;
    background: #0d1117;
    color: #d29922;
    padding: 0 2;
    display: none;
}
#processing-indicator.visible {
    display: block;
}

/* -- Input Area ------------------------------------------------ */
#input-area {
    width: 100%;
    height: auto;
    max-height: 8;
    dock: bottom;
    background: #161b22;
    border-top: solid #30363d;
    padding: 0 0 0 1;
}
#input-row {
    width: 100%;
    height: auto;
    min-height: 1;
    background: transparent;
}
#prompt-symbol {
    width: auto;
    color: #3fb950;
    text-style: bold;
    background: transparent;
    content-align: left middle;
    padding: 0;
}
#user-input {
    width: 1fr;
    height: auto;
    min-height: 1;
    max-height: 7;
    background: #161b22;
    border: none;
    color: #e6edf3;
    content-align: left middle;
    padding: 0 1 0 0;
}
#user-input:focus { border: none; }
#user-input > .input--cursor {
    color: #58a6ff;
    background: #58a6ff 30%;
    text-style: bold;
}
#user-input > .input--placeholder { color: #484f58; text-style: dim; }

/* -- Toolbar --------------------------------------------------- */
#toolbar {
    width: 100%;
    height: 1;
    dock: bottom;
    background: #0d1117;
    color: #484f58;
    text-style: dim;
    padding: 0 2;
    border-top: solid #30363d;
}
"""


# ---------------------------------------------------------------------------
# StatusBar
# ---------------------------------------------------------------------------

class StatusBar(Container):
    """Top bar: app name, model, provider, response time, provider dots."""

    DEFAULT_CSS = CSS

    provider: reactive[str] = reactive("groq")
    model: reactive[str] = reactive("llama-3.3-70b")
    response_time: reactive[float] = reactive(0.0)
    provider_statuses: reactive[list[tuple[str, str]]] = reactive(
        [
            ("groq", "active"),
            ("gemini", "inactive"),
            ("github", "active"),
            ("cerebras", "inactive"),
        ]
    )
    is_processing: reactive[bool] = reactive(False)

    def compose(self) -> ComposeResult:
        with Horizontal(id="status-bar"):
            with Horizontal(id="status-left"):
                yield Static(
                    Text.assemble(("EDK_AI ", C_BLUE), ("v6", C_TEXT_MUTED)),
                    id="status-app-name",
                )
            with Horizontal(id="status-center"):
                yield Static(self._build_center_text(), id="status-model-info")
            with Horizontal(id="status-right"):
                yield Static(self._build_provider_dots(), id="status-providers")

    def _build_center_text(self) -> Text:
        parts = []
        if self.is_processing:
            parts.append((" ◐ ", C_YELLOW))
        else:
            parts.append((" ◆ ", C_BLUE))
        parts.append((self.model, C_BLUE))
        parts.append((" @ ", C_TEXT_MUTED))
        parts.append((self.provider, C_GREEN))
        if self.response_time > 0:
            parts.append((" ● ", C_TEXT_MUTED))
            t = f"{self.response_time:.0f}ms"
            parts.append((t, C_TEXT_MUTED))
        return Text.assemble(*parts)

    def _build_provider_dots(self) -> Text:
        parts = []
        for name, status in self.provider_statuses:
            if status == "active":
                col = C_GREEN
            elif status == "error":
                col = C_RED
            elif status == "loading":
                col = C_YELLOW
            else:
                col = C_TEXT_DIM
            sym = ICON_PROVIDER_ACTIVE if status == "active" else ICON_PROVIDER_INACTIVE
            parts.append((f"[{name}{sym}] ", col))
        return Text.assemble(*parts)

    def watch_provider(self, value: str) -> None:
        self._refresh_center()

    def watch_model(self, value: str) -> None:
        self._refresh_center()

    def watch_response_time(self, value: float) -> None:
        self._refresh_center()

    def watch_is_processing(self, value: bool) -> None:
        self._refresh_center()

    def watch_provider_statuses(self, value: list[tuple[str, str]]) -> None:
        try:
            w = self.query_one("#status-providers", Static)
            w.update(self._build_provider_dots())
        except Exception:
            pass

    def _refresh_center(self) -> None:
        try:
            self.query_one("#status-model-info", Static).update(self._build_center_text())
        except Exception:
            pass

    def update_status(self, provider: str, model: str, response_time: float = 0.0) -> None:
        self.provider = provider
        self.model = model
        self.response_time = response_time

    def update_provider_status(self, statuses: list[tuple[str, str]]) -> None:
        self.provider_statuses = statuses

    def set_processing(self, processing: bool) -> None:
        self.is_processing = processing


# ---------------------------------------------------------------------------
# ProcessingIndicator
# ---------------------------------------------------------------------------

class ProcessingIndicator(Static):
    """Animated braille spinner shown while AI is working."""

    DEFAULT_CSS = CSS

    def __init__(self) -> None:
        super().__init__("", id="processing-indicator")
        self._spinner_idx = 0
        self._timer: Optional[asyncio.Task] = None
        self._message = "Thinking..."

    def on_mount(self) -> None:
        self._start_animation()

    def _start_animation(self) -> None:
        self._timer = asyncio.create_task(self._animate())

    async def _animate(self) -> None:
        while True:
            try:
                ch = ICON_SPINNER[self._spinner_idx % len(ICON_SPINNER)]
                self.update(Text.assemble((f" {ch} ", C_YELLOW), (self._message, C_TEXT_MUTED)))
                self._spinner_idx += 1
                await asyncio.sleep(0.08)
            except asyncio.CancelledError:
                break
            except Exception:
                break

    def set_message(self, message: str) -> None:
        self._message = message

    def show(self) -> None:
        self.add_class("visible")

    def hide(self) -> None:
        self.remove_class("visible")

    def on_unmount(self) -> None:
        if self._timer and not self._timer.done():
            self._timer.cancel()


# ---------------------------------------------------------------------------
# ChatLog
# ---------------------------------------------------------------------------

class ChatLog(RichLog):
    """RichLog chat with markdown/code parsing and syntax highlighting."""

    DEFAULT_CSS = CSS

    SEPARATOR = "─" * 60

    def __init__(self) -> None:
        super().__init__(
            id="chat-log",
            highlight=True,
            markup=True,
            wrap=True,
            auto_scroll=True,
        )
        self._messages: list[Message] = []
        self._console = Console(color_system="truecolor", force_terminal=True, width=120)

    # -- public writers ------------------------------------------------

    def print_user(self, text: str) -> None:
        self._messages.append(Message(text, MsgType.USER))
        self._write_user(text)

    def print_ai(self, text: str) -> None:
        self._messages.append(Message(text, MsgType.AI))
        self._parse_and_render(text)

    def print_system(self, text: str) -> None:
        self._messages.append(Message(text, MsgType.SYSTEM))
        self._write_system(text)

    def print_tool(self, name: str, args: dict) -> None:
        self._messages.append(
            Message(f"{name}: {args}", MsgType.TOOL, metadata={"name": name, "args": args})
        )
        self._write_tool(name, args)

    def print_tool_result(self, name: str, result: str, success: bool = True) -> None:
        self._write_tool_result(name, result, success)

    def print_error(self, text: str) -> None:
        self._messages.append(Message(text, MsgType.ERROR))
        self._write_error(text)

    def print_success(self, text: str) -> None:
        self._messages.append(Message(text, MsgType.SUCCESS))
        self._write_success(text)

    def print_code(self, code: str, language: str = "python") -> None:
        self._messages.append(Message(code, MsgType.CODE, metadata={"lang": language}))
        self._write_code(code, language)

    def print_separator(self, title: str = "") -> None:
        if title:
            pad = max(2, (56 - len(title)) // 2)
            line = "─" * pad + f" {title} " + "─" * pad
        else:
            line = self.SEPARATOR
        self.write(Text(line, style=f"bold {C_BORDER}"))

    def print_empty(self) -> None:
        self.write("")

    # -- internal formatters -------------------------------------------

    def _write_user(self, text: str) -> None:
        self.write("")
        pfx = Text.assemble((" ", C_BG), (ICON_USER, f"bold {C_GREEN}"), (" ", C_BG))
        self.write(Text.assemble(pfx, Text(text, C_TEXT)))

    def _write_ai(self, text: str) -> None:
        pfx = Text.assemble((" ", C_BG), (ICON_AI, f"bold {C_BLUE}"), (" ", C_BG))
        self.write(Text.assemble(pfx, Text(text, C_TEXT)))

    def _write_system(self, text: str) -> None:
        self.write("")
        pfx = Text.assemble((" ", C_BG), (ICON_SYSTEM, f"bold {C_YELLOW}"), (" ", C_BG))
        self.write(Text.assemble(pfx, Text(text, C_YELLOW)))

    def _write_tool(self, name: str, args: dict) -> None:
        self.write("")
        pfx = Text.assemble((" ", C_BG), (ICON_TOOL, f"bold {C_CYAN}"), (" ", C_BG))
        hdr = Text.assemble(pfx, ("Tool: ", f"bold {C_CYAN}"), (name, f"bold {C_PURPLE}"))
        self.write(hdr)
        if args:
            self.write(Text(f"       {self._fmt_dict(args)}", C_TEXT_MUTED))

    def _write_tool_result(self, name: str, result: str, success: bool) -> None:
        col = C_GREEN if success else C_RED
        icon = ICON_SUCCESS if success else ICON_ERROR
        pfx = Text.assemble(("   ", C_BG), (icon, f"bold {col}"), (" ", C_BG))
        self.write(Text.assemble(pfx, (name, f"bold {col}"), (" → ", C_TEXT_MUTED)))
        rs = str(result)
        if len(rs) > 200:
            rs = rs[:200] + "..."
        self.write(Text(f"       {rs}", C_TEXT_MUTED))

    def _write_error(self, text: str) -> None:
        self.write("")
        pfx = Text.assemble((" ", C_BG), (ICON_ERROR, f"bold {C_RED}"), (" ", C_BG))
        self.write(Text.assemble(pfx, Text(text, C_RED)))

    def _write_success(self, text: str) -> None:
        self.write("")
        pfx = Text.assemble((" ", C_BG), (ICON_SUCCESS, f"bold {C_GREEN}"), (" ", C_BG))
        self.write(Text.assemble(pfx, Text(text, C_GREEN)))

    def _write_code(self, code: str, language: str = "python") -> None:
        lang = COMMON_LANGUAGES.get(language.lower(), "python")
        try:
            syntax = Syntax(
                code.strip(),
                lang,
                theme="monokai",
                line_numbers=True,
                word_wrap=True,
                padding=(0, 2),
                background_color=C_BG,
            )
            panel = Panel(
                syntax,
                title=f"[bold {C_TEXT_MUTED}]{lang}[/]",
                border_style=C_BORDER,
                padding=(0, 0),
                style=f"on {C_BG}",
            )
            self.write("")
            self.write(panel)
        except Exception:
            self.write("")
            self.write(Text(f"```{language}", C_TEXT_MUTED))
            self.write(Text(code, C_TEXT))
            self.write(Text("```", C_TEXT_MUTED))

    def _fmt_dict(self, d: dict) -> str:
        if not d:
            return "{}"
        parts = []
        for k, v in d.items():
            vs = repr(v) if not isinstance(v, str) or len(v) < 50 else repr(v[:50] + "...")
            parts.append(f"{k}={vs}")
        return ", ".join(parts)

    # -- markdown / code parsing ---------------------------------------

    def _parse_and_render(self, text: str) -> None:
        pattern = r'```(\w*)\n(.*?)```'
        last = 0
        for m in re.finditer(pattern, text, re.DOTALL):
            before = text[last:m.start()]
            if before.strip():
                self._render_md_chunk(before)
            lang = m.group(1).strip() or "text"
            self._write_code(m.group(2), lang)
            last = m.end()
        remaining = text[last:]
        if remaining.strip():
            self._render_md_chunk(remaining)

    def _render_md_chunk(self, text: str) -> None:
        lines = text.split("\n")
        para: list[str] = []

        def flush():
            if para:
                self._write_ai_para(" ".join(para))
                para.clear()

        for raw in lines:
            s = raw.strip()
            if not s:
                flush()
                continue

            if s.startswith("# "):
                flush(); self._write_ai_header(s[2:], 1); continue
            if s.startswith("## "):
                flush(); self._write_ai_header(s[3:], 2); continue
            if s.startswith("### "):
                flush(); self._write_ai_header(s[4:], 3); continue

            if s.startswith(("- ", "* ")):
                flush(); self._write_ai_li(s[2:]); continue

            nm = re.match(r'^\d+\.\s+(.+)$', s)
            if nm:
                flush(); self._write_ai_num(nm.group(1)); continue

            if s.startswith("> "):
                flush(); self._write_ai_bq(s[2:]); continue

            para.append(s)

        flush()

    def _write_ai_para(self, text: str) -> None:
        pfx = Text.assemble((" ", C_BG), (ICON_AI, f"bold {C_BLUE}"), (" ", C_BG))
        self.write(Text.assemble(pfx, self._parse_inline(text)))

    def _write_ai_header(self, text: str, level: int) -> None:
        pfx = Text.assemble((" ", C_BG), (ICON_AI, f"bold {C_BLUE}"), (" ", C_BG))
        ind = "  " * (level - 1)
        self.write(Text.assemble(pfx, Text(f"{ind}{text}", f"bold {C_BLUE}")))

    def _write_ai_li(self, text: str) -> None:
        pfx = Text.assemble((" ", C_BG), (ICON_AI, f"bold {C_BLUE}"), (" ", C_BG))
        self.write(Text.assemble(pfx, Text("  • ", C_TEXT_MUTED), self._parse_inline(text)))

    def _write_ai_num(self, text: str) -> None:
        pfx = Text.assemble((" ", C_BG), (ICON_AI, f"bold {C_BLUE}"), (" ", C_BG))
        self.write(Text.assemble(pfx, Text("  → ", C_TEXT_MUTED), self._parse_inline(text)))

    def _write_ai_bq(self, text: str) -> None:
        pfx = Text.assemble((" ", C_BG), (ICON_AI, f"bold {C_BLUE}"), (" ", C_BG))
        self.write(Text.assemble(pfx, Text(f"  ▌ {text}", f"italic {C_TEXT_MUTED}")))

    def _parse_inline(self, text: str) -> Text:
        result = Text()
        i = 0
        while i < len(text):
            # bold **text**
            if text[i:i+2] == "**" and i + 2 < len(text):
                j = text.find("**", i + 2)
                if j != -1:
                    result.append(text[i+2:j], f"bold {C_TEXT}")
                    i = j + 2
                    continue
            # italic *text* or _text_
            if text[i] in "*_" and i + 1 < len(text):
                j = text.find(text[i], i + 1)
                if j != -1:
                    result.append(text[i+1:j], f"italic {C_TEXT_MUTED}")
                    i = j + 1
                    continue
            # inline `code`
            if text[i] == '`' and i + 1 < len(text):
                j = text.find('`', i + 1)
                if j != -1:
                    result.append(text[i+1:j], f"on {C_BG_SECONDARY} {C_PURPLE}")
                    i = j + 1
                    continue
            result.append(text[i])
            i += 1
        return result if len(result) > 0 else Text(text, C_TEXT)

    def clear_history(self) -> None:
        self._messages.clear()
        self.clear()

    def get_history(self) -> list[Message]:
        return list(self._messages)


# ---------------------------------------------------------------------------
# InputBar
# ---------------------------------------------------------------------------

class InputBar(Container):
    """Input with green prompt, history, suggestions, slash commands."""

    DEFAULT_CSS = CSS

    BINDINGS = [
        Binding("up", "history_prev", show=False),
        Binding("down", "history_next", show=False),
    ]

    def __init__(self) -> None:
        super().__init__(id="input-area")
        self._history: list[str] = []
        self._history_index: int = -1
        self._suggestions = [
            "/help", "/clear", "/model", "/provider",
            "/status", "/tools", "/undo", "/redo",
            "/save", "/load", "/exit", "/quit",
        ]
        self._placeholder = (
            "Type a message...  ·  / for commands  ·  Shift+Enter for newline"
        )

    def compose(self) -> ComposeResult:
        with Horizontal(id="input-row"):
            yield Static(Text(ICON_USER, style=f"bold {C_GREEN}"), id="prompt-symbol")
            yield Input(placeholder=self._placeholder, id="user-input")

    def on_mount(self) -> None:
        self.query_one("#user-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        if value:
            self._history.append(value)
            self._history_index = len(self._history)
            self.post_message(self.Submitted(value))
            event.input.value = ""

    def action_history_prev(self) -> None:
        if not self._history or self._history_index <= 0:
            return
        self._history_index -= 1
        inp = self.query_one("#user-input", Input)
        inp.value = self._history[self._history_index]
        inp.cursor_position = len(inp.value)

    def action_history_next(self) -> None:
        if not self._history:
            return
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            inp = self.query_one("#user-input", Input)
            inp.value = self._history[self._history_index]
            inp.cursor_position = len(inp.value)
        elif self._history_index == len(self._history) - 1:
            self._history_index = len(self._history)
            self.query_one("#user-input", Input).value = ""

    def set_value(self, text: str) -> None:
        self.query_one("#user-input", Input).value = text

    def get_value(self) -> str:
        return self.query_one("#user-input", Input).value

    def clear(self) -> None:
        self.query_one("#user-input", Input).value = ""

    def focus(self) -> None:
        self.query_one("#user-input", Input).focus()

    class Submitted(TextualMessage):
        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value


# ---------------------------------------------------------------------------
# Toolbar
# ---------------------------------------------------------------------------

class Toolbar(Static):
    """Bottom hint bar."""

    DEFAULT_CSS = CSS

    def __init__(self) -> None:
        super().__init__("", id="toolbar")
        self._default = self._mk([
            ("Enter", "submit"), ("Shift+Enter", "newline"), ("↑↓", "history"),
            ("/", "commands"), ("Ctrl+C", "cancel"),
        ])
        self._processing = self._mk([("Ctrl+C", "cancel"), ("Processing...", "")])

    def on_mount(self) -> None:
        self.update(self._default)

    def set_processing(self, processing: bool) -> None:
        self.update(self._processing if processing else self._default)

    def _mk(self, hints: list[tuple[str, str]]) -> Text:
        parts = []
        for k, d in hints:
            if k and d:
                parts.append((k, f"bold {C_TEXT_MUTED}"))
                parts.append((f":{d}  ", C_TEXT_DIM))
            elif k:
                parts.append((f"{k}  ", C_TEXT_MUTED))
        return Text.assemble(*parts) if parts else Text("")



# ---------------------------------------------------------------------------
# AgentPanel -- Main Widget
# ---------------------------------------------------------------------------

class AgentPanel(Container):
    """Main panel: StatusBar + ChatLog + ProcessingIndicator + InputBar + Toolbar."""

    DEFAULT_CSS = CSS

    BINDINGS = [
        Binding("ctrl+c", "cancel", show=False),
        Binding("ctrl+l", "clear", show=False),
    ]

    def __init__(self) -> None:
        super().__init__(id="agent-panel")
        self._status_bar = StatusBar()
        self._chat_log = ChatLog()
        self._typing_indicator = TypingIndicator(id="typing-indicator")
        self._processing = ProcessingIndicator()
        self._input_bar = InputBar()
        self._toolbar = Toolbar()
        self._cancelled = False
        self._dashboard: ProjectDashboard | None = None
        self.model_name = "llama-3.3-70b"
        self.provider_name = "groq"

    # -- compose -------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield self._status_bar
        yield self._chat_log
        yield self._typing_indicator
        yield self._processing
        yield self._input_bar
        yield self._toolbar

    def on_mount(self) -> None:
        self._input_bar.focus()
        self.print_welcome()

    # -- welcome -------------------------------------------------------

    def print_welcome(self) -> None:
        self.print_separator("EDK_AI v6")
        self._chat_log.write(Text.assemble(
            ("  Welcome to ", C_TEXT_MUTED), ("EDK_AI", f"bold {C_BLUE}"),
            (" -- your terminal AI assistant.", C_TEXT_MUTED),
        ))
        self._chat_log.write("")
        self._chat_log.write(Text.assemble(
            ("  Model: ", C_TEXT_DIM), ("llama-3.3-70b", f"bold {C_PURPLE}"),
            ("  ·  Provider: ", C_TEXT_DIM), ("Groq", f"bold {C_GREEN}"),
            ("  ·  Type ", C_TEXT_DIM), ("/help", f"bold {C_YELLOW}"),
            (" for commands.", C_TEXT_DIM),
        ))
        self._chat_log.write("")
        self.print_separator()
        self._chat_log.write("")

    # -- public print methods ------------------------------------------

    def print_user(self, text: str) -> None:
        """Format and print a user message."""
        self._chat_log.print_user(text)

    def print_ai(self, text: str) -> None:
        """Format and print AI response with markdown/code parsing."""
        self._chat_log.print_ai(text)
        self._track_activity("ai_response", text[:80])

    def print_system(self, text: str) -> None:
        """Format and print a system message."""
        self._chat_log.print_system(text)

    def print_tool(self, name: str, args: dict) -> None:
        """Format and print a tool call."""
        self._chat_log.print_tool(name, args)

    def print_tool_result(self, name: str, result: str, success: bool = True) -> None:
        """Format and print a tool result."""
        self._chat_log.print_tool_result(name, result, success)

    def print_error(self, text: str) -> None:
        """Format and print an error."""
        self._chat_log.print_error(text)

    def print_success(self, text: str) -> None:
        """Format and print a success."""
        self._chat_log.print_success(text)

    def print_code(self, code: str, language: str = "python") -> None:
        """Print syntax-highlighted code block."""
        self._chat_log.print_code(code, language)

    def print_separator(self, title: str = "") -> None:
        """Print a decorative separator line."""
        self._chat_log.print_separator(title)

    def print_empty(self) -> None:
        """Print an empty line."""
        self._chat_log.print_empty()

    # -- state management ----------------------------------------------

    def start_processing(self, message: str = "Thinking...") -> None:
        """Show spinner, disable input, update toolbar, start typing indicator."""
        self._cancelled = False
        self._processing.set_message(message)
        self._processing.show()
        self._toolbar.set_processing(True)
        self._status_bar.set_processing(True)
        self._typing_indicator.start()
        self._track_activity("process", f"Started: {message}")

    def stop_processing(self) -> None:
        """Hide spinner, re-enable input, stop typing indicator."""
        self._processing.hide()
        self._toolbar.set_processing(False)
        self._status_bar.set_processing(False)
        self._typing_indicator.stop()
        self._input_bar.focus()
        self._track_activity("process", "Completed")

    def action_cancel(self) -> None:
        """Cancel current operation."""
        self._cancelled = True
        self.stop_processing()
        self.print_system("Operation cancelled by user.")
        self._track_activity("cancel", "User cancelled operation")

    def action_clear(self) -> None:
        """Clear chat history."""
        self._chat_log.clear_history()
        self.print_welcome()
        self._track_activity("clear", "Chat history cleared")

    # -- status bar delegation -----------------------------------------

    def update_status(self, provider: str, model: str, response_time: float = 0.0) -> None:
        """Update status bar with current provider/model/time."""
        self.provider_name = provider
        self.model_name = model
        self._status_bar.update_status(provider, model, response_time)
        self._typing_indicator.set_model(model, provider)

    def update_provider_status(self, statuses: list[tuple[str, str]]) -> None:
        """Update provider health indicators.

        Args:
            statuses: List of (name, status) tuples.
                     Status values: "active", "inactive", "error", "loading"
        """
        self._status_bar.update_provider_status(statuses)

    # -- activity tracking / dashboard ---------------------------------

    def set_dashboard(self, dashboard: ProjectDashboard) -> None:
        """Attach a ProjectDashboard for activity tracking."""
        self._dashboard = dashboard

    def _track_activity(self, action: str, detail: str = "") -> None:
        """Log an activity event to the dashboard if attached."""
        if self._dashboard is not None:
            try:
                self._dashboard.add_activity(action, detail)
            except Exception:
                pass

    # -- input handling ------------------------------------------------

    def on_input_bar_submitted(self, event: InputBar.Submitted) -> None:
        """Handle input from InputBar."""
        value = event.value.strip()
        if not value:
            return

        # Slash commands
        if value.startswith("/"):
            self._handle_slash_command(value)
            self._track_activity("command", value)
            return

        # Normal user message
        self.print_user(value)
        self._track_activity("user_message", value[:80])
        self.post_message(self.UserMessage(value))

    def _handle_slash_command(self, text: str) -> None:
        """Route slash command to handler."""
        handler = SlashCommandHandler(self)
        handler.handle(text)

    def get_input(self) -> str:
        """Get current input value."""
        return self._input_bar.get_value()

    def clear_input(self) -> None:
        """Clear input field."""
        self._input_bar.clear()

    def focus_input(self) -> None:
        """Focus the input field."""
        self._input_bar.focus()

    # -- events --------------------------------------------------------

    class UserMessage(TextualMessage):
        """Posted when user sends a message."""

        def __init__(self, content: str) -> None:
            super().__init__()
            self.content = content

    class SlashCommand(TextualMessage):
        """Posted when user enters a slash command."""

        def __init__(self, command: str, args: str = "") -> None:
            super().__init__()
            self.command = command
            self.args = args

    # -- properties ----------------------------------------------------

    @property
    def chat_log(self) -> ChatLog:
        return self._chat_log

    @property
    def status_bar(self) -> StatusBar:
        return self._status_bar

    @property
    def input_bar(self) -> InputBar:
        return self._input_bar

    @property
    def typing_indicator(self) -> TypingIndicator:
        return self._typing_indicator


# ---------------------------------------------------------------------------
# SlashCommandHandler
# ---------------------------------------------------------------------------

class SlashCommandHandler:
    """Handles /commands for AgentPanel. Extend for custom commands."""

    COMMANDS: dict[str, str] = {
        "/help": "Show available commands",
        "/clear": "Clear chat history",
        "/model": "Switch model (usage: /model <name>)",
        "/provider": "Switch provider (usage: /provider <name>)",
        "/status": "Show system status",
        "/tools": "List available tools",
        "/undo": "Undo last action",
        "/redo": "Redo last action",
        "/save": "Save chat to file (usage: /save <filename>)",
        "/load": "Load chat from file (usage: /load <filename>)",
        "/exit": "Exit the application",
        "/quit": "Exit the application (alias)",
    }

    def __init__(self, panel: AgentPanel) -> None:
        self.panel = panel

    def handle(self, text: str) -> bool:
        """Handle a slash command. Returns True if handled."""
        if not text.startswith("/"):
            return False
        parts = text.split(None, 1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        handler_name = f"cmd_{command[1:]}"
        handler = getattr(self, handler_name, self.cmd_unknown)
        handler(args)
        return True

    def cmd_help(self, args: str = "") -> None:
        self.panel.print_system("Available commands:")
        for cmd, desc in self.COMMANDS.items():
            self.panel._chat_log.write(Text.assemble(
                (f"  {cmd:12} ", f"bold {C_CYAN}"), (desc, C_TEXT_MUTED),
            ))

    def cmd_clear(self, args: str = "") -> None:
        self.panel.action_clear()

    def cmd_model(self, args: str = "") -> None:
        if args:
            self.panel.update_status(self.panel.provider_name, args)
            self.panel.print_success(f"Model switched to: {args}")
            self.panel._track_activity("model_change", f"Switched to {args}")
        else:
            self.panel.print_system(f"Current model: {self.panel.model_name}")
            self.panel.print_system("Available: type /models to see all")

    def cmd_provider(self, args: str = "") -> None:
        if args:
            self.panel.update_status(args, self.panel.model_name)
            self.panel.print_success(f"Provider switched to: {args}")
            self.panel._track_activity("provider_change", f"Switched to {args}")
        else:
            self.panel.print_system(f"Current provider: {self.panel.provider_name}")

    def cmd_status(self, args: str = "") -> None:
        self.panel.print_separator("System Status")
        self.panel._chat_log.write(Text.assemble(
            ("  Provider:  ", C_TEXT_DIM),
            (self.panel.status_bar.provider, f"bold {C_GREEN}"),
        ))
        self.panel._chat_log.write(Text.assemble(
            ("  Model:     ", C_TEXT_DIM),
            (self.panel.status_bar.model, f"bold {C_PURPLE}"),
        ))
        self.panel._chat_log.write(Text.assemble(
            ("  Messages:  ", C_TEXT_DIM),
            (str(len(self.panel.chat_log.get_history())), C_TEXT),
        ))
        self.panel._chat_log.write(Text.assemble(
            ("  Status:    ", C_TEXT_DIM), ("Ready", f"bold {C_GREEN}"),
        ))

    def cmd_tools(self, args: str = "") -> None:
        self.panel.print_system("Available tools:")
        tools = [
            ("search_web", "Search the web for information"),
            ("read_file", "Read file contents"),
            ("write_file", "Write content to a file"),
            ("execute_shell", "Execute a shell command"),
            ("search_code", "Search code within a project"),
        ]
        for name, desc in tools:
            self.panel._chat_log.write(Text.assemble(
                (f"  {ICON_TOOL} {name:16} ", f"bold {C_CYAN}"), (desc, C_TEXT_MUTED),
            ))

    def cmd_undo(self, args: str = "") -> None:
        self.panel.print_system("Undo not yet implemented.")

    def cmd_redo(self, args: str = "") -> None:
        self.panel.print_system("Redo not yet implemented.")

    def cmd_save(self, args: str = "") -> None:
        if not args:
            self.panel.print_error("Usage: /save <filename>")
            return
        try:
            with open(args, "w") as f:
                for msg in self.panel.chat_log.get_history():
                    f.write(f"[{msg.msg_type.name}] {msg.content}\n")
            self.panel.print_success(f"Chat saved to: {args}")
        except Exception as e:
            self.panel.print_error(f"Failed to save: {e}")

    def cmd_load(self, args: str = "") -> None:
        if not args:
            self.panel.print_error("Usage: /load <filename>")
            return
        try:
            with open(args, "r") as f:
                content = f.read()
            self.panel.print_success(f"Loaded {args}")
            self.panel._chat_log.write(Text(content, C_TEXT_MUTED))
        except Exception as e:
            self.panel.print_error(f"Failed to load: {e}")

    def cmd_exit(self, args: str = "") -> None:
        self.panel.print_system("Goodbye!")
        self.panel.app.exit()

    def cmd_quit(self, args: str = "") -> None:
        self.cmd_exit(args)

    def cmd_unknown(self, args: str = "") -> None:
        self.panel.print_error("Unknown command. Type /help for available commands.")


# ---------------------------------------------------------------------------
# Demo Application
# ---------------------------------------------------------------------------

class AgentPanelDemoApp:
    """Standalone demo. Run with:  python agent_panel.py"""

    @staticmethod
    def run() -> None:
        from textual.app import App

        class DemoApp(App):
            CSS = CSS

            def compose(self) -> ComposeResult:
                self.agent = AgentPanel()
                yield self.agent

            def on_mount(self) -> None:
                self.title = "EDK_AI Agent Panel"
                asyncio.create_task(self._demo_sequence())

            async def _demo_sequence(self) -> None:
                await asyncio.sleep(0.5)

                # User message
                self.agent.print_user("Can you explain how async/await works in Python?")
                await asyncio.sleep(0.3)

                # Processing + response
                self.agent.start_processing("Thinking...")
                await asyncio.sleep(1.5)
                self.agent.stop_processing()

                self.agent.print_ai(
                    "**Async/await** in Python provides a way to write *concurrent* code "
                    "that looks and behaves like synchronous code. Here's how it works:\n\n"
                    "### Core Concepts\n\n"
                    "1. **`async def`** -- Defines a coroutine function\n"
                    "2. **`await`** -- Pauses execution until the awaited task completes\n"
                    "3. **`asyncio.run()`** -- Entry point to run the async event loop\n\n"
                    "Here's a simple example:\n\n"
                    "```python\n"
                    "import asyncio\n\n"
                    "async def fetch_data():\n"
                    "    print('Starting...')\n"
                    "    await asyncio.sleep(1)  # Non-blocking!\n"
                    "    return {'data': [1, 2, 3]}\n\n"
                    "async def main():\n"
                    "    result = await fetch_data()\n"
                    "    print(f'Got: {result}')\n\n"
                    "asyncio.run(main())\n"
                    "```\n\n"
                    "The key advantage is that while `await asyncio.sleep(1)` is running, "
                    "*other tasks can execute* -- making your program more efficient!"
                )
                await asyncio.sleep(0.5)

                # Tool call demo
                self.agent.print_tool("search_web", {"query": "Python asyncio best practices 2024"})
                await asyncio.sleep(0.8)
                self.agent.print_tool_result(
                    "search_web", "Found 5 results about Python asyncio patterns...", success=True,
                )
                await asyncio.sleep(0.3)

                # Another user message
                self.agent.print_user("Show me a more complex example with multiple tasks.")
                await asyncio.sleep(0.3)

                self.agent.start_processing("Generating code...")
                await asyncio.sleep(1.2)
                self.agent.stop_processing()

                self.agent.print_ai(
                    "Here's an example running multiple tasks concurrently:\n\n"
                    "```python\n"
                    "import asyncio\n"
                    "import aiohttp\n\n"
                    "async def fetch_url(session, url):\n"
                    "    async with session.get(url) as response:\n"
                    "        return await response.text()\n\n"
                    "async def main():\n"
                    "    urls = [\n"
                    "        'https://api.github.com',\n"
                    "        'https://httpbin.org/get',\n"
                    "        'https://jsonplaceholder.typicode.com/posts/1',\n"
                    "    ]\n"
                    "    async with aiohttp.ClientSession() as session:\n"
                    "        tasks = [fetch_url(session, url) for url in urls]\n"
                    "        results = await asyncio.gather(*tasks)\n"
                    "        for url, result in zip(urls, results):\n"
                    "            print(f'{url}: {len(result)} bytes')\n\n"
                    "asyncio.run(main())\n"
                    "```\n\n"
                    "This fetches all three URLs *concurrently* rather than sequentially."
                )
                await asyncio.sleep(0.3)

                # Error + success demo
                self.agent.print_error("Simulated error: Rate limit exceeded (429)")
                await asyncio.sleep(0.3)
                self.agent.print_success("Retry successful after 2s backoff.")

                # Update status bar
                self.agent.update_status("groq", "llama-3.3-70b", 145.0)
                self.agent.update_provider_status([
                    ("groq", "active"), ("gemini", "active"),
                    ("github", "active"), ("cerebras", "error"),
                ])

            def on_agent_panel_user_message(self, event: AgentPanel.UserMessage) -> None:
                asyncio.create_task(self._respond(event.content))

            async def _respond(self, content: str) -> None:
                self.agent.start_processing()
                await asyncio.sleep(1.0)
                self.agent.stop_processing()
                self.agent.print_ai(
                    f"You asked about: **{content}**\n\n"
                    "This is a demo response. In a real implementation, "
                    "this would be connected to an LLM API."
                )

        DemoApp().run()


# ---------------------------------------------------------------------------
# Entry Point & Exports
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    AgentPanelDemoApp.run()

__all__ = [
    "AgentPanel",
    "AgentPanelDemoApp",
    "ChatLog",
    "StatusBar",
    "InputBar",
    "Toolbar",
    "ProcessingIndicator",
    "TypingIndicator",
    "SlashCommandHandler",
    "Message",
    "MsgType",
    "CSS",
    "C_BG",
    "C_BG_SECONDARY",
    "C_BORDER",
    "C_TEXT",
    "C_TEXT_MUTED",
    "C_TEXT_DIM",
    "C_BLUE",
    "C_GREEN",
    "C_YELLOW",
    "C_RED",
    "C_PURPLE",
    "C_CYAN",
]

"""Main Textual application for Terminal Studio.

Defines :class:`StudioApp`, the top-level TUI, together with the
composite widgets that make up the interface:

* :class:`FileTree` — project file explorer
* :class:`AIPanel` — AI chat interface
* :class:`AITerminalPanel` — AI-enhanced command output panel
* :class:`StatusBar` — editor status line
* :class:`CommandPalette` — quick-action overlay
* :class:`OpenFileScreen` — simple file-open dialog
* :class:`NLPalette` — natural-language command palette
* :class:`TemplatePickerScreen` — new-project template picker
* :class:`AutoFixScreen` — apply AI-suggested fixes
* :class:`CodeActionsScreen` — context-aware code actions
* :class:`PromptScreen` — generic text-input modal
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.events import Key
from textual.screen import Screen
from textual.widgets import (
    Button,
    DirectoryTree,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    TabbedContent,
    TabPane,
    TextArea,
)

from edkai.ai.client import AIClient
from edkai.ai.providers import ProviderRegistry
from edkai.ai.code_actions import CodeAction, CodeActionsEngine
from edkai.ai.ghost import GhostEngine
from edkai.ai.inline_generator import InlineGenerator
from edkai.ai.nl_commands import NLCommandEngine
from edkai.ai.refactor import RefactorEngine
from edkai.ai.test_generator import TestGenerator
from edkai.core.auto_fix import AutoFixEngine
from edkai.core.config import StudioConfig
from edkai.core.project import Project
from edkai.core.snippets import SnippetEngine
from edkai.core.templates import TemplateManager
from edkai.core.test_runner import TestRunner

from edkai.widgets.ai_panel import AIPanel
from edkai.widgets.ai_terminal import AITerminalPanel
from edkai.widgets.editor import Editor
from edkai.widgets.file_tree import FileTree
from edkai.widgets.ghost_overlay import GhostOverlay
from edkai.widgets.git_panel import GitPanel
from edkai.widgets.nl_palette import NLPalette
from edkai.widgets.search_panel import SearchPanel
from edkai.widgets.snippet_bar import SnippetBar
from edkai.widgets.status_bar import StatusBar
from edkai.widgets.test_panel import TestPanel
from edkai.widgets.agent_panel import AgentPanel


# ---------------------------------------------------------------------------
# Modal screens
# ---------------------------------------------------------------------------


class OpenFileScreen(Screen[Optional[Path]]):
    """Modal dialog to open a file by typing its path."""

    CSS = """
    OpenFileScreen {
        align: center middle;
    }
    #dialog {
        width: 50;
        height: auto;
        border: thick $background 80%;
        background: $surface;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Open File", id="dialog-title")
            yield Input(placeholder="Path to file…", id="path-input")
            with Horizontal(id="dialog-buttons"):
                yield Button("Open", variant="primary", id="open-btn")
                yield Button("Cancel", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "open-btn":
            value = self.query_one("#path-input", Input).value.strip()
            if value:
                self.dismiss(Path(value))
            else:
                self.dismiss(None)
        elif event.button.id == "cancel-btn":
            self.dismiss(None)

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        value = self.query_one("#path-input", Input).value.strip()
        if value:
            self.dismiss(Path(value))
        else:
            self.dismiss(None)


class CommandPalette(Screen[Optional[str]]):
    """Quick-command overlay.

    Lists studio actions that can be filtered by typing and activated
    with Enter.
    """

    COMMANDS: List[tuple[str, str]] = [
        ("Open File", "open_file"),
        ("Quick Open", "quick_open"),
        ("Save File", "save_file"),
        ("New File", "new_file"),
        ("Toggle Sidebar", "toggle_sidebar"),
        ("Toggle Terminal", "toggle_terminal"),
        ("Toggle AI Panel", "toggle_ai"),
        ("Toggle Snippets", "toggle_snippet_bar"),
        ("Toggle Tests", "toggle_test_panel"),
        ("Toggle Search", "toggle_search_panel"),
        ("Toggle Git", "toggle_git_panel"),
        ("Run Code", "run_file"),
        ("Toggle Comment", "toggle_comment"),
        ("Ghost Suggest", "ghost_suggest"),
        ("Generate from Comment", "generate_from_comment"),
        ("NL Palette", "nl_palette"),
        ("Code Actions", "code_actions"),
        ("Refactor", "refactor_selection"),
        ("Optimize", "optimize_code"),
        ("New Project", "new_project"),
        ("Explain Command", "explain_last_command"),
        ("Suggest Command", "suggest_command"),
        ("Quit", "quit"),
    ]

    _filtered: List[tuple[str, str]] = []

    CSS = """
    CommandPalette {
        align: center middle;
    }
    #palette-box {
        width: 50;
        height: auto;
        max-height: 20;
        border: thick $background 80%;
        background: $surface;
        padding: 1 2;
    }
    ListView {
        height: auto;
        max-height: 12;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="palette-box"):
            yield Input(placeholder="Type a command…", id="palette-input")
            yield ListView(id="palette-list")

    def on_mount(self) -> None:
        self._refresh_list("")
        self.query_one("#palette-input", Input).focus()

    def _refresh_list(self, filter_text: str) -> None:
        list_view = self.query_one("#palette-list", ListView)
        list_view.clear()
        self._filtered = []
        ft = filter_text.lower()
        for name, action in self.COMMANDS:
            if ft in name.lower():
                self._filtered.append((name, action))
                list_view.append(ListItem(Label(name)))

    def on_input_changed(self, event: Input.Changed) -> None:
        self._refresh_list(event.value)

    def on_list_view_selected(self, _event: ListView.Selected) -> None:
        lv = self.query_one("#palette-list", ListView)
        idx = lv.index
        if 0 <= idx < len(self._filtered):
            self.dismiss(self._filtered[idx][1])

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        lv = self.query_one("#palette-list", ListView)
        idx = lv.index
        if 0 <= idx < len(self._filtered):
            self.dismiss(self._filtered[idx][1])
        else:
            self.dismiss(None)


class TemplatePickerScreen(Screen[Optional[str]]):
    """Modal screen to pick a project template."""

    CSS = """
    TemplatePickerScreen {
        align: center middle;
    }
    #dialog {
        width: 50;
        height: auto;
        max-height: 20;
        border: thick $background 80%;
        background: $surface;
        padding: 1 2;
    }
    ListView {
        height: auto;
        max-height: 12;
    }
    """

    def __init__(self, templates: List[str], descriptions: Dict[str, str], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._templates = templates
        self._descriptions = descriptions

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("New Project from Template", id="dialog-title")
            yield ListView(id="template-list")

    def on_mount(self) -> None:
        lv = self.query_one("#template-list", ListView)
        for name in self._templates:
            desc = self._descriptions.get(name, "")
            lv.append(ListItem(Label(f"{name} — {desc}")))
        if self._templates:
            lv.index = 0
            lv.focus()

    def on_list_view_selected(self, _event: ListView.Selected) -> None:
        lv = self.query_one("#template-list", ListView)
        idx = lv.index
        if 0 <= idx < len(self._templates):
            self.dismiss(self._templates[idx])
        else:
            self.dismiss(None)


class AutoFixScreen(Screen[bool]):
    """Modal screen to review and apply an AI auto-fix."""

    CSS = """
    AutoFixScreen {
        align: center middle;
    }
    #dialog {
        width: 70;
        height: auto;
        max-height: 25;
        border: thick $background 80%;
        background: $surface;
        padding: 1 2;
    }
    #explanation {
        height: auto;
        max-height: 15;
        overflow: auto;
    }
    """

    def __init__(self, explanation: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._explanation = explanation

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("AI Auto-Fix Suggestion", id="dialog-title")
            yield Static(self._explanation, id="explanation")
            with Horizontal(id="dialog-buttons"):
                yield Button("Apply (Enter)", variant="success", id="apply-btn")
                yield Button("Dismiss", variant="default", id="dismiss-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "apply-btn":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def on_key(self, event: Key) -> None:
        if event.key == "enter":
            event.stop()
            event.prevent_default()
            self.dismiss(True)


class CodeActionsScreen(Screen[Optional[CodeAction]]):
    """Modal screen to pick a context-aware code action."""

    CSS = """
    CodeActionsScreen {
        align: center middle;
    }
    #dialog {
        width: 50;
        height: auto;
        max-height: 20;
        border: thick $background 80%;
        background: $surface;
        padding: 1 2;
    }
    ListView {
        height: auto;
        max-height: 12;
    }
    """

    def __init__(self, actions: List[CodeAction], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._actions = actions

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Code Actions", id="dialog-title")
            yield ListView(id="action-list")

    def on_mount(self) -> None:
        lv = self.query_one("#action-list", ListView)
        for action in self._actions:
            lv.append(ListItem(Label(f"{action.name} ({action.kind})")))
        if self._actions:
            lv.index = 0
            lv.focus()

    def on_list_view_selected(self, _event: ListView.Selected) -> None:
        lv = self.query_one("#action-list", ListView)
        idx = lv.index
        if 0 <= idx < len(self._actions):
            self.dismiss(self._actions[idx])
        else:
            self.dismiss(None)


class PromptScreen(Screen[Optional[str]]):
    """Generic input modal."""

    CSS = """
    PromptScreen {
        align: center middle;
    }
    #dialog {
        width: 50;
        height: auto;
        border: thick $background 80%;
        background: $surface;
        padding: 1 2;
    }
    """

    def __init__(self, title: str, placeholder: str = "", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._title = title
        self._placeholder = placeholder

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self._title, id="dialog-title")
            yield Input(placeholder=self._placeholder, id="prompt-input")
            with Horizontal(id="dialog-buttons"):
                yield Button("OK", variant="primary", id="ok-btn")
                yield Button("Cancel", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ok-btn":
            self.dismiss(self.query_one("#prompt-input", Input).value)
        else:
            self.dismiss(None)

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        self.dismiss(self.query_one("#prompt-input", Input).value)


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------


class StudioApp(App):
    """Terminal Studio TUI IDE.

    Layout
    ------
    * Header
    * Horizontal split: File Tree (25%) | Editor (50%) | Right dock (0-40%) | AI Panel (25%)
    * Terminal panel (30 % height)
    * Status bar
    * Footer

    Key bindings and event routing are declared below; internal tab
    state is tracked via ``self._tabs``.
    """

    CSS = """
    StudioApp {
        layout: vertical;
    }

    #main-layout {
        layout: horizontal;
        height: 1fr;
    }

    #sidebar {
        width: 25%;
        height: 100%;
        border: solid $primary;
    }

    #center-col {
        width: 50%;
        height: 100%;
        layout: vertical;
    }

    #editor-area {
        height: 1fr;
        border: solid $primary;
    }

    #editor-area TabbedContent {
        height: 100%;
    }

    #editor-area TabPane {
        height: 100%;
    }

    #editor-with-ghost {
        height: 100%;
        layout: vertical;
    }

    #editor-with-ghost Editor {
        height: 1fr;
    }

    #ghost-overlay {
        position: absolute;
        width: auto;
        height: auto;
        background: transparent;
        border: none;
        display: none;
        text-style: dim;
        color: $text-muted;
    }

    #snippet-bar {
        height: auto;
        dock: bottom;
        display: none;
    }
    #snippet-bar.visible {
        display: flex;
    }

    #right-dock {
        width: 0;
        height: 100%;
        layout: vertical;
        display: none;
        border: solid $primary;
    }
    #right-dock.visible {
        width: 30%;
        display: block;
    }
    #right-dock.search-visible {
        width: 40%;
        display: block;
    }

    #test-panel {
        height: 1fr;
        display: none;
    }
    #search-panel {
        height: 1fr;
        display: none;
    }
    #git-panel {
        height: 1fr;
        display: none;
    }

    #ai-panel {
        width: 25%;
        height: 100%;
        border: solid $primary;
    }

    #agent-panel {
        display: none;
        height: 30%;
        border: solid $primary;
    }
    #terminal-panel {
        height: 30%;
        border: solid $primary;
    }

    #status-bar {
        height: 1;
        background: $surface-darken-1;
        color: $text;
        text-style: bold;
    }
    """

    BINDINGS = [
        Binding("ctrl+o", "open_file", "Open"),
        Binding("ctrl+p", "quick_open", "Quick Open"),
        Binding("ctrl+s", "save_file", "Save"),
        Binding("ctrl+n", "new_file", "New"),
        Binding("ctrl+b", "toggle_sidebar", "Toggle Sidebar"),
        Binding("ctrl+j", "toggle_terminal", "Toggle Terminal"),
        Binding("ctrl+shift+a", "toggle_ai", "Toggle AI"),
        Binding("ctrl+enter", "run_file", "Run"),
        Binding("f5", "run_file", "Run"),
        Binding("ctrl+forward_slash", "toggle_comment", "Comment"),
        Binding("f1", "command_palette", "Command Palette"),
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+space", "ghost_suggest", "Ghost Suggest"),
        Binding("ctrl+g", "generate_from_comment", "Generate from Comment"),
        Binding("ctrl+shift+s", "toggle_snippet_bar", "Snippets"),
        Binding("ctrl+shift+t", "toggle_test_panel", "Tests"),
        Binding("ctrl+shift+f", "toggle_search_panel", "Search"),
        Binding("ctrl+shift+g", "toggle_git_panel", "Git"),
        Binding("ctrl+a", "toggle_agent_panel", "Agent"),
        Binding("ctrl+shift+e", "explain_last_command", "Explain Command"),
        Binding("ctrl+shift+c", "suggest_command", "Suggest Command"),
        Binding("ctrl+shift+p", "nl_palette", "NL Palette"),
        Binding("ctrl+period", "code_actions", "Code Actions"),
        Binding("ctrl+shift+r", "refactor_selection", "Refactor"),
        Binding("ctrl+shift+o", "optimize_code", "Optimize"),
        Binding("ctrl+shift+n", "new_project", "New Project"),
        Binding("ctrl+shift+d", "generate_docstring", "Docstring"),
    ]

    def __init__(
        self,
        project: Project | None = None,
        config: StudioConfig | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.project = project or Project()
        self.config = config or StudioConfig.load()
        self._tabs: Dict[str, dict[str, Any]] = {}
        self._tab_counter = 0

        # AI client shared across all engines
        # AI client via provider registry (multi-provider support)
        registry = ProviderRegistry(self.config)
        self._ai_client = registry.get_client(self.config.active_provider)

        # Engines
        self._ghost_engine = GhostEngine(self._ai_client)
        self._inline_generator = InlineGenerator(self._ai_client)
        self._refactor_engine = RefactorEngine(self._ai_client)
        self._auto_fix = AutoFixEngine(self._ai_client)
        self._code_actions_engine = CodeActionsEngine(self._ai_client)
        self._nl_engine = NLCommandEngine(self._ai_client)
        self._snippet_engine = SnippetEngine()
        self._template_manager = TemplateManager(ai_client=self._ai_client)
        self._test_runner = TestRunner()
        self._test_generator = TestGenerator(self._ai_client)

        # Ghost debounce task
        self._ghost_task: asyncio.Task[Any] | None = None

        # Pending auto-fix code
        self._pending_auto_fix: Optional[str] = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-layout"):
            yield FileTree(self.project.root, id="sidebar")
            with Vertical(id="center-col"):
                with TabbedContent(id="editor-area"):
                    with TabPane("Untitled", id="tab-untitled"):
                        with Vertical(id="editor-with-ghost"):
                            yield Editor(id="editor-untitled")
                            yield GhostOverlay(id="ghost-overlay")
                yield SnippetBar(
                    snippet_engine=self._snippet_engine,
                    id="snippet-bar",
                )
            with Vertical(id="right-dock"):
                yield TestPanel(
                    runner=self._test_runner,
                    generator=self._test_generator,
                    auto_fix=self._auto_fix,
                    id="test-panel",
                )
                yield SearchPanel(
                    root=str(self.project.root),
                    id="search-panel",
                )
                yield GitPanel(
                    root=str(self.project.root),
                    id="git-panel",
                )
            yield AIPanel(
                client=self._ai_client,
                id="ai-panel",
            )
            yield AgentPanel(id="agent-panel")
        yield AITerminalPanel(
            client=self._ai_client,
            cwd=str(self.project.root),
            id="terminal-panel",
        )
        yield StatusBar(id="status-bar", project_name=self.project.root.name)
        yield Footer()

    def on_mount(self) -> None:
        """Initialise the first (empty) editor tab and restore theme."""
        editor = self.query_one("#editor-untitled", Editor)
        pane = self.query_one("#tab-untitled", TabPane)
        self._tabs["tab-untitled"] = {
            "path": None,
            "dirty": False,
            "editor": editor,
            "pane": pane,
        }
        self.status_bar.attach(editor)
        self.dark = self.config.theme == "dark"
        self._update_status()

        # Set initial context for panels
        test_panel = self.query_one("#test-panel", TestPanel)
        test_panel.set_project(str(self.project.root), "")

    # ------------------------------------------------------------------
    # Event routing — file tree
    # ------------------------------------------------------------------

    def on_directory_tree_file_selected(
        self, event: DirectoryTree.FileSelected
    ) -> None:
        """Open the file selected in the sidebar tree."""
        self.open_file(Path(event.path))

    # ------------------------------------------------------------------
    # Snippet bar
    # ------------------------------------------------------------------

    def on_snippet_bar_snippet_insert(self, event: SnippetBar.SnippetInsert) -> None:
        """Insert a snippet into the active editor."""
        info = self._active_editor_info()
        if not info:
            return
        editor = info["editor"]
        snippet = self._snippet_engine.expand(event.trigger, event.language)
        if not snippet:
            return
        row, col = editor.cursor_location
        lines = editor.text.split("\n")
        if 0 <= row < len(lines):
            lines[row] = lines[row][:col] + snippet + lines[row][col:]
            editor.text = "\n".join(lines)
            info["dirty"] = True
            self._update_tab_title(self._active_tab_id() or "")
            self._update_status()

    # ------------------------------------------------------------------
    # Search / Git / Test panel navigation
    # ------------------------------------------------------------------

    def on_search_panel_file_selected(self, event: SearchPanel.FileSelected) -> None:
        """Open a file from the search panel at a specific line."""
        self.open_file_at(Path(event.path), event.line, event.col)

    def on_git_panel_file_selected(self, event: GitPanel.FileSelected) -> None:
        """Open a file from the git panel."""
        self.open_file(Path(event.path))

    def on_jump_to_file(self, event: Any) -> None:
        """Navigate to a test failure location."""
        self.open_file_at(Path(getattr(event, "file_path", "")), getattr(event, "line", 1))

    def open_file_at(self, path: Path, line: int = 1, col: int = 1) -> None:
        """Open *path* and move cursor to (*line*, *col*)."""
        self.open_file(path)
        info = self._active_editor_info()
        if info:
            editor = info["editor"]
            # Convert 1-based to 0-based
            target_line = max(0, line - 1)
            target_col = max(0, col - 1)
            # Clamp to text bounds
            lines = editor.text.split("\n")
            if target_line >= len(lines):
                target_line = len(lines) - 1 if lines else 0
            if target_line >= 0:
                target_col = min(target_col, len(lines[target_line]))
            editor.cursor_location = (target_line, target_col)
            editor.focus()

    # ------------------------------------------------------------------
    # Ghost overlay key interception
    # ------------------------------------------------------------------

    def on_key(self, event: Key) -> None:
        """Intercept Tab for ghost acceptance and dismiss on other keys."""
        try:
            overlay = self.query_one("#ghost-overlay", GhostOverlay)
        except Exception:
            return
        if overlay.suggestion:
            if event.key == "tab":
                event.stop()
                event.prevent_default()
                overlay.accept()
                return
            # Dismiss on any printable or navigation key (not pure modifiers)
            if event.key not in (
                "shift", "ctrl", "alt", "meta", "left", "right", "up", "down",
                "home", "end", "pageup", "pagedown",
            ):
                overlay.dismiss()
        # Intercept Enter in AI panel when a pending auto-fix is available
        if event.key == "enter" and self._pending_auto_fix:
            focused = self.focused
            if focused is not None and focused.id == "message-input":
                event.stop()
                event.prevent_default()
                self._apply_auto_fix()

    # ------------------------------------------------------------------
    # Editor tab helpers
    # ------------------------------------------------------------------

    def _active_tab_id(self) -> Optional[str]:
        """Return the ID of the currently visible editor tab."""
        tabbed = self.query_one("#editor-area", TabbedContent)
        return tabbed.active

    def _active_editor_info(self) -> Dict[str, Any] | None:
        """Return the metadata dict for the active editor tab."""
        tab_id = self._active_tab_id()
        return self._tabs.get(tab_id) if tab_id else None

    def _add_editor_tab(self, path: Optional[Path], title: Optional[str] = None) -> str:
        """Create a new editor tab for *path* and return its ID.

        Args:
            path: File to open, or ``None`` for an empty buffer.
            title: Tab label; inferred from *path* when omitted.

        Returns:
            The generated tab identifier.
        """
        self._tab_counter += 1
        tab_id = f"tab-{self._tab_counter}"
        display_title = title or (path.name if path else "Untitled")
        editor = Editor(id=f"editor-{self._tab_counter}")
        pane = TabPane(display_title, editor, id=tab_id)

        tabbed = self.query_one("#editor-area", TabbedContent)
        tabbed.add_pane(pane)
        tabbed.active = tab_id

        self._tabs[tab_id] = {"path": path, "dirty": False, "editor": editor, "pane": pane}
        if path and path.is_file():
            try:
                editor.load_file(str(path))
            except OSError as exc:
                self.status_bar.update(f"Error reading {path.name}: {exc}")
        if path:
            self.project.open_file(path)
        self.status_bar.attach(editor)
        self._update_status()
        return tab_id

    def _update_tab_title(self, tab_id: str) -> None:
        """Refresh the tab label to reflect the dirty state."""
        info = self._tabs.get(tab_id)
        if not info:
            return
        path = info["path"]
        dirty = info["dirty"]
        name = path.name if path else "Untitled"
        title = f"{name}{'*' if dirty else ''}"
        pane = info.get("pane")
        if pane is not None:
            pane.title = title

    def _update_status(self) -> None:
        """Push current editor metadata to the status bar."""
        self.status_bar.refresh_display()

    # ------------------------------------------------------------------
    # Right-dock helpers
    # ------------------------------------------------------------------

    def _show_right_panel(self, panel_id: str, width_class: str) -> None:
        """Show a specific right panel, hiding others and the AI panel."""
        dock = self.query_one("#right-dock")
        ai = self.query_one("#ai-panel")
        test = self.query_one("#test-panel")
        search = self.query_one("#search-panel")
        git = self.query_one("#git-panel")

        for widget in (test, search, git):
            widget.display = False

        panel = self.query_one(f"#{panel_id}")
        panel.display = True
        dock.set_classes(width_class)
        ai.display = False

        if panel_id == "search-panel":
            self.query_one("#input-files", Input).focus()
        elif panel_id == "git-panel":
            asyncio.create_task(self.query_one("#git-panel", GitPanel).refresh_status())

    def _hide_all_right_panels(self) -> None:
        """Hide all right panels and restore the AI panel."""
        dock = self.query_one("#right-dock")
        ai = self.query_one("#ai-panel")
        test = self.query_one("#test-panel")
        search = self.query_one("#search-panel")
        git = self.query_one("#git-panel")

        for widget in (test, search, git):
            widget.display = False
        dock.set_classes("")
        ai.display = True

    # ------------------------------------------------------------------
    # Actions — file operations
    # ------------------------------------------------------------------

    def open_file(self, path: Path) -> None:
        """Open *path* in a new editor tab (or focus existing)."""
        resolved = path.resolve()
        for tab_id, info in self._tabs.items():
            if info["path"] == resolved:
                tabbed = self.query_one("#editor-area", TabbedContent)
                tabbed.active = tab_id
                return
        self._add_editor_tab(resolved)

    def action_open_file(self) -> None:
        """Show the open-file dialog."""
        def on_result(result: Optional[Path]) -> None:
            if result:
                self.open_file(result)

        self.push_screen(OpenFileScreen(), callback=on_result)

    def action_quick_open(self) -> None:
        """Alias for open-file (quick-open can be enhanced later)."""
        self.action_open_file()

    def action_new_file(self) -> None:
        """Create a new empty editor tab."""
        self._add_editor_tab(None)

    def action_save_file(self) -> None:
        """Save the active editor tab to disk."""
        info = self._active_editor_info()
        if not info:
            self.status_bar.update("No active editor")
            return
        path = info["path"]
        editor = info["editor"]
        if not path:
            self.status_bar.update("Cannot save: no file path (use Save As)")
            return
        try:
            editor.save()
            info["dirty"] = False
            self._update_tab_title(self._active_tab_id() or "")
            self.status_bar.update(f"Saved {path.name}")
        except OSError as exc:
            self.status_bar.update(f"Save failed: {exc}")

    # ------------------------------------------------------------------
    # Actions — toggles
    # ------------------------------------------------------------------

    def action_toggle_sidebar(self) -> None:
        """Show / hide the file-tree sidebar."""
        sidebar = self.query_one("#sidebar")
        sidebar.display = not sidebar.display

    def action_toggle_terminal(self) -> None:
        """Show / hide the bottom terminal panel."""
        panel = self.query_one("#terminal-panel")
        panel.display = not panel.display

    def action_toggle_ai(self) -> None:
        """Show / hide the AI assistant panel."""
        panel = self.query_one("#ai-panel")
        panel.display = not panel.display

    def action_toggle_snippet_bar(self) -> None:
        """Show / hide the snippet bar."""
        bar = self.query_one("#snippet-bar", SnippetBar)
        bar.toggle()

    def action_toggle_test_panel(self) -> None:
        """Show / hide the test panel."""
        panel = self.query_one("#test-panel", TestPanel)
        if panel.display:
            self._hide_all_right_panels()
        else:
            self._show_right_panel("test-panel", "visible")

    def action_toggle_search_panel(self) -> None:
        """Show / hide the search panel."""
        panel = self.query_one("#search-panel", SearchPanel)
        if panel.display:
            self._hide_all_right_panels()
        else:
            self._show_right_panel("search-panel", "search-visible")

    def action_toggle_git_panel(self) -> None:
        """Show / hide the git panel."""
        panel = self.query_one("#git-panel", GitPanel)
        if panel.display:
            self._hide_all_right_panels()
        else:
            self._show_right_panel("git-panel", "visible")

    # ------------------------------------------------------------------
    # Actions — run & comment
    # ------------------------------------------------------------------


    def action_toggle_agent_panel(self) -> None:
        """Show / hide the agent panel."""
        panel = self.query_one("#agent-panel", AgentPanel)
        panel.display = not panel.display

    def action_run_file(self) -> None:
        """Detect the language of the active file and execute it."""
        info = self._active_editor_info()
        if not info or not info["path"]:
            self.status_bar.update("No file to run")
            return
        path = info["path"]
        asyncio.create_task(self._run_file(path))

    async def _run_file(self, path: Path) -> None:
        """Run *path* via the external terminal panel.

        Args:
            path: Absolute path to the source file.
        """
        terminal = self.query_one("#terminal-panel", AITerminalPanel)
        ext = path.suffix.lower()

        # C/C++ needs a compile step before running
        if ext in (".c", ".cpp", ".cc", ".cxx"):
            await self._run_compiled(path, terminal)
            return

        cmd = self._build_run_command(path)
        if not cmd:
            terminal.run_command(f"No runner configured for {path.suffix}")
            return

        terminal.clear_output()
        self.status_bar.update(f"Running {path.name}…")
        await terminal.run_command(" ".join(cmd), cwd=str(self.project.root))
        self.status_bar.update(f"Finished {path.name}")

        # Auto-fix loop
        if terminal._last_exit_code != 0:
            await self._auto_fix_after_run(path, terminal)

    async def _auto_fix_after_run(self, path: Path, terminal: AITerminalPanel) -> None:
        """If the run failed, ask the AI for a fix and show it."""
        info = self._active_editor_info()
        if not info:
            return
        editor = info["editor"]
        language = self._detect_language(path)
        self.status_bar.update("Diagnosing error with AI …")
        try:
            fixed_code, explanation = await self._auto_fix.diagnose_and_fix(
                editor.text,
                terminal._last_output,
                language,
            )
        except Exception as exc:
            self.status_bar.update(f"Auto-fix failed: {exc}")
            return

        ai = self.query_one("#ai-panel", AIPanel)
        ai._add_message(
            f"[Auto-Fix] {explanation}\n\nPress Enter in the AI panel message input to apply the fix.",
            role="assistant",
        )
        self._pending_auto_fix = fixed_code
        self.status_bar.update("Auto-fix suggestion ready (press Enter in AI input to apply)")

    def _apply_auto_fix(self) -> None:
        """Apply the pending auto-fix to the active editor."""
        if not self._pending_auto_fix:
            return
        info = self._active_editor_info()
        if not info:
            return
        editor = info["editor"]
        editor.text = self._pending_auto_fix
        info["dirty"] = True
        self._update_tab_title(self._active_tab_id() or "")
        self._update_status()
        self.status_bar.update("Auto-fix applied")
        self._pending_auto_fix = None

    async def _run_compiled(self, path: Path, terminal: AITerminalPanel) -> None:
        """Compile and run a C/C++ source file.

        Args:
            path: Source file path.
            terminal: The terminal panel to run commands in.
        """
        ext = path.suffix.lower()
        compiler = "gcc" if ext == ".c" else "g++"
        binary = path.with_suffix("")

        terminal.clear_output()
        self.status_bar.update(f"Compiling {path.name}…")
        cmd_str = f"{compiler} {path.name} -o {binary.name} && ./{binary.name}"
        await terminal.run_command(cmd_str, cwd=str(self.project.root))
        self.status_bar.update(f"Finished {path.name}")

        if terminal._last_exit_code != 0:
            await self._auto_fix_after_run(path, terminal)

    def _build_run_command(self, path: Path) -> List[str] | None:
        """Return the shell command list for *path* based on extension.

        Args:
            path: Source file to execute.

        Returns:
            A list of command tokens, or ``None`` if unsupported.
        """
        ext = path.suffix.lower()
        mapping: Dict[str, List[str]] = {
            ".py": [sys.executable, str(path)],
            ".js": ["node", str(path)],
            ".sh": ["bash", str(path)],
            ".go": ["go", "run", str(path)],
            ".rs": ["cargo", "run"],
        }
        return mapping.get(ext)

    def action_toggle_comment(self) -> None:
        """Toggle a language-appropriate comment on the current line."""
        info = self._active_editor_info()
        if not info:
            return
        editor = info["editor"]
        path = info["path"]
        comment = self._comment_prefix(path)
        row, _col = editor.cursor_location
        lines = editor.text.split("\n")
        if not (0 <= row < len(lines)):
            return
        line = lines[row]
        if line.startswith(comment):
            lines[row] = line[len(comment):]
        else:
            lines[row] = comment + line
        editor.text = "\n".join(lines)
        editor.cursor_location = (row, 0)
        info["dirty"] = True
        self._update_tab_title(self._active_tab_id() or "")
        self._update_status()

    def _comment_prefix(self, path: Optional[Path]) -> str:
        """Return the single-line comment token for *path*'s language.

        Args:
            path: File path (may be ``None``).

        Returns:
            Comment string, e.g. ``"# "`` or ``"// "``.
        """
        if not path:
            return "# "
        ext = path.suffix.lower()
        c_style = {".js", ".ts", ".cpp", ".c", ".cc", ".cxx", ".java", ".go", ".rs"}
        return "// " if ext in c_style else "# "

    def _detect_language(self, path: Optional[Path]) -> str:
        """Guess a human-readable language name from *path*.

        Args:
            path: File path (may be ``None``).

        Returns:
            Language label, e.g. ``"python"`` or ``"plaintext"``.
        """
        if not path:
            return "plaintext"
        mapping: Dict[str, str] = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".go": "go",
            ".rs": "rust",
            ".c": "c",
            ".cpp": "cpp",
            ".sh": "shell",
            ".json": "json",
            ".md": "markdown",
        }
        return mapping.get(path.suffix.lower(), "plaintext")

    # ------------------------------------------------------------------
    # Actions — AI-powered features
    # ------------------------------------------------------------------

    def action_ghost_suggest(self) -> None:
        """Manually trigger a ghost text suggestion."""
        info = self._active_editor_info()
        if not info:
            return
        editor = info["editor"]
        asyncio.create_task(self._do_ghost_suggest(editor))

    async def _do_ghost_suggest(self, editor: Editor) -> None:
        """Fetch and display a ghost suggestion for *editor*."""
        path = self._active_editor_info()["path"] if self._active_editor_info() else None
        language = self._detect_language(path)
        row, col = editor.cursor_location
        suggestion = await self._ghost_engine.suggest(
            editor.text, row, col, language
        )
        overlay = self.query_one("#ghost-overlay", GhostOverlay)
        if suggestion:
            overlay.set_suggestion(
                suggestion,
                row,
                col,
                on_accept=lambda text: self._accept_ghost(text, editor),
            )
            self._position_ghost_overlay(overlay, editor)
        else:
            overlay.dismiss()

    def _accept_ghost(self, text: str, editor: Editor) -> None:
        """Insert accepted ghost text at the cursor."""
        row, col = editor.cursor_location
        lines = editor.text.split("\n")
        if not (0 <= row < len(lines)):
            return
        # Insert suggestion at cursor; handle multiline suggestions
        prefix = lines[row][:col]
        suffix = lines[row][col:]
        suggestion_lines = text.split("\n")
        if len(suggestion_lines) == 1:
            lines[row] = prefix + text + suffix
        else:
            lines[row] = prefix + suggestion_lines[0]
            for i, sl in enumerate(suggestion_lines[1:], start=row + 1):
                lines.insert(i, sl)
            # Append original suffix to last inserted line
            lines[row + len(suggestion_lines) - 1] += suffix
        editor.text = "\n".join(lines)
        # Move cursor to end of inserted text
        new_row = row + len(suggestion_lines) - 1
        new_col = len(lines[new_row]) - len(suffix) if suffix else len(lines[new_row])
        editor.cursor_location = (new_row, new_col)
        info = self._active_editor_info()
        if info:
            info["dirty"] = True
            self._update_tab_title(self._active_tab_id() or "")
            self._update_status()

    def _position_ghost_overlay(self, overlay: GhostOverlay, editor: Editor) -> None:
        """Position the ghost overlay near the cursor.

        This is a heuristic positioning; precise placement would require
        introspecting the TextArea's internal layout.
        """
        row, col = editor.cursor_location
        # Rough estimate: offset by line number width + a small padding
        line_num_width = len(str(max(1, len(editor.text.splitlines())))) + 1
        try:
            overlay.styles.offset = (col + line_num_width, row)
        except Exception:
            pass

    def action_generate_from_comment(self) -> None:
        """Replace the current comment line with AI-generated code."""
        info = self._active_editor_info()
        if not info:
            return
        editor = info["editor"]
        path = info["path"]
        row, _col = editor.cursor_location
        lines = editor.text.split("\n")
        if not (0 <= row < len(lines)):
            return
        line = lines[row].strip()
        if not line.startswith("#") and not line.startswith("//"):
            self.status_bar.update("Current line is not a comment")
            return
        language = self._detect_language(path)
        self.status_bar.update("Generating code from comment …")
        asyncio.create_task(self._do_generate_from_comment(editor, line, language, row, lines))

    async def _do_generate_from_comment(
        self,
        editor: Editor,
        line: str,
        language: str,
        row: int,
        lines: List[str],
    ) -> None:
        """Async worker for generate-from-comment."""
        generated = await self._inline_generator.generate_from_description(
            line, language, editor.text
        )
        if generated:
            lines[row] = generated
            editor.text = "\n".join(lines)
            info = self._active_editor_info()
            if info:
                info["dirty"] = True
                self._update_tab_title(self._active_tab_id() or "")
                self._update_status()
            self.status_bar.update("Code generated from comment")
        else:
            self.status_bar.update("No code generated")

    def action_explain_last_command(self) -> None:
        """Ask AI to explain the last terminal command."""
        terminal = self.query_one("#terminal-panel", AITerminalPanel)
        asyncio.create_task(terminal._ai_explain())

    def action_suggest_command(self) -> None:
        """Ask AI to suggest a terminal command for a task."""

        def on_result(task: Optional[str]) -> None:
            if task:
                terminal = self.query_one("#terminal-panel", AITerminalPanel)
                asyncio.create_task(terminal._ai_suggest_command(task))

        self.push_screen(
            PromptScreen("Describe the task for a command suggestion:", "e.g. find all Python files"),
            callback=on_result,
        )

    def action_nl_palette(self) -> None:
        """Open the natural-language command palette."""
        info = self._active_editor_info()
        context: Dict[str, Any] = {}
        if info:
            context["language"] = self._detect_language(info["path"])
            context["file_path"] = str(info["path"]) if info["path"] else ""
        palette = NLPalette(engine=self._nl_engine, context=context)

        def on_result(action: Optional[Any]) -> None:
            if action is None:
                return
            self._execute_nl_action(action)

        self.push_screen(palette, callback=on_result)

    def _execute_nl_action(self, action: Any) -> None:
        """Execute an action returned by the NL palette."""
        action_type = getattr(action, "type", "")
        params = getattr(action, "params", {}) or {}
        if action_type == "open":
            path = params.get("path")
            if path:
                self.open_file(Path(path))
        elif action_type == "save":
            self.action_save_file()
        elif action_type == "run":
            self.action_run_file()
        elif action_type == "toggle_sidebar":
            self.action_toggle_sidebar()
        elif action_type == "toggle_terminal":
            self.action_toggle_terminal()
        elif action_type == "toggle_ai":
            self.action_toggle_ai()
        elif action_type == "goto_line":
            line = params.get("line", 1)
            info = self._active_editor_info()
            if info:
                info["editor"].cursor_location = (max(0, line - 1), 0)
        elif action_type == "search":
            query = params.get("query", "")
            self.action_toggle_search_panel()
            search = self.query_one("#input-files", Input)
            search.value = query
        elif action_type == "insert_code":
            code = params.get("code", "")
            info = self._active_editor_info()
            if info:
                editor = info["editor"]
                row, col = editor.cursor_location
                lines = editor.text.split("\n")
                if 0 <= row < len(lines):
                    lines[row] = lines[row][:col] + code + lines[row][col:]
                    editor.text = "\n".join(lines)
        elif action_type == "explain":
            self.action_code_actions()
        elif action_type == "generate":
            self.action_generate_from_comment()
        else:
            self.status_bar.update(f"NL action not implemented: {action_type}")

    def action_code_actions(self) -> None:
        """Show context-aware code actions for the current cursor position."""
        info = self._active_editor_info()
        if not info:
            return
        editor = info["editor"]
        path = info["path"]
        language = self._detect_language(path)
        row, _col = editor.cursor_location
        actions = self._code_actions_engine.get_actions(row, editor.text, language)
        if not actions:
            self.status_bar.update("No code actions available")
            return

        def on_result(action: Optional[CodeAction]) -> None:
            if action:
                asyncio.create_task(self._apply_code_action(action, editor))

        self.push_screen(CodeActionsScreen(actions), callback=on_result)

    async def _apply_code_action(self, action: CodeAction, editor: Editor) -> None:
        """Apply a selected code action to the editor."""
        modified = await self._code_actions_engine.execute_action(action, editor.text)
        if modified and modified != editor.text:
            editor.text = modified
            info = self._active_editor_info()
            if info:
                info["dirty"] = True
                self._update_tab_title(self._active_tab_id() or "")
                self._update_status()
            self.status_bar.update(f"Applied: {action.name}")

    def action_refactor_selection(self) -> None:
        """Refactor the current editor selection with an instruction."""
        info = self._active_editor_info()
        if not info:
            return
        editor = info["editor"]
        selected = editor.selected_text
        if not selected:
            self.status_bar.update("No selection to refactor")
            return
        path = info["path"]
        language = self._detect_language(path)

        def on_result(instruction: Optional[str]) -> None:
            if instruction:
                self.status_bar.update("Refactoring selection …")
                asyncio.create_task(
                    self._do_refactor(editor, selected, instruction, language)
                )

        self.push_screen(
            PromptScreen("Refactor instruction:", "e.g. extract to function"),
            callback=on_result,
        )

    async def _do_refactor(
        self, editor: Editor, code: str, instruction: str, language: str
    ) -> None:
        """Async worker for refactor selection."""
        result = await self._refactor_engine.refactor_selection(code, instruction, language)
        if result:
            editor.text = editor.text.replace(code, result, 1)
            info = self._active_editor_info()
            if info:
                info["dirty"] = True
                self._update_tab_title(self._active_tab_id() or "")
                self._update_status()
            self.status_bar.update("Refactor applied")
        else:
            self.status_bar.update("Refactor failed")

    def action_optimize_code(self) -> None:
        """Optimize the current file or selection."""
        info = self._active_editor_info()
        if not info:
            return
        editor = info["editor"]
        path = info["path"]
        language = self._detect_language(path)
        code = editor.selected_text or editor.text
        if not code.strip():
            self.status_bar.update("No code to optimize")
            return
        self.status_bar.update("Optimizing code …")
        asyncio.create_task(self._do_optimize(editor, code, language))

    async def _do_optimize(self, editor: Editor, code: str, language: str) -> None:
        """Async worker for optimize."""
        result = await self._refactor_engine.optimize(code, language)
        if result:
            if editor.selected_text:
                editor.text = editor.text.replace(code, result, 1)
            else:
                editor.text = result
            info = self._active_editor_info()
            if info:
                info["dirty"] = True
                self._update_tab_title(self._active_tab_id() or "")
                self._update_status()
            self.status_bar.update("Optimization applied")
        else:
            self.status_bar.update("Optimization failed")

    def action_new_project(self) -> None:
        """Create a new project from a template."""
        templates = self._template_manager.list_templates()
        descriptions = {name: self._template_manager.describe_template(name) for name in templates}
        if not templates:
            self.status_bar.update("No templates available")
            return

        def on_result(template_name: Optional[str]) -> None:
            if not template_name:
                return

            def on_path_result(target_path: Optional[str]) -> None:
                if not target_path:
                    return
                target = Path(target_path).expanduser()
                try:
                    created = self._template_manager.create_project(
                        template_name, target, {"NAME": target.name}
                    )
                    self.status_bar.update(
                        f"Created {template_name} project with {len(created)} files"
                    )
                except Exception as exc:
                    self.status_bar.update(f"Project creation failed: {exc}")

            self.push_screen(
                PromptScreen("Target directory:", str(self.project.root / "new-project")),
                callback=on_path_result,
            )

        self.push_screen(
            TemplatePickerScreen(templates, descriptions),
            callback=on_result,
        )

    def action_generate_docstring(self) -> None:
        """Generate a docstring for the current function/class."""
        info = self._active_editor_info()
        if not info:
            return
        editor = info["editor"]
        path = info["path"]
        language = self._detect_language(path)
        row, _col = editor.cursor_location
        lines = editor.text.split("\n")
        if not (0 <= row < len(lines)):
            return
        # Find the start of the current function/class by scanning upward
        start = row
        while start >= 0 and not (lines[start].strip().startswith("def ") or lines[start].strip().startswith("class ")):
            start -= 1
        if start < 0:
            self.status_bar.update("No function/class found at cursor")
            return
        # Gather the signature lines
        sig_lines: List[str] = []
        idx = start
        while idx < len(lines) and ")" not in lines[idx]:
            sig_lines.append(lines[idx])
            idx += 1
        if idx < len(lines):
            sig_lines.append(lines[idx])
        code_block = "\n".join(sig_lines)
        self.status_bar.update("Generating docstring …")
        asyncio.create_task(self._do_generate_docstring(editor, code_block, language, start, lines))

    async def _do_generate_docstring(
        self,
        editor: Editor,
        code_block: str,
        language: str,
        start: int,
        lines: List[str],
    ) -> None:
        """Async worker for docstring generation."""
        docstring = await self._ghost_engine.generate_docstring(code_block, language)
        if docstring:
            # Insert after the signature line
            insert_idx = start
            while insert_idx < len(lines) and ")" not in lines[insert_idx]:
                insert_idx += 1
            insert_idx += 1
            indent = self._get_indent(lines[start])
            doc_lines = docstring.split("\n")
            formatted = [indent + "    \"\"\"" + doc_lines[0]]
            for dl in doc_lines[1:]:
                formatted.append(indent + "    " + dl)
            formatted.append(indent + "    \"\"\"")
            for i, dl in enumerate(formatted):
                lines.insert(insert_idx + i, dl)
            editor.text = "\n".join(lines)
            info = self._active_editor_info()
            if info:
                info["dirty"] = True
                self._update_tab_title(self._active_tab_id() or "")
                self._update_status()
            self.status_bar.update("Docstring generated")
        else:
            self.status_bar.update("Docstring generation failed")

    @staticmethod
    def _get_indent(line: str) -> str:
        """Return the leading whitespace of a line."""
        return line[: len(line) - len(line.lstrip())]

    # ------------------------------------------------------------------
    # Actions — command palette & quit
    # ------------------------------------------------------------------

    def action_command_palette(self) -> None:
        """Open the command palette overlay."""
        def on_result(action: Optional[str]) -> None:
            if action and hasattr(self, f"action_{action}"):
                getattr(self, f"action_{action}")()

        self.push_screen(CommandPalette(), callback=on_result)

    # ------------------------------------------------------------------
    # Editor events
    # ------------------------------------------------------------------

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """Mark the owning tab dirty when its text changes and debounce ghost."""
        for tab_id, info in self._tabs.items():
            editor = info["editor"]
            if editor is event.text_area and not info["dirty"] and editor.is_dirty:
                info["dirty"] = True
                self._update_tab_title(tab_id)
                self._update_status()
                break

        # Debounce ghost suggestion
        info = self._active_editor_info()
        if info and info["editor"] is event.text_area:
            self._debounce_ghost_suggest(info["editor"])
            # Update snippet bar language
            bar = self.query_one("#snippet-bar", SnippetBar)
            bar.set_language(self._detect_language(info["path"]))
            # Update test panel context
            test_panel = self.query_one("#test-panel", TestPanel)
            test_panel.set_context_code(
                str(info["path"]) if info["path"] else "",
                info["editor"].text,
            )

    def _debounce_ghost_suggest(self, editor: Editor) -> None:
        """Schedule a ghost suggestion after a 1-second delay."""
        if self._ghost_task is not None and not self._ghost_task.done():
            self._ghost_task.cancel()
        self._ghost_task = asyncio.create_task(self._ghost_suggest_after_delay(editor))

    async def _ghost_suggest_after_delay(self, editor: Editor) -> None:
        """Wait 1 s then request a ghost suggestion."""
        await asyncio.sleep(1.0)
        # Ensure the editor is still active
        info = self._active_editor_info()
        if not info or info["editor"] is not editor:
            return
        path = info["path"]
        language = self._detect_language(path)
        row, col = editor.cursor_location
        suggestion = await self._ghost_engine.suggest(editor.text, row, col, language)
        overlay = self.query_one("#ghost-overlay", GhostOverlay)
        if suggestion:
            overlay.set_suggestion(
                suggestion,
                row,
                col,
                on_accept=lambda text: self._accept_ghost(text, editor),
            )
            self._position_ghost_overlay(overlay, editor)
        else:
            overlay.dismiss()

    def on_tabbed_content_tab_activated(
        self, event: TabbedContent.TabActivated
    ) -> None:
        """Switch project focus when the user changes editor tabs."""
        tab_id = event.tab.id
        info = self._tabs.get(tab_id)
        if info and info["path"]:
            self.project.set_active_file(info["path"])
        if info:
            self.status_bar.attach(info["editor"])
            ai = self.query_one("#ai-panel", AIPanel)
            path = info["path"]
            ai.set_context(str(path) if path else "", info["editor"].text)
            # Update snippet bar and test panel context
            bar = self.query_one("#snippet-bar", SnippetBar)
            bar.set_language(self._detect_language(path))
            test_panel = self.query_one("#test-panel", TestPanel)
            test_panel.set_context_code(str(path) if path else "", info["editor"].text)
        self._update_status()

    def on_tabbed_content_tab_closed(self, event: TabbedContent.TabClosed) -> None:
        """Clean up internal state when a tab is closed."""
        pane = event.tab
        if pane.id in self._tabs:
            path = self._tabs[pane.id]["path"]
            if path:
                self.project.close_file(path)
            del self._tabs[pane.id]
        info = self._active_editor_info()
        if info:
            self.status_bar.attach(info["editor"])
        else:
            self.status_bar.detach()
        self._update_status()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_unmount(self) -> None:
        """Persist project session and configuration on exit."""
        self.config.theme = "dark" if self.dark else "light"
        self.config.save()
        self.project.save_session()

"""Natural language command palette for Terminal Studio.

A modal screen that accepts free-form natural language, parses it into
structured editor actions, and displays results with previews and
confidence scores.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import (
    Button,
    Input,
    Label,
    ListItem,
    ListView,
    Static,
)

from edkai.ai.nl_commands import EditorAction, NLCommandEngine
from edkai.ai.client import AIClient


class NLActionItem(ListItem):
    """A single result row in the NL palette."""

    DEFAULT_CSS = """
    NLActionItem {
        height: auto;
        padding: 0 1;
    }
    NLActionItem:hover {
        background: $primary-darken-2;
    }
    """

    def __init__(
        self,
        action: EditorAction,
        preview: str,
        *,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ) -> None:
        """Initialise an action item.

        Args:
            action: The parsed :class:`EditorAction`.
            preview: Human-readable preview text.
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self.action = action
        self.preview = preview

    def compose(self) -> ComposeResult:
        """Compose the action item UI."""
        yield Label(self.preview)


class NLPalette(Screen):
    """Command palette that understands natural language.

    Accepts free-form text such as ``"sort function"``,
    ``"create api endpoint for users"``, or ``"find TODOs"`` and
    displays parsed actions with confidence scores.  Supports a
    history of recent NL commands.

    Key bindings:

    * ``F1`` or ``Ctrl+Shift+P`` — open the palette.
    * ``Enter`` — activate the selected action.
    * ``Escape`` — dismiss.
    """

    BINDINGS = [
        ("escape", "dismiss", "Close"),
    ]

    _history_path: Path = Path.home() / ".config" / "edkai" / "nl_history.json"
    _recent_commands: List[str] = []

    _results: List[tuple[EditorAction, str]] = []

    show_hint: reactive[bool] = reactive(True)
    is_parsing: reactive[bool] = reactive(False)

    CSS = """
    NLPalette {
        align: center middle;
    }
    #palette-box {
        width: 70;
        height: auto;
        max-height: 25;
        border: thick $background 80%;
        background: $surface;
        padding: 1 2;
    }
    #palette-input {
        margin-bottom: 1;
    }
    #intent-label {
        text-style: bold;
        color: $accent;
        height: auto;
    }
    #confidence-label {
        color: $text-muted;
        height: auto;
    }
    ListView {
        height: auto;
        max-height: 12;
        margin: 1 0;
    }
    #hint-bar {
        height: auto;
        color: $text-muted;
        text-style: italic;
    }
    #parsing-spinner {
        height: auto;
        color: $warning;
        display: none;
    }
    """

    def __init__(
        self,
        engine: NLCommandEngine | None = None,
        context: Dict[str, Any] | None = None,
        *,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ) -> None:
        """Initialise the natural language palette.

        Args:
            engine: A :class:`NLCommandEngine` instance.  If ``None``
                a default engine without AI fallback is used.
            context: Editor context (language, file path, etc.).
            name: Screen name.
            id: Screen ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self.engine = engine or NLCommandEngine()
        self.context = context or {}
        self._load_history()

    def compose(self) -> ComposeResult:
        """Compose the NL palette UI."""
        with Vertical(id="palette-box"):
            yield Input(placeholder="Describe what you want to do…", id="palette-input")
            yield Static("Intent: —", id="intent-label")
            yield Static("Confidence: —", id="confidence-label")
            yield Static("Parsing …", id="parsing-spinner")
            yield ListView(id="palette-list")
            yield Static(
                "Try: create a function, find TODOs, explain this code, go to line 42",
                id="hint-bar",
            )

    def on_mount(self) -> None:
        """Focus the input and show recent commands if any."""
        inp = self.query_one("#palette-input", Input)
        inp.focus()
        if self._recent_commands:
            self._show_history()

    # ------------------------------------------------------------------
    # History management
    # ------------------------------------------------------------------

    def _load_history(self) -> None:
        """Load recent NL commands from disk."""
        if self._history_path.exists():
            try:
                with open(self._history_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._recent_commands = data.get("commands", [])
            except (json.JSONDecodeError, OSError):
                self._recent_commands = []

    def _save_history(self) -> None:
        """Persist recent NL commands to disk."""
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._history_path, "w", encoding="utf-8") as fh:
            json.dump({"commands": self._recent_commands[-50:]}, fh)

    def _add_to_history(self, command: str) -> None:
        """Append a command to the recent history, deduplicating."""
        if command in self._recent_commands:
            self._recent_commands.remove(command)
        self._recent_commands.append(command)
        self._save_history()

    # ------------------------------------------------------------------
    # UI refresh
    # ------------------------------------------------------------------

    def watch_show_hint(self, show: bool) -> None:  # noqa: FBT001
        """Toggle the examples hint bar."""
        self.query_one("#hint-bar", Static).display = show

    def watch_is_parsing(self, parsing: bool) -> None:  # noqa: FBT001
        """Toggle the parsing spinner."""
        self.query_one("#parsing-spinner", Static).display = parsing

    def _refresh_results(self) -> None:
        """Populate the result list with parsed actions."""
        list_view = self.query_one("#palette-list", ListView)
        list_view.clear()
        for action, preview in self._results:
            list_view.append(NLActionItem(action, preview))
        if self._results:
            self.show_hint = False
        else:
            self.show_hint = True

    def _show_history(self) -> None:
        """Show recent commands as selectable items."""
        list_view = self.query_one("#palette-list", ListView)
        list_view.clear()
        for cmd in reversed(self._recent_commands[-10:]):
            list_view.append(ListItem(Label(f"Recent: {cmd}")))
        self.show_hint = True

    def _update_intent(self, action: EditorAction) -> None:
        """Update the intent and confidence labels."""
        intent_label = self.query_one("#intent-label", Static)
        conf_label = self.query_one("#confidence-label", Static)
        intent_label.update(f"Intent: {action.type}")
        conf_label.update(f"Confidence: {action.confidence:.0%}")

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Parse the input as the user types."""
        text = event.value.strip()
        if not text:
            self._results = []
            if self._recent_commands:
                self._show_history()
            else:
                self._refresh_results()
            self.query_one("#intent-label", Static).update("Intent: —")
            self.query_one("#confidence-label", Static).update("Confidence: —")
            return

        self.is_parsing = True
        action = await self.engine.parse(text, self.context)
        self.is_parsing = False

        self._update_intent(action)
        preview = self._action_preview(action)
        self._results = [(action, preview)]
        self._refresh_results()

    async def on_input_submitted(self, _event: Input.Submitted) -> None:
        """Activate the top result when the user presses Enter."""
        if self._results:
            action, _ = self._results[0]
            text = self.query_one("#palette-input", Input).value.strip()
            if text:
                self._add_to_history(text)
            self.dismiss(action)
        else:
            self.dismiss(None)

    def on_list_view_selected(self, _event: ListView.Selected) -> None:
        """Activate a result from the list view."""
        lv = self.query_one("#palette-list", ListView)
        idx = lv.index
        if 0 <= idx < len(self._results):
            action, _ = self._results[idx]
            text = self.query_one("#palette-input", Input).value.strip()
            if text:
                self._add_to_history(text)
            self.dismiss(action)

    # ------------------------------------------------------------------
    # Preview formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _action_preview(action: EditorAction) -> str:
        """Build a human-readable preview for an action.

        Args:
            action: The parsed action.

        Returns:
            A short preview string.
        """
        params = action.params
        if action.type == "goto_line":
            return f"Go to line {params.get('line', '?')}"
        if action.type == "search":
            return f"Search for '{params.get('query', '')}'"
        if action.type == "rename":
            return f"Rename '{params.get('old')}' → '{params.get('new')}'"
        if action.type == "insert_code":
            snippet = params.get("code", "")
            first_line = snippet.splitlines()[0] if snippet else ""
            return f"Insert code: {first_line}"
        if action.type == "run":
            return f"Run {params.get('target', 'current file')}"
        if action.type == "open":
            return f"Open {params.get('path', 'file')}"
        if action.type == "save":
            return "Save file"
        if action.type == "explain":
            return "Explain code"
        if action.type == "generate":
            return f"Generate {params.get('language', 'code')}"
        if action.type == "toggle_sidebar":
            return "Toggle sidebar"
        if action.type == "toggle_terminal":
            return "Toggle terminal"
        if action.type == "toggle_ai":
            return "Toggle AI panel"
        return f"Unknown action: {action.type}"

    def action_dismiss(self) -> None:
        """Close the palette without taking an action."""
        self.dismiss(None)

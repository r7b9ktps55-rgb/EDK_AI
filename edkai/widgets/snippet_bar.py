"""Snippet bar widget for Terminal Studio.

A horizontal bar that displays context-aware snippet buttons for the
current file type.  Users can click a button to insert the snippet, or
use ``Ctrl+Shift+S`` to toggle visibility.
"""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

from textual.binding import Binding
from textual.message import Message
from textual.containers import Horizontal
from textual.widgets import Button, Label, Static

from edkai.core.snippets import SnippetEngine

if TYPE_CHECKING:
    from textual.app import ComposeResult


class SnippetBar(Horizontal):
    """Shows available snippets for the current language.

    The bar renders a row of compact snippet buttons.  Each button
    displays the trigger word and, on hover / focus, reveals a short
    description preview.  Clicking a button sends a
    :class:`SnippetInsert` message that the app can handle to insert
    the expanded snippet into the active editor.

    Key bindings
    ------------
    * ``ctrl+shift+s`` — toggle visibility.

    CSS
    ---
    The bar uses ``display: none`` / ``display: flex`` toggling and
    minimal styling so it fits neatly above the editor area.
    """

    DEFAULT_CSS = """
    SnippetBar {
        height: auto;
        padding: 0 1;
        background: $surface-darken-1;
        display: none;
    }
    SnippetBar.visible {
        display: flex;
    }
    SnippetBar Button {
        width: auto;
        min-width: 8;
        margin: 0 1;
        padding: 0 1;
        content-align: center middle;
        text-style: bold;
    }
    SnippetBar #snippet-label {
        width: auto;
        padding: 0 1;
        content-align: center middle;
        color: $text-muted;
    }
    SnippetBar #snippet-empty {
        width: 1fr;
        content-align: center middle;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("ctrl+shift+s", "toggle", "Toggle Snippets"),
    ]

    class SnippetInsert(Message):
        """Message sent when the user requests a snippet insertion.

        Attributes:
            trigger: The snippet trigger word.
            language: The language context for expansion.
        """

        def __init__(self, trigger: str, language: str) -> None:
            super().__init__()
            self.trigger = trigger
            self.language = language

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        snippet_engine: SnippetEngine | None = None,
        *,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
        disabled: bool = False,
    ) -> None:
        """Initialise the snippet bar.

        Args:
            snippet_engine: The engine that resolves triggers.  If
                ``None``, a default engine is instantiated.
            name: Widget name.
            id: Widget identifier.
            classes: CSS classes.
            disabled: Whether the widget is disabled.
        """
        super().__init__(name=name, id=id, classes=classes, disabled=disabled)
        self._engine = snippet_engine or SnippetEngine()
        self._language: str = "python"
        self._visible_bar: bool = False

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def compose(self) -> "ComposeResult":
        """Build the bar contents."""
        yield Label("Snippets:", id="snippet-label")
        self._refresh_buttons()

    def watch__visible_bar(self, visible: bool) -> None:
        """React to visibility toggle."""
        self.set_class(visible, "visible")

    def watch__language(self, language: str) -> None:
        """React to language changes."""
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        """Rebuild the snippet buttons for the current language."""
        # Remove old buttons
        for btn in self.query(Button):
            btn.remove()
        for lbl in self.query("#snippet-empty"):
            lbl.remove()

        snippets = self._engine.list_snippets(self._language)
        if not snippets:
            self.mount(Label("No snippets for this language", id="snippet-empty"))
            return

        for trigger, source, preview in snippets:
            btn = Button(
                trigger,
                id=f"btn-snippet-{trigger}",
                tooltip=f"{source}: {preview}",
                variant="primary" if source == "custom" else "default",
            )
            self.mount(btn)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_language(self, language: str) -> None:
        """Switch the context language and refresh the button row.

        Args:
            language: New language identifier (e.g. ``"python"``).
        """
        if language != self._language:
            self._language = language
            self._refresh_buttons()

    def toggle(self) -> None:
        """Toggle the bar's visibility."""
        self._visible_bar = not self._visible_bar
        self.watch__visible_bar(self._visible_bar)

    def show(self) -> None:
        """Show the bar."""
        self._visible_bar = True
        self.watch__visible_bar(True)

    def hide(self) -> None:
        """Hide the bar."""
        self._visible_bar = False
        self.watch__visible_bar(False)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle snippet button clicks."""
        btn_id = event.button.id
        if btn_id is None or not btn_id.startswith("btn-snippet-"):
            return
        trigger = btn_id[len("btn-snippet-") :]
        self.post_message(self.SnippetInsert(trigger, self._language))

    def action_toggle(self) -> None:
        """Key-binding action to toggle visibility."""
        self.toggle()

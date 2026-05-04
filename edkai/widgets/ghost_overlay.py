"""Ghost overlay widget for displaying dim inline suggestions.

Renders predicted text in a muted style immediately after the cursor.
It can be accepted (Tab) or dismissed (any other key).
"""

from __future__ import annotations
from typing import Optional

from collections.abc import Callable

from textual.reactive import reactive
from textual.widgets import Static


class GhostOverlay(Static):
    """Displays ghost (dim) text after the cursor.

    The overlay is positioned at a specific (line, column) and shows a
    suggested continuation in a muted colour.  When the user presses **Tab**
    the suggestion is "accepted" (a callback is invoked); any other
    keystroke dismisses it.

    Attributes:
        suggestion: The current ghost text string (reactive).
        target_line: 0-based line index where the suggestion starts.
        target_col: 0-based column index where the suggestion starts.
    """

    suggestion: reactive[str] = reactive("", always_update=True)
    target_line: reactive[int] = reactive(0)
    target_col: reactive[int] = reactive(0)

    DEFAULT_CSS = """
    GhostOverlay {
        color: $text-muted;
        text-style: dim;
        width: auto;
        height: auto;
        background: transparent;
        border: none;
        padding: 0;
        margin: 0;
    }
    """

    def __init__(
        self,
        *,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ) -> None:
        """Initialise the ghost overlay.

        Args:
            name: Widget name.
            id: Widget identifier.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._on_accept: Callable[[str], None] | None = None

    # ------------------------------------------------------------------
    # Reactive watchers
    # ------------------------------------------------------------------

    def watch_suggestion(self, value: str) -> None:
        """Update the displayed text whenever :attr:`suggestion` changes."""
        self.update(value)
        self.display = bool(value)

    def watch_target_line(self, _value: int) -> None:
        """Refresh layout when the target line changes."""
        self.refresh()

    def watch_target_col(self, _value: int) -> None:
        """Refresh layout when the target column changes."""
        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_suggestion(
        self,
        text: str,
        line: int,
        col: int,
        on_accept: Callable[[str], None] | None = None,
    ) -> None:
        """Position and display a new suggestion.

        Args:
            text: The ghost text to render.
            line: 0-based target line index.
            col: 0-based target column index.
            on_accept: Optional callback ``(text: str) -> None`` invoked
                when the user accepts the suggestion.
        """
        self.suggestion = text
        self.target_line = line
        self.target_col = col
        self._on_accept = on_accept
        self.display = bool(text)

    def accept(self) -> Optional[str]:
        """Accept the current suggestion.

        Invokes the optional *on_accept* callback and clears the overlay.

        Returns:
            The accepted text, or ``None`` if there was no suggestion.
        """
        if not self.suggestion:
            return None
        accepted = self.suggestion
        if self._on_accept is not None:
            try:
                self._on_accept(accepted)
            except Exception:
                # Callback errors must not break the overlay.
                pass
        self.dismiss()
        return accepted

    def dismiss(self) -> None:
        """Hide the suggestion and reset internal state."""
        self.suggestion = ""
        self._on_accept = None
        self.display = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        """Ensure the overlay starts hidden."""
        self.display = False

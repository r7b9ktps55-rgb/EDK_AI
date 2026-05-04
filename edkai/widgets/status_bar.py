"""Status bar widget for Terminal Studio.

Displays contextual information at the bottom of the editor:
current file, encoding, cursor position, language mode, and project name.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, TYPE_CHECKING

from textual.reactive import reactive
from textual.widgets import Static

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from edkai.widgets.editor import Editor


class StatusBar(Static):
    """A status bar that shows editor and project metadata.

    Monitors an attached :class:`Editor` and updates automatically
    when the cursor moves, the file changes, or the text is edited.
    """

    project_name: reactive[str] = reactive("Untitled Project")
    """Name of the project displayed on the right side."""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        width: 100%;
        background: $surface-darken-1;
        color: $text-muted;
        padding: 0 1;
        content-align: left middle;
    }
    """

    def __init__(
        self,
        *,
        project_name: str = "Untitled Project",
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
        disabled: bool = False,
    ) -> None:
        """Initialise the status bar.

        Args:
            project_name: Default project name shown on the right.
            name: Widget name.
            id: Widget identifier.
            classes: CSS classes.
            disabled: Whether the widget is disabled.
        """
        super().__init__(
            "",
            name=name,
            id=id,
            classes=classes,
            disabled=disabled,
        )
        self._editor: Editor | None = None
        self._encoding: str = "UTF-8"
        self.project_name = project_name

    # ------------------------------------------------------------------
    # Editor attachment
    # ------------------------------------------------------------------

    def attach(self, editor: Editor) -> None:
        """Attach an editor so the status bar tracks its state.

        Args:
            editor: The editor widget to monitor.
        """
        self._editor = editor
        self.refresh_display()

    def detach(self) -> None:
        """Detach the currently monitored editor."""
        self._editor = None
        self.refresh_display()

    # ------------------------------------------------------------------
    # Display update
    # ------------------------------------------------------------------

    def refresh_display(self) -> None:
        """Force an immediate update of the status text."""
        self.update(self._render_status())

    def _render_status(self) -> str:
        """Build the status string from current editor state.

        Format::

            file_name | encoding | Ln line, Col col | language | Project: name
        """
        if self._editor is None:
            return f"No file open | {self._encoding} | Ln 1, Col 1 | plain | Project: {self.project_name}"

        editor = self._editor
        file_name = editor.file_name or "Untitled"
        if editor.file_path:
            try:
                size = Path(editor.file_path).stat().st_size
                file_name = f"{file_name} ({self._human_size(size)})"
            except OSError:
                pass

        line, col = editor.cursor_line_column
        language = editor.language_mode or "plain"
        dirty = " *" if editor.is_dirty else ""

        return (
            f"{file_name}{dirty} | {self._encoding} | "
            f"Ln {line}, Col {col} | {language} | "
            f"Project: {self.project_name}"
        )

    @staticmethod
    def _human_size(size_bytes: int) -> str:
        """Return a human-readable file size."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        return f"{size_bytes / (1024 * 1024):.1f} MB"

    # ------------------------------------------------------------------
    # Reactive watchers
    # ------------------------------------------------------------------

    def watch_project_name(self, project_name: str) -> None:
        """Refresh the bar when the project name changes."""
        self.refresh_display()

    # ------------------------------------------------------------------
    # Public helpers called by the app
    # ------------------------------------------------------------------

    def on_editor_changed(self, editor: Editor) -> None:
        """Call this from the app when the editor emits a ``Changed`` event."""
        if editor is self._editor:
            self.refresh_display()

    def on_cursor_moved(self, editor: Editor) -> None:
        """Call this from the app when the cursor moves."""
        if editor is self._editor:
            self.refresh_display()

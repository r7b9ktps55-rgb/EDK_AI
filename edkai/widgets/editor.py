"""Code editor widget for Terminal Studio.

Extends Textual's ``TextArea`` with file loading, saving, dirty-state
tracking, and automatic language detection for syntax highlighting.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, TYPE_CHECKING

from textual.reactive import reactive
from textual.widgets import TextArea

from edkai.syntax.highlighter import detect_language

if TYPE_CHECKING:
    from textual.app import ComposeResult


class Editor(TextArea):
    """A code editor widget extending ``TextArea``.

    Features:
    - Syntax highlighting via Textual's built-in tree-sitter support.
    - Line numbers and auto-indent enabled.
    - Dirty-state tracking (``*`` indicator when modified).
    - ``load_file()`` / ``save()`` for disk I/O.
    - Emits ``Changed`` events on edit.
    """

    file_path: reactive[Optional[str]] = reactive(None)
    """Path of the file currently being edited, or ``None``."""

    DEFAULT_CSS = """
    Editor {
        height: 1fr;
        width: 1fr;
    }
    """

    def __init__(
        self,
        *,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
        disabled: bool = False,
    ) -> None:
        """Initialise the editor.

        Args:
            name: Widget name.
            id: Widget identifier.
            classes: CSS classes.
            disabled: Whether the widget is disabled.
        """
        super().__init__(
            text="",
            language=None,
            theme="vscode_dark",
            soft_wrap=False,
            tab_behavior="indent",
            read_only=False,
            show_cursor=True,
            show_line_numbers=True,
            line_number_start=1,
            name=name,
            id=id,
            classes=classes,
            disabled=disabled,
            highlight_cursor_line=True,
        )
        self._original_text: str = ""
        self._is_dirty: bool = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_dirty(self) -> bool:
        """Return ``True`` if the buffer has been modified since the last save."""
        return self._is_dirty

    @property
    def tab_label(self) -> str:
        """Return a label suitable for a tab, including the dirty indicator.

        Example: ``"main.py *"`` when modified.
        """
        name = self.file_name or "Untitled"
        return f"{name} *" if self._is_dirty else name

    @property
    def file_name(self) -> Optional[str]:
        """Return the basename of :attr:`file_path`, or ``None``."""
        if self.file_path is None:
            return None
        return Path(self.file_path).name

    @property
    def language_mode(self) -> Optional[str]:
        """Return the current syntax-highlighting language, or ``None``."""
        return self.language

    @property
    def cursor_line_column(self) -> tuple[int, int]:
        """Return the 1-based ``(line, column)`` of the cursor."""
        line, col = self.cursor_location
        return (line + 1, col + 1)

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_notify(widget: "Editor", message: str, severity: str = "information") -> None:
        """Send a notification if the widget is mounted in an app."""
        try:
            widget.notify(message, severity=severity)
        except Exception:
            # Widget may not be mounted in an active app (e.g. unit tests).
            pass

    def load_file(self, path: str | Path) -> None:
        """Load the contents of *path* into the editor.

        Args:
            path: File path to open.

        Raises:
            FileNotFoundError: If *path* does not exist.
            PermissionError: If *path* cannot be read.
            OSError: For other I/O errors.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            content = file_path.read_text(encoding="utf-8")
        except PermissionError as exc:
            raise PermissionError(f"Permission denied: {file_path}") from exc
        except OSError as exc:
            raise OSError(f"Error reading {file_path}: {exc}") from exc

        self._original_text = content
        self.load_text(content)
        self.file_path = str(file_path.resolve())

        lang = detect_language(str(file_path))
        if lang and lang in self.available_languages:
            self.language = lang
        else:
            # Fallback: map common unsupported names to built-ins.
            fallback = {
                "typescript": "javascript",
                "cpp": "c",
            }.get(lang)
            if fallback and fallback in self.available_languages:
                self.language = fallback
            else:
                self.language = None

        self._set_dirty_state(False)
        self.post_message(self.Changed(self))

    def save(self) -> bool:
        """Save the current buffer to disk if :attr:`file_path` is set.

        Returns:
            ``True`` if the file was saved successfully.

        Raises:
            PermissionError: If the file cannot be written.
            OSError: For other I/O errors.
        """
        if self.file_path is None:
            self._safe_notify(self, "No file path set—cannot save", severity="warning")
            return False

        file_path = Path(self.file_path)
        try:
            file_path.write_text(self.text, encoding="utf-8")
        except PermissionError as exc:
            self._safe_notify(self, f"Permission denied: {file_path}", severity="error")
            raise PermissionError(f"Permission denied: {file_path}") from exc
        except OSError as exc:
            self._safe_notify(self, f"Error saving {file_path}: {exc}", severity="error")
            raise OSError(f"Error saving {file_path}: {exc}") from exc

        self._original_text = self.text
        self._set_dirty_state(False)
        self._safe_notify(self, f"Saved {file_path.name}", severity="information")
        return True

    # ------------------------------------------------------------------
    # Dirty state
    # ------------------------------------------------------------------

    def _set_dirty_state(self, dirty: bool) -> None:
        """Update the internal dirty flag and notify listeners."""
        if self._is_dirty != dirty:
            self._is_dirty = dirty
            self.post_message(self.DirtyChanged(self, dirty))

    def check_dirty(self) -> None:
        """Recompute dirty state by comparing current text to original."""
        self._set_dirty_state(self.text != self._original_text)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def on_changed(self, event: TextArea.Changed) -> None:
        """Handle text changes to update dirty state."""
        # Ensure we only react to our own changes.
        if event.text_area is self:
            self.check_dirty()

    def on_selection_changed(self, event: TextArea.SelectionChanged) -> None:
        """Handle cursor/selection changes (bubble up for status bar)."""
        if event.text_area is self:
            self.post_message(self.Changed(self))

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    class DirtyChanged(TextArea.Changed):
        """Message sent when the dirty state toggles.

        Attributes:
            editor: The editor instance.
            dirty: ``True`` if the buffer is now dirty.
        """

        def __init__(self, editor: "Editor", dirty: bool) -> None:
            super().__init__(editor)
            self.dirty = dirty

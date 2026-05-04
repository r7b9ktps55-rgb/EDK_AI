"""File tree widget for Terminal Studio.

A file explorer built on top of Textual's ``DirectoryTree`` with support
for hidden file filtering, context menu actions, and custom messages.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Iterable, Optional, TYPE_CHECKING

from textual.reactive import reactive
from textual.widgets import DirectoryTree
from textual.widgets._directory_tree import DirEntry
from textual.widgets.tree import TreeNode

if TYPE_CHECKING:
    from textual.app import ComposeResult


class FileTree(DirectoryTree):
    """A file explorer widget that extends ``DirectoryTree``.

    Features:
    - Toggleable filtering of hidden files.
    - Emits ``FileSelected`` / ``DirectorySelected`` on click.
    - Context menu actions: New File, New Folder, Delete, Rename.
    - Keyboard navigation (inherited from ``DirectoryTree``).
    - ``refresh_tree()`` to reload the directory contents.
    """

    show_hidden: reactive[bool] = reactive(False)
    """When ``True``, hidden files and directories are shown."""

    BINDINGS = [
        *(DirectoryTree.BINDINGS if hasattr(DirectoryTree, "BINDINGS") else []),
        ("f5", "refresh_tree", "Refresh"),
        ("delete", "delete_selected", "Delete"),
    ]

    def __init__(
        self,
        path: str | Path = ".",
        *,
        show_hidden: bool = False,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
        disabled: bool = False,
    ) -> None:
        """Initialise the file tree.

        Args:
            path: Root directory to display.
            show_hidden: Whether hidden files should be visible.
            name: Widget name.
            id: Widget identifier.
            classes: CSS classes.
            disabled: Whether the widget is disabled.
        """
        super().__init__(
            path,
            name=name,
            id=id,
            classes=classes,
            disabled=disabled,
        )
        self.show_hidden = show_hidden

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        """Filter paths before adding them to the tree.

        Hidden files (starting with ``.``) are excluded unless
        :attr:`show_hidden` is ``True``.

        Args:
            paths: The paths to be filtered.

        Returns:
            The filtered paths.
        """
        if self.show_hidden:
            return paths
        return [p for p in paths if not p.name.startswith(".")]

    # ------------------------------------------------------------------
    # Reload
    # ------------------------------------------------------------------

    def refresh_tree(self) -> None:
        """Reload the directory tree from disk.

        This repopulates the tree starting at the current root path while
        attempting to preserve the expanded state of nodes.
        """
        self.clear()
        self.reset_node(
            self.root,
            str(self.path),
            DirEntry(self.PATH(self.path)),
        )
        self.root.expand()

    def action_refresh_tree(self) -> None:
        """Action handler bound to the refresh key binding."""
        self.refresh_tree()

    # ------------------------------------------------------------------
    # Context menu actions
    # ------------------------------------------------------------------

    async def action_new_file(self) -> None:
        """Create a new file in the currently selected directory."""
        node = self.cursor_node
        if node is None:
            return
        target_dir = await self._resolve_directory(node)
        if target_dir is None:
            self._safe_notify("Cannot determine target directory", severity="error")
            return
        # Prompt the user for a file name via the app
        if self.app is not None:
            self.app.push_screen(
                _FileNameInputScreen(
                    title="New File",
                    callback=lambda name: self._do_new_file(target_dir, name),
                )
            )

    async def action_new_folder(self) -> None:
        """Create a new folder in the currently selected directory."""
        node = self.cursor_node
        if node is None:
            return
        target_dir = await self._resolve_directory(node)
        if target_dir is None:
            self._safe_notify("Cannot determine target directory", severity="error")
            return
        if self.app is not None:
            self.app.push_screen(
                _FileNameInputScreen(
                    title="New Folder",
                    callback=lambda name: self._do_new_folder(target_dir, name),
                )
            )

    async def action_delete_selected(self) -> None:
        """Delete the currently selected file or directory."""
        node = self.cursor_node
        if node is None or node.data is None:
            return
        path: Path = node.data.path
        if self.app is not None:
            self.app.push_screen(
                _ConfirmScreen(
                    message=f"Delete {path.name}?",
                    callback=lambda confirmed: (
                        self._do_delete(path) if confirmed else None
                    ),
                )
            )

    async def action_rename_selected(self) -> None:
        """Rename the currently selected file or directory."""
        node = self.cursor_node
        if node is None or node.data is None:
            return
        path: Path = node.data.path
        if self.app is not None:
            self.app.push_screen(
                _FileNameInputScreen(
                    title="Rename",
                    default=path.name,
                    callback=lambda name: self._do_rename(path, name),
                )
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _safe_notify(self, message: str, severity: str = "information") -> None:
        """Send a notification if the widget is mounted in an app."""
        try:
            self.notify(message, severity=severity)
        except Exception:
            pass

    async def _resolve_directory(self, node: TreeNode[DirEntry]) -> Optional[Path]:
        """Return the directory path represented by *node*.

        If *node* points to a file, its parent directory is returned.
        """
        if node.data is None:
            return None
        path: Path = node.data.path
        if await asyncio.to_thread(path.is_dir):
            return path
        return path.parent

    def _do_new_file(self, directory: Path, name: str) -> None:
        """Create a new empty file inside *directory*."""
        if not name:
            return
        new_path = directory / name
        try:
            new_path.touch(exist_ok=False)
            self.refresh_tree()
            self._safe_notify(f"Created file {name}", severity="information")
        except FileExistsError:
            self._safe_notify(f"File '{name}' already exists", severity="error")
        except PermissionError:
            self._safe_notify("Permission denied", severity="error")
        except OSError as exc:
            self._safe_notify(f"Error creating file: {exc}", severity="error")

    def _do_new_folder(self, directory: Path, name: str) -> None:
        """Create a new folder inside *directory*."""
        if not name:
            return
        new_path = directory / name
        try:
            new_path.mkdir(parents=False, exist_ok=False)
            self.refresh_tree()
            self._safe_notify(f"Created folder {name}", severity="information")
        except FileExistsError:
            self._safe_notify(f"Folder '{name}' already exists", severity="error")
        except PermissionError:
            self._safe_notify("Permission denied", severity="error")
        except OSError as exc:
            self._safe_notify(f"Error creating folder: {exc}", severity="error")

    def _do_delete(self, path: Path) -> None:
        """Delete *path* (file or directory)."""
        try:
            if path.is_dir():
                import shutil

                shutil.rmtree(path)
            else:
                path.unlink()
            self.refresh_tree()
            self._safe_notify(f"Deleted {path.name}", severity="information")
        except PermissionError:
            self._safe_notify("Permission denied", severity="error")
        except OSError as exc:
            self._safe_notify(f"Error deleting: {exc}", severity="error")

    def _do_rename(self, path: Path, name: str) -> None:
        """Rename *path* to *name*."""
        if not name:
            return
        new_path = path.with_name(name)
        try:
            path.rename(new_path)
            self.refresh_tree()
            self._safe_notify(f"Renamed to {name}", severity="information")
        except FileExistsError:
            self._safe_notify(f"'{name}' already exists", severity="error")
        except PermissionError:
            self._safe_notify("Permission denied", severity="error")
        except OSError as exc:
            self._safe_notify(f"Error renaming: {exc}", severity="error")

    # ------------------------------------------------------------------
    # Event overrides
    # ------------------------------------------------------------------

    def on_tree_node_selected(self, event: DirectoryTree.NodeSelected) -> None:
        """Re-post file / directory selections so the app can react."""
        if event.node.data is None:
            return
        path: Path = event.node.data.path
        if path.is_dir():
            self.post_message(self.DirectorySelected(event.node, path))
        else:
            self.post_message(self.FileSelected(event.node, path))

    def watch_show_hidden(self, show_hidden: bool) -> None:
        """Refresh the tree when the hidden-files toggle changes."""
        self.refresh_tree()


# ----------------------------------------------------------------------
# Modal screens for user input (defined here to avoid extra modules)
# ----------------------------------------------------------------------

from textual.app import App  # noqa: E402
from textual.containers import Horizontal, Vertical  # noqa: E402
from textual.screen import ModalScreen  # noqa: E402
from textual.widgets import Button, Input, Label  # noqa: E402


class _FileNameInputScreen(ModalScreen[Optional[str]]):  # type: ignore[misc]
    """A small modal screen that prompts for a file or folder name."""

    DEFAULT_CSS = """
    _FileNameInputScreen {
        align: center middle;
    }
    _FileNameInputScreen > Vertical {
        width: 40;
        height: auto;
        padding: 1 2;
        border: thick $background 80%;
        background: $surface;
    }
    _FileNameInputScreen Label {
        width: 100%;
    }
    _FileNameInputScreen Input {
        width: 100%;
    }
    _FileNameInputScreen Horizontal {
        width: 100%;
        height: auto;
        content-align: right middle;
    }
    _FileNameInputScreen Button {
        margin-left: 1;
    }
    """

    def __init__(
        self,
        title: str,
        default: str = "",
        callback: "callable[[Optional[str]], None] | None" = None,
    ) -> None:
        super().__init__()
        self._title = title
        self._default = default
        self._callback = callback

    def compose(self) -> "ComposeResult":
        with Vertical():
            yield Label(self._title)
            yield Input(value=self._default, placeholder="Name…")
            with Horizontal():
                yield Button("OK", id="ok", variant="primary")
                yield Button("Cancel", id="cancel", variant="error")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._confirm(event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ok":
            inp = self.query_one(Input)
            self._confirm(inp.value)
        else:
            self._dismiss(None)

    def _confirm(self, value: str) -> None:
        self._dismiss(value)

    def _dismiss(self, result: Optional[str]) -> None:
        if self._callback is not None:
            self._callback(result)
        self.dismiss(result)


class _ConfirmScreen(ModalScreen[bool]):  # type: ignore[misc]
    """A small modal confirmation screen."""

    DEFAULT_CSS = """
    _ConfirmScreen {
        align: center middle;
    }
    _ConfirmScreen > Vertical {
        width: 40;
        height: auto;
        padding: 1 2;
        border: thick $background 80%;
        background: $surface;
    }
    _ConfirmScreen Label {
        width: 100%;
    }
    _ConfirmScreen Horizontal {
        width: 100%;
        height: auto;
        content-align: right middle;
    }
    _ConfirmScreen Button {
        margin-left: 1;
    }
    """

    def __init__(
        self,
        message: str,
        callback: "callable[[bool], None] | None" = None,
    ) -> None:
        super().__init__()
        self._message = message
        self._callback = callback

    def compose(self) -> "ComposeResult":
        with Vertical():
            yield Label(self._message)
            with Horizontal():
                yield Button("Yes", id="yes", variant="primary")
                yield Button("No", id="no", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        confirmed = event.button.id == "yes"
        if self._callback is not None:
            self._callback(confirmed)
        self.dismiss(confirmed)

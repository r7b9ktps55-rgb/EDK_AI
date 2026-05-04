"""Git panel widget for Terminal Studio.

Displays the current repository status, inline diffs, and action buttons.
Individual files can be staged/unstaged and their diffs inspected.

Toggle visibility with ``Ctrl+Shift+G``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

from textual.message import Message
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.widgets import (
    Button,
    Checkbox,
    Input,
    Label,
    ListItem,
    ListView,
    Static,
)

from edkai.core.git_manager import GitManager, GitStatus

if TYPE_CHECKING:
    from textual.app import ComposeResult


# ---------------------------------------------------------------------------
# Internal messages
# ---------------------------------------------------------------------------

class FileSelected(Message):
    """Posted when the user clicks a file in the git panel to open it."""

    def __init__(self, path: str) -> None:
        super().__init__()
        self.path = path


# ---------------------------------------------------------------------------
# GitPanel
# ---------------------------------------------------------------------------


class GitPanel(Static):
    """Git status with inline diff and actions.

    Layout::

        ┌──────────────────────────────────────┐
        │ Branch: main                         │
        │ [Stage All] [Commit] [Pull] [Push]   │
        │ ── Modified ─────────────────────────│
        │ [ ] file.py                    Diff ▶│
        │ [x] other.py                         │
        │ ── Untracked ────────────────────────│
        │ [ ] new_file.py                      │
        │ ── Staged ───────────────────────────│
        │ [x] staged.py                        │
        │ ── Diff ─────────────────────────────│
        │  - removed line                      │
        │  + added line                        │
        └──────────────────────────────────────┘
    """

    branch: reactive[str] = reactive("")
    """Current git branch name."""

    status: reactive[GitStatus | None] = reactive(None)
    """Latest parsed git status."""

    diff_text: reactive[str] = reactive("")
    """Currently displayed diff text."""

    DEFAULT_CSS = """
    GitPanel {
        width: 50;
        height: 35;
        border: thick $background 80%;
        background: $surface;
        padding: 1 2;
    }
    GitPanel #branch-label {
        text-style: bold;
        color: $primary;
    }
    GitPanel #diff-view {
        height: 1fr;
        border: solid $primary-darken-2;
        padding: 0 1;
        overflow: auto;
    }
    GitPanel .diff-removed {
        color: $error;
        text-style: dim;
    }
    GitPanel .diff-added {
        color: $success;
    }
    GitPanel .diff-header {
        color: $text-muted;
        text-style: bold;
    }
    GitPanel .diff-neutral {
        color: $text;
    }
    GitPanel .file-row {
        height: auto;
        padding: 0 1;
    }
    GitPanel ListItem {
        height: auto;
        padding: 0;
    }
    GitPanel Horizontal {
        height: auto;
    }
    GitPanel Button {
        margin: 0 1;
    }
    GitPanel #commit-input {
        width: 100%;
        margin: 1 0;
    }
    """

    BINDINGS = [
        ("ctrl+shift+g", "toggle", "Toggle Git"),
    ]

    def __init__(
        self,
        root: str = ".",
        *,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
        disabled: bool = False,
    ) -> None:
        """Initialise the git panel.

        Args:
            root: Project root directory (should be inside a git repo).
            name: Widget name.
            id: Widget identifier.
            classes: CSS classes.
            disabled: Whether the widget is disabled.
        """
        super().__init__(
            name=name,
            id=id,
            classes=classes,
            disabled=disabled,
        )
        self._root = root
        self._manager = GitManager()
        self._staged_set: set[str] = set()
        self._refresh_task: asyncio.Task[None] | None = None

    def compose(self) -> "ComposeResult":
        with Vertical():
            yield Label("Branch: --", id="branch-label")
            with Horizontal(id="action-bar"):
                yield Button("Stage All", id="btn-stage-all", variant="primary")
                yield Button("Commit", id="btn-commit", variant="success")
                yield Button("Pull", id="btn-pull", variant="warning")
                yield Button("Push", id="btn-push", variant="warning")
            yield Input(placeholder="Commit message…", id="commit-input")
            yield Label("Modified", classes="mode-label")
            yield ListView(id="list-modified")
            yield Label("Untracked", classes="mode-label")
            yield ListView(id="list-untracked")
            yield Label("Staged", classes="mode-label")
            yield ListView(id="list-staged")
            yield Label("Diff", classes="mode-label")
            yield Static("", id="diff-view")

    def on_mount(self) -> None:
        """Start background refresh when mounted."""
        asyncio.create_task(self._refresh_loop())

    # ------------------------------------------------------------------
    # Background refresh
    # ------------------------------------------------------------------

    async def _refresh_loop(self) -> None:
        """Poll git status periodically while mounted."""
        while self.is_mounted:
            if self.display:
                await self.refresh_status()
            await asyncio.sleep(5.0)

    async def refresh_status(self) -> None:
        """Fetch and render the latest git status."""
        new_status = await self._manager.status(self._root)
        self.status = new_status
        self.branch = await self._manager.get_branch(self._root)

    def watch_branch(self, branch: str) -> None:
        """Update the branch label."""
        label = self.query_one("#branch-label", Label)
        label.update(f"Branch: {branch or '--'}")

    def watch_status(self, status: GitStatus | None) -> None:
        """Re-render the file lists when status changes."""
        if status is None:
            return

        # Modified
        mod_list = self.query_one("#list-modified", ListView)
        mod_list.clear()
        for f in status.modified:
            checked = f in status.staged
            mod_list.append(
                ListItem(
                    Horizontal(
                        Checkbox(f, value=checked, id=f"chk-mod-{f}"),
                        Button("Diff", id=f"btn-diff-{f}"),
                    )
                )
            )

        # Untracked
        unt_list = self.query_one("#list-untracked", ListView)
        unt_list.clear()
        for f in status.untracked:
            unt_list.append(
                ListItem(
                    Checkbox(f, value=False, id=f"chk-unt-{f}")
                )
            )

        # Staged
        stg_list = self.query_one("#list-staged", ListView)
        stg_list.clear()
        for f in status.staged:
            stg_list.append(
                ListItem(
                    Checkbox(f, value=True, id=f"chk-stg-{f}")
                )
            )

    def watch_diff_text(self, text: str) -> None:
        """Render the diff with inline colour coding."""
        view = self.query_one("#diff-view", Static)
        if not text:
            view.update("(select a file to see diff)")
            return

        lines: List[str] = []
        for raw in text.splitlines():
            if raw.startswith("---") or raw.startswith("+++") or raw.startswith("@@"):
                lines.append(f"[b]{raw}[/b]")
            elif raw.startswith("-"):
                lines.append(f"[red]{raw}[/red]")
            elif raw.startswith("+"):
                lines.append(f"[green]{raw}[/green]")
            else:
                lines.append(raw)
        view.update("\n".join(lines))

    # ------------------------------------------------------------------
    # Event handlers — buttons
    # ------------------------------------------------------------------

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle action-bar and per-file diff buttons."""
        btn_id = event.button.id or ""

        if btn_id == "btn-stage-all":
            if self.status:
                for f in self.status.modified + self.status.untracked:
                    await self._manager.stage(str(Path(self._root) / f))
            await self.refresh_status()

        elif btn_id == "btn-commit":
            inp = self.query_one("#commit-input", Input)
            msg = inp.value.strip()
            if msg:
                ok = await self._manager.commit(msg, self._root)
                if ok:
                    inp.value = ""
                await self.refresh_status()

        elif btn_id == "btn-pull":
            ok, output = await self._manager.pull(self._root)
            self._safe_notify(f"Pull: {output}", "information" if ok else "error")
            await self.refresh_status()

        elif btn_id == "btn-push":
            ok, output = await self._manager.push(self._root)
            self._safe_notify(f"Push: {output}", "information" if ok else "error")
            await self.refresh_status()

        elif btn_id.startswith("btn-diff-"):
            file_name = btn_id[len("btn-diff-"):]
            file_path = str(Path(self._root) / file_name)
            diff = await self._manager.diff(file_path)
            self.diff_text = diff

    # ------------------------------------------------------------------
    # Event handlers — checkboxes (stage / unstage)
    # ------------------------------------------------------------------

    async def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Stage or unstage a file when its checkbox is toggled."""
        chk_id = event.checkbox.id or ""
        file_name = ""
        if chk_id.startswith("chk-mod-"):
            file_name = chk_id[len("chk-mod-"):]
        elif chk_id.startswith("chk-unt-"):
            file_name = chk_id[len("chk-unt-"):]
        elif chk_id.startswith("chk-stg-"):
            file_name = chk_id[len("chk-stg-"):]

        if not file_name:
            return

        file_path = str(Path(self._root) / file_name)
        if event.value:
            await self._manager.stage(file_path)
        else:
            await self._manager.unstage(file_path)
        await self.refresh_status()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_toggle(self) -> None:
        """Toggle panel visibility."""
        self.display = not self.display
        if self.display:
            asyncio.create_task(self.refresh_status())

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _safe_notify(self, message: str, severity: str = "information") -> None:
        """Send a notification if possible."""
        try:
            self.notify(message, severity=severity)
        except Exception:
            pass

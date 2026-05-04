"""Search panel widget for Terminal Studio.

Provides three search modes — **Files**, **Content**, and **Symbols** —
with real-time fuzzy matching, result lists, and keyboard navigation.
Results can be clicked or activated with Enter to open the file at the
relevant position.

Toggle visibility with ``Ctrl+Shift+F``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, List, Optional, TYPE_CHECKING

from textual.message import Message
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import (
    Button,
    Input,
    Label,
    ListItem,
    ListView,
    Static,
    TabbedContent,
    TabPane,
)

from edkai.core.fuzzy_search import ContentResult, FuzzySearcher, SearchResult
from edkai.core.symbols import Symbol, SymbolExtractor

if TYPE_CHECKING:
    from textual.app import ComposeResult


# ---------------------------------------------------------------------------
# Internal messages
# ---------------------------------------------------------------------------

class FileSelected(Message):
    """Posted when the user selects a file search result."""

    def __init__(self, path: str, line: int = 1, col: int = 1) -> None:
        super().__init__()
        self.path = path
        self.line = line
        self.col = col


# ---------------------------------------------------------------------------
# SearchPanel
# ---------------------------------------------------------------------------


class SearchPanel(Static):
    """Advanced search with file/content/symbol modes.

    UI layout::

        ┌─────────────────────────────────────┐
        │ [Files] [Content] [Symbols]         │
        │ Search: __________________________  │
        │                                     │
        │  > result_1.py          score 120 │
        │  > result_2.py           score 95 │
        │  ...                                │
        └─────────────────────────────────────┘

    Results are clickable and trigger :class:`FileSelected`.
    """

    searching: reactive[bool] = reactive(False)
    """``True`` while an async search is in flight."""

    DEFAULT_CSS = """
    SearchPanel {
        width: 60;
        height: 30;
        border: thick $background 80%;
        background: $surface;
        padding: 1 2;
    }
    SearchPanel Input {
        width: 100%;
        margin: 1 0;
    }
    SearchPanel ListView {
        width: 100%;
        height: 1fr;
        border: solid $primary-darken-2;
    }
    SearchPanel ListItem {
        height: auto;
        padding: 0 1;
    }
    SearchPanel .search-meta {
        color: $text-muted;
        text-style: dim;
    }
    SearchPanel .highlight {
        text-style: bold underline;
        color: $text-accent;
    }
    SearchPanel .mode-label {
        text-style: bold;
        color: $primary;
    }
    """

    BINDINGS = [
        ("ctrl+shift+f", "toggle", "Toggle Search"),
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
        """Initialise the search panel.

        Args:
            root: Project root directory to search within.
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
        self._searcher = FuzzySearcher()
        self._symbol_extractor = SymbolExtractor()
        self._debounce_task: asyncio.Task[Any] | None = None
        self._last_query: str = ""

    def compose(self) -> "ComposeResult":
        with Vertical():
            with TabbedContent(id="search-tabs"):
                with TabPane("Files", id="tab-files"):
                    yield Input(placeholder="Fuzzy search files…", id="input-files")
                    yield ListView(id="list-files")
                with TabPane("Content", id="tab-content"):
                    yield Input(placeholder="Search in file contents…", id="input-content")
                    yield ListView(id="list-content")
                with TabPane("Symbols", id="tab-symbols"):
                    yield Input(placeholder="Search symbols…", id="input-symbols")
                    yield ListView(id="list-symbols")

    def on_mount(self) -> None:
        """Focus the first input when the panel is mounted."""
        self.query_one("#input-files", Input).focus()

    # ------------------------------------------------------------------
    # Debounced search
    # ------------------------------------------------------------------

    def _schedule_search(self, query: str, mode: str, delay: float = 0.25) -> None:
        """Cancel any pending search and schedule a new one.

        Args:
            query: User input.
            mode: One of ``files``, ``content``, ``symbols``.
            delay: Seconds to wait before running the search.
        """
        if self._debounce_task is not None and not self._debounce_task.done():
            self._debounce_task.cancel()
        self._debounce_task = asyncio.create_task(
            self._debounced_search(query, mode, delay)
        )

    async def _debounced_search(
        self, query: str, mode: str, delay: float
    ) -> None:
        """Wait *delay* seconds then execute the search."""
        await asyncio.sleep(delay)
        if query != self._last_query:
            self._last_query = query
        self.searching = True
        try:
            if mode == "files":
                results = await self._searcher.search_files(query, self._root)
                self._render_files(results)
            elif mode == "content":
                results = await self._searcher.search_content(query, self._root)
                self._render_content(results)
            elif mode == "symbols":
                results = self._symbol_extractor.search_symbols(query, self._root)
                self._render_symbols(results)
        except Exception as exc:
            self._show_error(str(exc), mode)
        finally:
            self.searching = False

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    def _render_files(self, results: List[SearchResult]) -> None:
        """Populate the Files result list."""
        lv = self.query_one("#list-files", ListView)
        lv.clear()
        for r in results:
            name = Path(r.path).name
            dir_part = str(Path(r.path).parent.relative_to(Path(self._root).resolve()))
            label_text = f"{name}\n  [dir: {dir_part}]  score: {r.score}"
            lv.append(ListItem(Label(label_text, classes="search-item")))
        self._file_results = results

    def _render_content(self, results: List[ContentResult]) -> None:
        """Populate the Content result list."""
        lv = self.query_one("#list-content", ListView)
        lv.clear()
        self._content_results = results
        for r in results:
            short_file = Path(r.file).name
            label_text = f"{short_file}:{r.line}:{r.col}\n  {r.match_line.strip()[:80]}"
            lv.append(ListItem(Label(label_text, classes="search-item")))

    def _render_symbols(self, results: List[Symbol]) -> None:
        """Populate the Symbols result list."""
        lv = self.query_one("#list-symbols", ListView)
        lv.clear()
        self._symbol_results = results
        for s in results:
            short_file = Path(s.file).name
            label_text = f"{s.name} ({s.type})\n  [file: {short_file}:{s.line}]  {s.signature[:60]}"
            lv.append(ListItem(Label(label_text, classes="search-item")))

    def _show_error(self, message: str, mode: str) -> None:
        """Display an error in the given mode's list."""
        list_id = f"list-{mode}"
        lv = self.query_one(f"#{list_id}", ListView)
        lv.clear()
        lv.append(ListItem(Label(f"Error: {message}", classes="search-meta")))

    # ------------------------------------------------------------------
    # Event handlers — input changes
    # ------------------------------------------------------------------

    def on_input_changed(self, event: Input.Changed) -> None:
        """Route input change to the correct search mode."""
        inp_id = event.input.id
        if not inp_id:
            return
        query = event.value.strip()
        if "files" in inp_id:
            self._schedule_search(query, "files")
        elif "content" in inp_id:
            self._schedule_search(query, "content")
        elif "symbols" in inp_id:
            self._schedule_search(query, "symbols")

    # ------------------------------------------------------------------
    # Event handlers — list selections
    # ------------------------------------------------------------------

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Open the selected result in the editor."""
        # Determine which tab is active
        tabs = self.query_one("#search-tabs", TabbedContent)
        active = tabs.active

        if active == "tab-files":
            idx = self.query_one("#list-files", ListView).index
            results = getattr(self, "_file_results", [])
            if 0 <= idx < len(results):
                r = results[idx]
                self.post_message(FileSelected(r.path))
        elif active == "tab-content":
            idx = self.query_one("#list-content", ListView).index
            results = getattr(self, "_content_results", [])
            if 0 <= idx < len(results):
                r = results[idx]
                self.post_message(FileSelected(r.file, r.line, r.col))
        elif active == "tab-symbols":
            idx = self.query_one("#list-symbols", ListView).index
            results = getattr(self, "_symbol_results", [])
            if 0 <= idx < len(results):
                s = results[idx]
                self.post_message(FileSelected(s.file, s.line, s.col))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_toggle(self) -> None:
        """Toggle panel visibility."""
        self.display = not self.display
        if self.display:
            self.query_one("#input-files", Input).focus()

    def watch_searching(self, searching: bool) -> None:
        """Update UI when search state changes."""
        # Optional: show a spinner or dim the results while searching.
        pass

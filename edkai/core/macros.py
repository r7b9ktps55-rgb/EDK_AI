"""Macro recorder for Terminal Studio.

Records sequences of editor actions (insertions, cursor movements,
deletions) and can replay them on any compatible editor widget.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from edkai.core.config import DEFAULT_CONFIG_DIR

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

DEFAULT_MACRO_DIR = DEFAULT_CONFIG_DIR / "macros"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Macro:
    """A recorded macro — a list of editor action steps.

    Attributes:
        name: Human-readable macro name.
        steps: Ordered list of action dictionaries.
    """

    name: str = "untitled"
    steps: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise the macro to a plain dictionary."""
        return {"name": self.name, "steps": self.steps}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Macro":
        """Restore a macro from a dictionary."""
        return cls(name=data.get("name", "untitled"), steps=data.get("steps", []))


# ---------------------------------------------------------------------------
# MacroRecorder
# ---------------------------------------------------------------------------

class MacroRecorder:
    """Records keystrokes and replays them.

    A macro is a list of steps, each a dict with at minimum an
    ``"action"`` key.  Supported actions:

    * ``insert`` — ``{"action": "insert", "text": "..."}``
    * ``delete`` — ``{"action": "delete", "count": 1}``
    * ``move`` — ``{"action": "move", "direction": "up|down|left|right"}``
    * ``goto`` — ``{"action": "goto", "row": 0, "col": 0}``
    * ``select`` — ``{"action": "select", "start_row": 0, "start_col": 0,
      "end_row": 0, "end_col": 0}``
    * ``replace`` — ``{"action": "replace", "old": "...", "new": "..."}``

    Example:
        >>> recorder = MacroRecorder()
        >>> recorder.start_recording()
        >>> recorder.record_insert("hello")
        >>> recorder.record_move("right")
        >>> macro = recorder.stop_recording()
        >>> macro.name = "greet"
        >>> recorder.save_macro("greet", macro)
    """

    def __init__(self) -> None:
        """Initialise the recorder with an empty state."""
        self._recording: List[Dict[str, Any]] = []
        self._is_recording: bool = False
        self._last_macro: Macro | None = None
        self._macro_dir: Path = DEFAULT_MACRO_DIR
        self._macro_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Recording controls
    # ------------------------------------------------------------------

    def start_recording(self) -> None:
        """Begin capturing editor actions."""
        self._recording = []
        self._is_recording = True

    def stop_recording(self) -> Macro:
        """Stop capturing and return the recorded macro.

        Returns:
            A :class:`Macro` containing all recorded steps.

        Raises:
            RuntimeError: If called while not recording.
        """
        if not self._is_recording:
            raise RuntimeError("Not currently recording a macro")
        self._is_recording = False
        macro = Macro(name="recording", steps=list(self._recording))
        self._last_macro = macro
        return macro

    def is_recording(self) -> bool:
        """Return ``True`` if the recorder is currently capturing."""
        return self._is_recording

    # ------------------------------------------------------------------
    # Step recorders
    # ------------------------------------------------------------------

    def record_insert(self, text: str) -> None:
        """Record an insertion action.

        Args:
            text: The text that was inserted.
        """
        if self._is_recording:
            self._recording.append({"action": "insert", "text": text})

    def record_delete(self, count: int = 1) -> None:
        """Record a deletion action.

        Args:
            count: Number of characters / items deleted.
        """
        if self._is_recording:
            self._recording.append({"action": "delete", "count": count})

    def record_move(self, direction: str) -> None:
        """Record a cursor-movement action.

        Args:
            direction: One of ``"up"``, ``"down"``, ``"left"``, ``"right"``.
        """
        if self._is_recording:
            self._recording.append({"action": "move", "direction": direction})

    def record_goto(self, row: int, col: int) -> None:
        """Record a direct cursor-jump action.

        Args:
            row: 0-based target row.
            col: 0-based target column.
        """
        if self._is_recording:
            self._recording.append({"action": "goto", "row": row, "col": col})

    def record_select(
        self,
        start_row: int,
        start_col: int,
        end_row: int,
        end_col: int,
    ) -> None:
        """Record a selection action.

        Args:
            start_row: 0-based selection start row.
            start_col: 0-based selection start column.
            end_row: 0-based selection end row.
            end_col: 0-based selection end column.
        """
        if self._is_recording:
            self._recording.append(
                {
                    "action": "select",
                    "start_row": start_row,
                    "start_col": start_col,
                    "end_row": end_row,
                    "end_col": end_col,
                }
            )

    def record_replace(self, old: str, new: str) -> None:
        """Record a replacement action.

        Args:
            old: Text that was replaced.
            new: Text that replaced it.
        """
        if self._is_recording:
            self._recording.append({"action": "replace", "old": old, "new": new})

    def record_custom(self, step: Dict[str, Any]) -> None:
        """Record an arbitrary custom action step.

        Args:
            step: A dictionary describing the action. Must contain an
                ``"action"`` key.
        """
        if self._is_recording:
            self._recording.append(step)

    # ------------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------------

    def play(self, macro: Macro, editor: Any) -> None:
        """Replay *macro* on *editor*.

        The editor must expose a TextArea-compatible API:

        * ``insert(text, location)`` — insert text at a location.
        * ``text`` property — read / write full buffer.
        * ``cursor_location`` property — read / write cursor as ``(row, col)``.

        Args:
            macro: The macro to replay.
            editor: The target editor widget.

        Raises:
            ValueError: If an action in the macro is not supported.
        """
        for step in macro.steps:
            action = step.get("action")
            if action == "insert":
                self._do_insert(editor, step)
            elif action == "delete":
                self._do_delete(editor, step)
            elif action == "move":
                self._do_move(editor, step)
            elif action == "goto":
                self._do_goto(editor, step)
            elif action == "select":
                self._do_select(editor, step)
            elif action == "replace":
                self._do_replace(editor, step)
            else:
                raise ValueError(f"Unsupported macro action: {action}")

    def replay_last(self, editor: Any) -> None:
        """Replay the most recently recorded or played macro.

        Args:
            editor: The target editor widget.

        Raises:
            RuntimeError: If no macro has been recorded yet.
        """
        if self._last_macro is None:
            raise RuntimeError("No macro has been recorded yet")
        self.play(self._last_macro, editor)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_macro(self, name: str, macro: Macro) -> Path:
        """Save a macro to disk.

        Args:
            name: File-friendly macro name (used as filename).
            macro: The macro to persist.

        Returns:
            The path to the saved JSON file.
        """
        file_path = self._macro_dir / f"{name}.json"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as fh:
            json.dump(macro.to_dict(), fh, indent=2)
        return file_path

    def load_macro(self, name: str) -> Macro:
        """Load a previously saved macro.

        Args:
            name: Macro name (filename without extension).

        Returns:
            A reconstructed :class:`Macro`.

        Raises:
            FileNotFoundError: If the macro file does not exist.
            json.JSONDecodeError: If the file is malformed.
        """
        file_path = self._macro_dir / f"{name}.json"
        with open(file_path, "r", encoding="utf-8") as fh:
            data: Dict[str, Any] = json.load(fh)
        return Macro.from_dict(data)

    def delete_macro(self, name: str) -> None:
        """Remove a saved macro from disk.

        Args:
            name: Macro name (filename without extension).

        Raises:
            FileNotFoundError: If the macro file does not exist.
        """
        file_path = self._macro_dir / f"{name}.json"
        file_path.unlink()

    def list_macros(self) -> List[str]:
        """Return a list of all saved macro names.

        Returns:
            Sorted list of macro names (without ``.json`` extension).
        """
        if not self._macro_dir.exists():
            return []
        return sorted(
            p.stem for p in self._macro_dir.iterdir() if p.suffix == ".json"
        )

    def rename_macro(self, old_name: str, new_name: str) -> Path:
        """Rename a saved macro on disk.

        Args:
            old_name: Current macro name.
            new_name: Desired macro name.

        Returns:
            The new file path.
        """
        old_path = self._macro_dir / f"{old_name}.json"
        new_path = self._macro_dir / f"{new_name}.json"
        old_path.rename(new_path)
        return new_path

    # ------------------------------------------------------------------
    # Playback helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _do_insert(editor: Any, step: Dict[str, Any]) -> None:
        """Execute an insert step on *editor*."""
        text = step.get("text", "")
        if hasattr(editor, "insert"):
            row, col = editor.cursor_location
            editor.insert(text, (row, col))
        else:
            editor.text = editor.text + text

    @staticmethod
    def _do_delete(editor: Any, step: Dict[str, Any]) -> None:
        """Execute a delete step on *editor*."""
        count = step.get("count", 1)
        if hasattr(editor, "delete"):
            row, col = editor.cursor_location
            editor.delete((row, col), (row, col + count))
        else:
            lines = editor.text.split("\n")
            row, col = editor.cursor_location
            line = lines[row]
            before = line[:col]
            after = line[col + count :]
            lines[row] = before + after
            editor.text = "\n".join(lines)

    @staticmethod
    def _do_move(editor: Any, step: Dict[str, Any]) -> None:
        """Execute a cursor-move step on *editor*."""
        direction = step.get("direction", "right")
        row, col = editor.cursor_location
        lines: List[str] = editor.text.split("\n")

        if direction == "up" and row > 0:
            row -= 1
            col = min(col, len(lines[row]))
        elif direction == "down" and row + 1 < len(lines):
            row += 1
            col = min(col, len(lines[row]))
        elif direction == "left" and col > 0:
            col -= 1
        elif direction == "right" and col < len(lines[row]):
            col += 1

        editor.cursor_location = (row, col)

    @staticmethod
    def _do_goto(editor: Any, step: Dict[str, Any]) -> None:
        """Execute a goto step on *editor*."""
        row = step.get("row", 0)
        col = step.get("col", 0)
        editor.cursor_location = (row, col)

    @staticmethod
    def _do_select(editor: Any, step: Dict[str, Any]) -> None:
        """Execute a select step on *editor*."""
        if hasattr(editor, "selection"):
            start = (step["start_row"], step["start_col"])
            end = (step["end_row"], step["end_col"])
            editor.selection = (start, end)

    @staticmethod
    def _do_replace(editor: Any, step: Dict[str, Any]) -> None:
        """Execute a replace step on *editor*."""
        old = step.get("old", "")
        new = step.get("new", "")
        editor.text = editor.text.replace(old, new, 1)

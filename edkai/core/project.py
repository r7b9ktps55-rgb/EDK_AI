"""Project session management for Terminal Studio.

Tracks open files, the active editor tab, project root, and a list of
recently opened projects. Sessions can be saved and restored across
application restarts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_SESSION_DIR = Path.home() / ".config" / "edkai"
DEFAULT_SESSION_PATH = DEFAULT_SESSION_DIR / "session.json"
MAX_RECENT_PROJECTS = 10


class Project:
    """Represents a single project session.

    Keeps track of the project root directory, currently open files,
    which file is active in the editor, and a global list of recently
    opened projects.
    """

    def __init__(self, root: Path | Optional[str] = None) -> None:
        """Initialise a new project session.

        Args:
            root: Filesystem path to the project root directory.
                Defaults to the current working directory.
        """
        self.root: Path = Path(root) if root else Path.cwd()
        self.open_files: List[Path] = []
        self.active_file: Optional[Path] = None
        self.recent_projects: List[str] = []

    def set_root(self, root: Path | str) -> None:
        """Change the project root and update recent projects list.

        Args:
            root: New project root directory.
        """
        self.root = Path(root).resolve()
        self._add_to_recent(str(self.root))

    def open_file(self, path: Path | str) -> None:
        """Register a file as open in the session.

        If the file is not already tracked it is appended to the list
        and becomes the active file.

        Args:
            path: Path to the file being opened.
        """
        file_path = Path(path).resolve()
        if file_path not in self.open_files:
            self.open_files.append(file_path)
        self.active_file = file_path

    def close_file(self, path: Path | str) -> None:
        """Remove a file from the open files list.

        If the closed file was the active file, the active file is
        reset to the last remaining open file, or ``None`` if empty.

        Args:
            path: Path to the file being closed.
        """
        file_path = Path(path).resolve()
        if file_path in self.open_files:
            self.open_files.remove(file_path)
        if self.active_file == file_path:
            self.active_file = self.open_files[-1] if self.open_files else None

    def set_active_file(self, path: Path | str) -> None:
        """Set the currently focused file without adding it.

        Args:
            path: Path to the file that should become active.
        """
        self.active_file = Path(path).resolve()

    def _add_to_recent(self, project_path: str) -> None:
        """Insert *project_path* at the front of the recent list.

        Duplicates are removed and the list is truncated to
        ``MAX_RECENT_PROJECTS``.
        """
        if project_path in self.recent_projects:
            self.recent_projects.remove(project_path)
        self.recent_projects.insert(0, project_path)
        if len(self.recent_projects) > MAX_RECENT_PROJECTS:
            self.recent_projects = self.recent_projects[:MAX_RECENT_PROJECTS]

    def to_dict(self) -> Dict[str, Any]:
        """Serialise the session to a plain dictionary.

        Returns:
            Dictionary suitable for JSON encoding.
        """
        return {
            "root": str(self.root),
            "open_files": [str(p) for p in self.open_files],
            "active_file": str(self.active_file) if self.active_file else None,
            "recent_projects": self.recent_projects,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Project":
        """Restore a project session from a dictionary.

        Args:
            data: Dictionary previously produced by :meth:`to_dict`.

        Returns:
            A reconstructed :class:`Project` instance.
        """
        root = data.get("root", str(Path.cwd()))
        instance = cls(root)
        instance.open_files = [Path(p) for p in data.get("open_files", [])]
        active = data.get("active_file")
        instance.active_file = Path(active) if active else None
        instance.recent_projects = data.get("recent_projects", [])
        return instance

    def save_session(self, path: Optional[Path] = None) -> None:
        """Persist the session to disk.

        Args:
            path: Target JSON file. Defaults to
                ``~/.config/edkai/session.json``.

        Raises:
            OSError: If writing to disk fails.
        """
        session_path = path or DEFAULT_SESSION_PATH
        session_path.parent.mkdir(parents=True, exist_ok=True)
        with open(session_path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2)

    @classmethod
    def restore_session(cls, path: Optional[Path] = None) -> "Project":
        """Load a previously saved session.

        If the file does not exist or is malformed, a default session
        rooted in the current working directory is returned.

        Args:
            path: Path to the session JSON file.

        Returns:
            A :class:`Project` instance.
        """
        session_path = path or DEFAULT_SESSION_PATH
        if not session_path.exists():
            return cls()
        try:
            with open(session_path, "r", encoding="utf-8") as fh:
                data: Dict[str, Any] = json.load(fh)
            return cls.from_dict(data)
        except (json.JSONDecodeError, OSError, KeyError, TypeError):
            return cls()

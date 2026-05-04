"""Session persistence for EDK_AI using SQLite.

Stores conversation history, checkpoints, and project metadata.
Enables /history and /resume commands.

Schema:
    sessions -- metadata about each session
    messages -- individual messages within sessions
    checkpoints -- undo points created during sessions

Usage:
    from edkai.core.persistence import PersistenceManager, Session, Message

    pm = PersistenceManager()
    sid = pm.create_session("/path/to/project", provider="openai", model="gpt-4")
    pm.save_message(sid, "user", "Hello!")
    pm.save_message(sid, "assistant", "Hi there!")

    # /history command
    history = pm.get_history(limit=20)
    for entry in history:
        print(f"{entry.started}: {entry.project} ({entry.messages} msgs)")

    # /resume command
    msgs = pm.get_session_messages(sid)
    for msg in msgs:
        print(f"[{msg.role}] {msg.content}")
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Session:
    """A saved session."""

    id: str
    project_path: str
    provider: str
    model: str
    started_at: float
    ended_at: float | None = None
    message_count: int = 0


@dataclass
class Message:
    """A saved message."""

    id: str
    session_id: str
    role: str
    content: str
    timestamp: float
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class HistoryEntry:
    """Entry for /history display."""

    session_id: str
    project: str
    started: str  # Human-readable
    messages: int
    provider: str


class PersistenceManager:
    """Manages persistent storage of sessions and messages.

    Thread-safe through thread-local SQLite connections.  All public
    methods raise ``sqlite3.Error`` on database failures so callers
    can decide how to handle them.

    Attributes:
        db_path: Path to the SQLite database file.
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        project_path TEXT NOT NULL,
        provider TEXT,
        model TEXT,
        started_at REAL NOT NULL,
        ended_at REAL,
        message_count INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT,
        timestamp REAL NOT NULL,
        tool_calls TEXT,  -- JSON serialized
        FOREIGN KEY (session_id) REFERENCES sessions(id)
    );

    CREATE TABLE IF NOT EXISTS checkpoints (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        description TEXT,
        git_commit TEXT,
        timestamp REAL NOT NULL,
        FOREIGN KEY (session_id) REFERENCES sessions(id)
    );

    CREATE INDEX IF NOT EXISTS idx_messages_session
        ON messages(session_id, timestamp);
    CREATE INDEX IF NOT EXISTS idx_sessions_project
        ON sessions(project_path, started_at);
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        """Initialise the persistence layer.

        Args:
            db_path: Path to the SQLite database.  When *None* the
                default ``~/.config/edkai/sessions.db`` is used.
        """
        if db_path is None:
            db_path = Path.home() / ".config" / "edkai" / "sessions.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._local = threading.local()
        self._init_db()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        """Get a thread-local SQLite connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self.db_path))
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self) -> None:
        """Create tables and indexes if they do not exist."""
        conn = self._get_conn()
        conn.executescript(self.SCHEMA)
        conn.commit()

    @staticmethod
    def _format_time(timestamp: float) -> str:
        """Convert a Unix timestamp to a human-readable relative string."""
        delta = time.time() - timestamp
        if delta < 60:
            return f"{int(delta)}s ago"
        elif delta < 3600:
            return f"{int(delta / 60)}m ago"
        elif delta < 86400:
            return f"{int(delta / 3600)}h ago"
        else:
            return f"{int(delta / 86400)}d ago"

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def create_session(
        self, project_path: str, provider: str = "", model: str = ""
    ) -> str:
        """Create a new session and return its ID.

        Args:
            project_path: Absolute path to the project directory.
            provider: LLM provider name (e.g. ``openai``).
            model: Model name (e.g. ``gpt-4``).

        Returns:
            The 12-character session identifier.
        """
        session_id = str(uuid.uuid4())[:12]

        conn = self._get_conn()
        conn.execute(
            "INSERT INTO sessions (id, project_path, provider, model, started_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, project_path, provider, model, time.time()),
        )
        conn.commit()

        return session_id

    def end_session(self, session_id: str) -> None:
        """Mark a session as ended by setting ``ended_at``."""
        conn = self._get_conn()
        conn.execute(
            "UPDATE sessions SET ended_at = ? WHERE id = ?",
            (time.time(), session_id),
        )
        conn.commit()

    def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> None:
        """Persist a single message and increment the session counter.

        Args:
            session_id: Target session ID.
            role: Message role (``user``, ``assistant``, ``system``, …).
            content: Message text content.
            tool_calls: Optional list of tool-call dictionaries (JSON-serialised).
        """
        msg_id = str(uuid.uuid4())[:12]
        tool_calls_json = json.dumps(tool_calls or [])

        conn = self._get_conn()
        conn.execute(
            "INSERT INTO messages (id, session_id, role, content, timestamp, tool_calls) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (msg_id, session_id, role, content, time.time(), tool_calls_json),
        )
        conn.execute(
            "UPDATE sessions SET message_count = message_count + 1 WHERE id = ?",
            (session_id,),
        )
        conn.commit()

    # ------------------------------------------------------------------
    # Checkpoints
    # ------------------------------------------------------------------

    def create_checkpoint(
        self,
        session_id: str,
        description: str = "",
        git_commit: str | None = None,
    ) -> str:
        """Create an undo checkpoint for a session.

        Args:
            session_id: Target session ID.
            description: Human-readable checkpoint description.
            git_commit: Optional Git commit SHA at checkpoint time.

        Returns:
            The 12-character checkpoint ID.
        """
        cp_id = str(uuid.uuid4())[:12]
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO checkpoints (id, session_id, description, git_commit, timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            (cp_id, session_id, description, git_commit, time.time()),
        )
        conn.commit()
        return cp_id

    def get_checkpoints(self, session_id: str) -> list[dict[str, Any]]:
        """Return all checkpoints for a session, oldest first."""
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT id, description, git_commit, timestamp "
            "FROM checkpoints WHERE session_id = ? ORDER BY timestamp",
            (session_id,),
        )
        return [
            {
                "id": row["id"],
                "description": row["description"] or "",
                "git_commit": row["git_commit"] or "",
                "time": self._format_time(row["timestamp"]),
            }
            for row in cursor.fetchall()
        ]

    # ------------------------------------------------------------------
    # History (supports /history command)
    # ------------------------------------------------------------------

    def get_history(self, limit: int = 20) -> list[HistoryEntry]:
        """Retrieve recent sessions for the ``/history`` command.

        Args:
            limit: Maximum number of sessions to return.

        Returns:
            List of :class:`HistoryEntry` objects, most-recent first.
        """
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT id, project_path, started_at, message_count, provider "
            "FROM sessions ORDER BY started_at DESC LIMIT ?",
            (limit,),
        )

        entries: list[HistoryEntry] = []
        for row in cursor.fetchall():
            project = row["project_path"]
            if len(project) > 50:
                project = "..." + project[-47:]

            entries.append(
                HistoryEntry(
                    session_id=row["id"],
                    project=project,
                    started=self._format_time(row["started_at"]),
                    messages=row["message_count"],
                    provider=row["provider"] or "auto",
                )
            )

        return entries

    def get_session_messages(self, session_id: str) -> list[Message]:
        """Fetch all messages for a session (used by ``/resume``).

        Args:
            session_id: Session to reconstruct.

        Returns:
            Ordered list of :class:`Message` objects.
        """
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT id, session_id, role, content, timestamp, tool_calls "
            "FROM messages WHERE session_id = ? ORDER BY timestamp",
            (session_id,),
        )

        messages: list[Message] = []
        for row in cursor.fetchall():
            messages.append(
                Message(
                    id=row["id"],
                    session_id=row["session_id"],
                    role=row["role"],
                    content=row["content"] or "",
                    timestamp=row["timestamp"],
                    tool_calls=json.loads(row["tool_calls"] or "[]"),
                )
            )

        return messages

    def get_session(self, session_id: str) -> Session | None:
        """Fetch a single session by ID.

        Returns:
            The :class:`Session` object, or *None* if not found.
        """
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT id, project_path, provider, model, started_at, "
            "ended_at, message_count FROM sessions WHERE id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return Session(
            id=row["id"],
            project_path=row["project_path"],
            provider=row["provider"] or "",
            model=row["model"] or "",
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            message_count=row["message_count"],
        )

    def search_history(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search message content with a LIKE query.

        Args:
            query: Search term.
            limit: Maximum number of results.

        Returns:
            List of result dictionaries with session context.
        """
        conn = self._get_conn()
        pattern = f"%{query}%"
        cursor = conn.execute(
            "SELECT m.id, m.role, m.content, m.timestamp, "
            "s.project_path, s.id AS session_id "
            "FROM messages m JOIN sessions s ON m.session_id = s.id "
            "WHERE m.content LIKE ? ORDER BY m.timestamp DESC LIMIT ?",
            (pattern, limit),
        )

        results: list[dict[str, Any]] = []
        for row in cursor.fetchall():
            results.append(
                {
                    "session_id": row["session_id"],
                    "role": row["role"],
                    "content": (row["content"] or "")[:200],
                    "time": self._format_time(row["timestamp"]),
                    "project": row["project_path"],
                }
            )

        return results

    # ------------------------------------------------------------------
    # Maintenance / introspection
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Return aggregate persistence statistics.

        Keys: ``total_sessions``, ``total_messages``, ``total_hours``,
        ``db_size_mb``.
        """
        conn = self._get_conn()

        sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        messages = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        total_time = conn.execute(
            "SELECT COALESCE(SUM(ended_at - started_at), 0) "
            "FROM sessions WHERE ended_at IS NOT NULL"
        ).fetchone()[0]

        return {
            "total_sessions": sessions,
            "total_messages": messages,
            "total_hours": round(total_time / 3600, 1),
            "db_size_kb": round(self.db_path.stat().st_size / 1024, 1)
            if self.db_path.exists()
            else 0,
            "db_size_mb": round(self.db_path.stat().st_size / 1024 / 1024, 1)
            if self.db_path.exists()
            else 0,
        }

    def cleanup_old_sessions(self, days: int = 30) -> int:
        """Delete sessions (and their messages/checkpoints) older than *days*.

        Args:
            days: Age threshold in days.

        Returns:
            Number of sessions removed.
        """
        cutoff = time.time() - (days * 86400)
        conn = self._get_conn()

        cursor = conn.execute(
            "SELECT id FROM sessions WHERE started_at < ?", (cutoff,)
        )
        old_ids = [row[0] for row in cursor.fetchall()]

        for sid in old_ids:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (sid,))
            conn.execute("DELETE FROM checkpoints WHERE session_id = ?", (sid,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (sid,))

        conn.commit()
        if old_ids:
            conn.execute("VACUUM")

        return len(old_ids)

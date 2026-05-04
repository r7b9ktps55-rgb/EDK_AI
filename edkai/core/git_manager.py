"""Git integration module for Terminal Studio.

Wraps common git operations (status, diff, blame, log, stage, commit, …)
in an async, non-blocking API using ``asyncio.create_subprocess_exec``.
If git is not installed or the path is not a repository, every method
gracefully degrades and returns empty / default values.
"""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BlameInfo:
    """Information about a single line from ``git blame``."""

    author: str
    """Author name."""

    email: str
    """Author e-mail address."""

    date: str
    """Commit date (ISO-8601-ish string)."""

    commit: str
    """Full commit SHA."""

    message: str
    """First line of the commit message."""


@dataclass(frozen=True)
class CommitInfo:
    """A single commit entry from ``git log``."""

    sha: str
    """Commit SHA (short or full depending on the caller)."""

    author: str
    """Author name."""

    email: str
    """Author e-mail."""

    date: str
    """Commit date string."""

    message: str
    """First line of the commit message."""


@dataclass(frozen=True)
class GitStatus:
    """Parsed output of ``git status --short``."""

    modified: List[str]
    """Files that are modified but not staged."""

    untracked: List[str]
    """Files that are untracked."""

    staged: List[str]
    """Files that are staged for the next commit."""

    branch: str
    """Current branch name."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _which_git() -> Optional[str]:
    """Return the path to the ``git`` executable, or ``None``."""
    return shutil.which("git")


async def _git_cmd(
    cwd: str,
    *args: str,
    env: Dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """Run a git sub-command and return ``(returncode, stdout, stderr)``.

    Args:
        cwd: Working directory for the subprocess.
        args: Arguments passed to ``git`` after the executable name.
        env: Optional extra environment variables.

    Returns:
        ``(returncode, stdout, stderr)``.
    """
    git = _which_git()
    if git is None:
        return (1, "", "git not found")
    proc = await asyncio.create_subprocess_exec(
        git,
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout, stderr = await proc.communicate()
    return (
        proc.returncode or 0,
        stdout.decode(errors="replace"),
        stderr.decode(errors="replace"),
    )


# ---------------------------------------------------------------------------
# GitManager
# ---------------------------------------------------------------------------


class GitManager:
    """Git operations and status tracking.

    Every method is async and non-blocking.  If git is unavailable or the
    path is not inside a git repository, methods return sensible defaults
    (empty strings / empty lists).
    """

    # ------------------------------------------------------------------
    # Repository detection
    # ------------------------------------------------------------------

    @staticmethod
    def is_git_repo(path: str) -> bool:
        """Return ``True`` if *path* is inside a git repository.

        Args:
            path: Any file or directory path.
        """
        if _which_git() is None:
            return False
        try:
            dot_git = Path(path).resolve()
            while dot_git != dot_git.parent:
                if (dot_git / ".git").exists():
                    return True
                dot_git = dot_git.parent
            return False
        except (OSError, RuntimeError):
            return False

    @staticmethod
    async def get_branch(path: str) -> str:
        """Return the current branch name.

        Args:
            path: Path inside the repository.

        Returns:
            Branch name, or ``"main"`` if unavailable.
        """
        if not GitManager.is_git_repo(path):
            return "main"
        rc, out, _ = await _git_cmd(path, "rev-parse", "--abbrev-ref", "HEAD")
        if rc == 0:
            return out.strip() or "main"
        return "main"

    @staticmethod
    async def has_uncommitted_changes(path: str) -> bool:
        """Return ``True`` if the working tree has uncommitted modifications.

        Args:
            path: Path inside the repository.
        """
        if not GitManager.is_git_repo(path):
            return False
        rc, out, _ = await _git_cmd(path, "status", "--porcelain")
        return rc == 0 and bool(out.strip())

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @staticmethod
    async def status(path: str) -> GitStatus:
        """Parse ``git status --short`` and return structured status.

        Args:
            path: Path inside the repository.

        Returns:
            A :class:`GitStatus` instance.
        """
        default = GitStatus(modified=[], untracked=[], staged=[], branch="main")
        if not GitManager.is_git_repo(path):
            return default

        branch = await GitManager.get_branch(path)
        rc, out, _ = await _git_cmd(path, "status", "--short")
        if rc != 0:
            return default._replace(branch=branch)

        modified: List[str] = []
        untracked: List[str] = []
        staged: List[str] = []

        for line in out.splitlines():
            if len(line) < 3:
                continue
            xy = line[:2]
            file_path = line[3:].strip()
            # Staging area in first column
            if xy[0] in "MADRC":
                staged.append(file_path)
            # Working tree in second column
            if xy[1] in "MADRC":
                modified.append(file_path)
            if xy == "??":
                untracked.append(file_path)

        return GitStatus(
            modified=modified,
            untracked=untracked,
            staged=staged,
            branch=branch,
        )

    # ------------------------------------------------------------------
    # Diff
    # ------------------------------------------------------------------

    @staticmethod
    async def diff(file_path: str) -> str:
        """Return a unified diff for *file_path*.

        Args:
            file_path: Absolute path to the file.

        Returns:
            Unified diff text (may be empty if no changes).
        """
        if not GitManager.is_git_repo(file_path):
            return ""
        rc, out, _ = await _git_cmd(
            str(Path(file_path).parent),
            "diff",
            "--no-color",
            "--",
            str(Path(file_path).name),
        )
        if rc == 0:
            return out
        return ""

    # ------------------------------------------------------------------
    # Blame
    # ------------------------------------------------------------------

    @staticmethod
    async def blame(file_path: str, line: int) -> BlameInfo | None:
        """Run ``git blame`` for a single line.

        Args:
            file_path: Absolute path to the file.
            line: 1-based line number.

        Returns:
            A :class:`BlameInfo` instance, or ``None`` if unavailable.
        """
        if not GitManager.is_git_repo(file_path):
            return None
        parent = str(Path(file_path).parent)
        name = Path(file_path).name
        rc, out, _ = await _git_cmd(
            parent,
            "blame",
            "-L",
            f"{line},{line}",
            "--porcelain",
            "--",
            name,
        )
        if rc != 0 or not out:
            return None

        sha = ""
        author = ""
        email = ""
        date = ""
        message = ""
        for raw in out.splitlines():
            if raw.startswith("author "):
                author = raw[7:]
            elif raw.startswith("author-mail "):
                email = raw[12:].strip("<>")
            elif raw.startswith("author-time "):
                ts = raw[11:].strip()
                date = ts
            elif raw.startswith("summary "):
                message = raw[8:]
            elif not sha and raw:
                # First token is the SHA
                sha = raw.split()[0]

        return BlameInfo(
            author=author or "Unknown",
            email=email or "",
            date=date,
            commit=sha,
            message=message,
        )

    # ------------------------------------------------------------------
    # Log
    # ------------------------------------------------------------------

    @staticmethod
    async def log(
        file_path: Optional[str] = None,
        max_count: int = 20,
    ) -> List[CommitInfo]:
        """Return recent commits.

        Args:
            file_path: Restrict log to this file, or ``None`` for the whole repo.
            max_count: Maximum commits to return.

        Returns:
            A list of :class:`CommitInfo` from newest to oldest.
        """
        if file_path and not GitManager.is_git_repo(file_path):
            return []
        if not file_path:
            # Assume caller passes a directory or we just don't know
            return []

        parent = str(Path(file_path).parent)
        args = [
            "log",
            f"--max-count={max_count}",
            "--pretty=format:%H%x00%an%x00%ae%x00%ad%x00%s",
            "--date=iso",
            "--",
            str(Path(file_path).name),
        ]
        rc, out, _ = await _git_cmd(parent, *args)
        if rc != 0 or not out:
            return []

        commits: List[CommitInfo] = []
        for entry in out.split("\n"):
            if not entry:
                continue
            parts = entry.split("\x00")
            if len(parts) < 5:
                continue
            commits.append(
                CommitInfo(
                    sha=parts[0][:8],
                    author=parts[1],
                    email=parts[2],
                    date=parts[3],
                    message=parts[4],
                )
            )
        return commits

    # ------------------------------------------------------------------
    # Mutable operations
    # ------------------------------------------------------------------

    @staticmethod
    async def stage(file_path: str) -> bool:
        """Stage *file_path* for the next commit.

        Args:
            file_path: Absolute path to the file.

        Returns:
            ``True`` on success.
        """
        if not GitManager.is_git_repo(file_path):
            return False
        parent = str(Path(file_path).parent)
        name = Path(file_path).name
        rc, _, _ = await _git_cmd(parent, "add", "--", name)
        return rc == 0

    @staticmethod
    async def unstage(file_path: str) -> bool:
        """Unstage *file_path*.

        Args:
            file_path: Absolute path to the file.

        Returns:
            ``True`` on success.
        """
        if not GitManager.is_git_repo(file_path):
            return False
        parent = str(Path(file_path).parent)
        name = Path(file_path).name
        rc, _, _ = await _git_cmd(parent, "reset", "HEAD", "--", name)
        return rc == 0

    @staticmethod
    async def commit(message: str, path: str = ".") -> bool:
        """Create a commit with the given message.

        Args:
            message: Commit message.
            path: Working directory (defaults to current).

        Returns:
            ``True`` on success.
        """
        if not GitManager.is_git_repo(path):
            return False
        rc, _, _ = await _git_cmd(path, "commit", "-m", message)
        return rc == 0

    # ------------------------------------------------------------------
    # Push / pull helpers (fire-and-forget style)
    # ------------------------------------------------------------------

    @staticmethod
    async def pull(path: str) -> tuple[bool, str]:
        """Run ``git pull``.

        Args:
            path: Path inside the repository.

        Returns:
            ``(success, stdout_or_stderr)``.
        """
        if not GitManager.is_git_repo(path):
            return (False, "not a git repo")
        rc, out, err = await _git_cmd(path, "pull")
        return (rc == 0, out if rc == 0 else err)

    @staticmethod
    async def push(path: str) -> tuple[bool, str]:
        """Run ``git push``.

        Args:
            path: Path inside the repository.

        Returns:
            ``(success, stdout_or_stderr)``.
        """
        if not GitManager.is_git_repo(path):
            return (False, "not a git repo")
        rc, out, err = await _git_cmd(path, "push")
        return (rc == 0, out if rc == 0 else err)

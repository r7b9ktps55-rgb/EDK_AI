"""Fuzzy file and content search engine for Terminal Studio.

Uses ``fd`` / ``find`` for filename discovery and ``rg`` (ripgrep) for
grep-style content search, falling back to pure-Python implementations when
the external tools are not installed.
"""

from __future__ import annotations

import asyncio
import fnmatch
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SearchResult:
    """Result from a filename fuzzy search."""

    path: str
    """Absolute path of the matched file."""

    score: int
    """Higher is better (exact hits score highest)."""

    match_positions: tuple[int, ...]
    """Indices of characters in the filename that matched the query."""


@dataclass(frozen=True)
class ContentResult:
    """Result from a content (grep) search."""

    file: str
    """Absolute path to the file containing the match."""

    line: int
    """1-based line number of the primary match."""

    col: int
    """1-based column of the primary match."""

    context_before: tuple[str, ...]
    """Lines preceding the match (oldest first)."""

    context_after: tuple[str, ...]
    """Lines following the match (newest first)."""

    match_line: str
    """The exact line that contains the match."""

    match_text: str
    """The exact text that matched."""

    score: int = 0
    """Search score (higher = better match)."""


# ---------------------------------------------------------------------------
# Fuzzy scoring
# ---------------------------------------------------------------------------


def _fuzzy_score(query: str, text: str) -> tuple[int, List[int]]:
    """Score how well *query* matches *text* using a simple fuzzy algorithm.

    Returns a tuple ``(score, positions)``.  The score rewards:

    * Exact substring matches (highest).
    * Query characters appearing in order with small gaps.
    * Matches at word boundaries or the start of the string.

    Args:
        query: The search string (lower-cased).
        text: The candidate text (lower-cased).

    Returns:
        A tuple of ``(score, match_positions)``.
    """
    q = query.lower()
    t = text.lower()

    # Exact substring is the best possible match.
    if q in t:
        idx = t.index(q)
        bonus = 1000
        if idx == 0:
            bonus += 500  # start-of-string bonus
        if idx == 0 or t[idx - 1] in " ./_-":
            bonus += 200  # word-boundary bonus
        return (bonus + len(q) * 10, list(range(idx, idx + len(q))))

    # Fuzzy matching -- walk through *t* consuming *q* greedily.
    positions: List[int] = []
    qi = 0
    score = 0
    for ti, ch in enumerate(t):
        if qi < len(q) and ch == q[qi]:
            positions.append(ti)
            # Bonus for consecutive characters.
            if len(positions) > 1 and positions[-1] == positions[-2] + 1:
                score += 15
            # Bonus for word-boundary match.
            if ti == 0 or t[ti - 1] in " ./_-":
                score += 10
            qi += 1
        if qi >= len(q):
            break

    if qi < len(q):
        # Not all characters matched.
        return (0, [])

    # Penalise large gaps.
    for i in range(1, len(positions)):
        gap = positions[i] - positions[i - 1] - 1
        score -= gap * 3

    return (max(score, 1), positions)


# ---------------------------------------------------------------------------
# Helpers -- external-tool detection
# ---------------------------------------------------------------------------


def _which(name: str) -> Optional[str]:
    """Return the path to *name* if it is on ``$PATH``."""
    return shutil.which(name)


# ---------------------------------------------------------------------------
# FuzzySearcher
# ---------------------------------------------------------------------------


class FuzzySearcher:
    """Fast fuzzy file/content search using ripgrep/fd.

    All search methods are fully async and spawn external tools via
    ``asyncio.create_subprocess_exec`` when available.  If the tools are
    missing the class transparently falls back to Python-only scanning.
    """

    # ------------------------------------------------------------------
    # File name search
    # ------------------------------------------------------------------

    async def search_files(
        self,
        query: str,
        root: str,
        max_results: int = 50,
    ) -> List[SearchResult]:
        """Fuzzy-search filenames under *root*.

        Args:
            query: The user-typed search string.
            root: Directory to search recursively.
            max_results: Maximum number of results to return.

        Returns:
            A list of :class:`SearchResult` sorted by descending score.
        """
        if not query:
            return []

        candidates = await self._list_files(root)
        scored: List[tuple[int, list[int], str]] = []
        for path in candidates:
            name = Path(path).name
            score, positions = _fuzzy_score(query, name)
            if score > 0:
                scored.append((score, positions, path))

        scored.sort(key=lambda x: x[0], reverse=True)
        results: List[SearchResult] = []
        for score, positions, path in scored[:max_results]:
            results.append(
                SearchResult(
                    path=path,
                    score=score,
                    match_positions=tuple(positions),
                )
            )
        return results

    async def _list_files(self, root: str) -> List[str]:
        """Return all regular-file paths under *root*, absolute form."""
        if _which("fd") is not None:
            return await self._list_files_fd(root)
        if _which("find") is not None:
            return await self._list_files_find(root)
        return await self._list_files_python(root)

    async def _list_files_fd(self, root: str) -> List[str]:
        """Use ``fd . --type f --absolute-path`` to enumerate files."""
        proc = await asyncio.create_subprocess_exec(
            "fd",
            ".",
            "--type",
            "f",
            "--absolute-path",
            cwd=root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return [line for line in stdout.decode().splitlines() if line]

    async def _list_files_find(self, root: str) -> List[str]:
        """Use POSIX ``find`` to enumerate files."""
        proc = await asyncio.create_subprocess_exec(
            "find",
            root,
            "-type",
            "f",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return [line for line in stdout.decode().splitlines() if line]

    async def _list_files_python(self, root: str) -> List[str]:
        """Pure-Python fallback to walk the directory tree."""
        paths: List[str] = []
        for dirpath, _dirnames, filenames in os.walk(root):
            # Skip hidden directories (e.g. .git, __pycache__)
            if any(part.startswith(".") for part in Path(dirpath).parts):
                continue
            for name in filenames:
                if name.startswith("."):
                    continue
                paths.append(str(Path(dirpath) / name))
        return paths

    # ------------------------------------------------------------------
    # Content search
    # ------------------------------------------------------------------

    async def search_content(
        self,
        query: str,
        root: str,
        max_results: int = 50,
    ) -> List[ContentResult]:
        """Search for *query* inside file contents.

        Uses ``rg`` when available; otherwise falls back to a Python grep.

        Args:
            query: Text to search for.
            root: Directory to search.
            max_results: Maximum results to return.

        Returns:
            A list of :class:`ContentResult` sorted by descending score.
        """
        if not query:
            return []

        if _which("rg") is not None:
            raw = await self._rg_content(query, root, max_results)
        else:
            raw = await self._python_content(query, root, max_results)

        # Score the results -- exact matches in the line get a boost.
        scored: List[tuple[int, ContentResult]] = []
        for result in raw:
            line_lower = result.match_line.lower()
            q_lower = query.lower()
            if q_lower in line_lower:
                score = 500 + len(q_lower) * 10
                if line_lower.startswith(q_lower):
                    score += 200
            else:
                score = 100
            scored.append((score, result))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:max_results]]

    async def grep_pattern(
        self,
        pattern: str,
        root: str,
        language: Optional[str] = None,
    ) -> List[ContentResult]:
        """Regex search for *pattern* inside file contents.

        Args:
            pattern: A regular-expression string.
            root: Directory to search.
            language: Optional language filter (e.g. ``"py"`` -> ``--type py``).

        Returns:
            A list of :class:`ContentResult`.
        """
        if not pattern:
            return []

        if _which("rg") is not None:
            return await self._rg_pattern(pattern, root, language)
        return await self._python_pattern(pattern, root, language)

    # ------------------------------------------------------------------
    # ripgrep implementations
    # ------------------------------------------------------------------

    async def _rg_content(
        self,
        query: str,
        root: str,
        max_results: int,
    ) -> List[ContentResult]:
        """Run ``rg --no-heading -n -C2`` for literal content search."""
        # rg treats positional args as regex, so escape special chars.
        safe = query.replace("\\", "\\\\").replace(".", "\\.").replace("*", "\\*")
        safe = safe.replace("+", "\\+").replace("?", "\\?").replace("(", "\\(")
        safe = safe.replace(")", "\\)").replace("[", "\\[").replace("]", "\\]")
        safe = safe.replace("{", "\\{").replace("}", "\\}").replace("^", "\\^")
        safe = safe.replace("$", "\\$").replace("|", "\\|")

        cmd = [
            "rg",
            "--no-heading",
            "-n",
            "-C2",
            "-F",
            safe,
            root,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return self._parse_rg_output(stdout.decode(), max_results)

    async def _rg_pattern(
        self,
        pattern: str,
        root: str,
        language: Optional[str],
    ) -> List[ContentResult]:
        """Run ``rg --no-heading -n -C2`` for regex search."""
        cmd = ["rg", "--no-heading", "-n", "-C2"]
        if language:
            cmd.extend(["--type", language])
        cmd.extend([pattern, root])
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return self._parse_rg_output(stdout.decode(), 1000)

    def _parse_rg_output(
        self,
        text: str,
        max_results: int,
    ) -> List[ContentResult]:
        """Parse ``rg --no-heading -n -C2`` output into :class:`ContentResult`."""
        results: List[ContentResult] = []
        current_file: Optional[str] = None
        current_line: int = 0
        match_text: str = ""
        match_line: str = ""
        before: List[str] = []
        after: List[str] = []

        def _flush() -> None:
            if current_file is None or not match_line:
                return
            real_after = after.copy()
            results.append(
                ContentResult(
                    file=current_file,
                    line=current_line,
                    col=1,
                    context_before=tuple(before[-2:]),
                    context_after=tuple(real_after[:2]),
                    match_line=match_line,
                    match_text=match_text or match_line,
                )
            )

        for raw_line in text.splitlines():
            if not raw_line:
                continue
            if raw_line.startswith("--"):
                _flush()
                before.clear()
                after.clear()
                match_line = ""
                match_text = ""
                continue

            parts = raw_line.split(":", 2)
            if len(parts) < 3:
                continue

            file_path, line_str, content = parts
            try:
                line_no = int(line_str)
            except ValueError:
                continue

            if current_file != file_path or line_no != current_line + 1:
                # New match group
                _flush()
                before.clear()
                after.clear()
                match_line = content
                match_text = content
                current_file = file_path
                current_line = line_no
            else:
                after.append(content)

        _flush()
        return results[:max_results]

    # ------------------------------------------------------------------
    # Pure-Python fallbacks
    # ------------------------------------------------------------------

    async def _python_content(
        self,
        query: str,
        root: str,
        max_results: int,
    ) -> List[ContentResult]:
        """Search file contents using Python only."""
        q_lower = query.lower()
        results: List[ContentResult] = []
        for dirpath, _dirnames, filenames in os.walk(root):
            if any(part.startswith(".") for part in Path(dirpath).parts):
                continue
            for name in filenames:
                if name.startswith("."):
                    continue
                path = Path(dirpath) / name
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except (OSError, UnicodeDecodeError):
                    continue
                lines = text.splitlines()
                for i, line in enumerate(lines, start=1):
                    if q_lower in line.lower():
                        before = tuple(lines[max(0, i - 3) : i - 1])
                        after = tuple(lines[i : i + 2])
                        col = line.lower().find(q_lower) + 1
                        results.append(
                            ContentResult(
                                file=str(path),
                                line=i,
                                col=col,
                                context_before=before,
                                context_after=after,
                                match_line=line,
                                match_text=query,
                            )
                        )
                        if len(results) >= max_results:
                            return results
        return results

    async def _python_pattern(
        self,
        pattern: str,
        root: str,
        language: Optional[str],
    ) -> List[ContentResult]:
        """Regex search file contents using Python only."""
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
        except re.error:
            return []

        # Language -> extension filter
        lang_exts: Dict[str, List[str]] = {
            "py": [".py"],
            "js": [".js", ".jsx", ".mjs"],
            "ts": [".ts", ".tsx"],
            "go": [".go"],
            "rs": [".rs"],
            "c": [".c", ".h"],
            "cpp": [".cpp", ".cc", ".cxx", ".hpp"],
            "java": [".java"],
            "rb": [".rb"],
        }
        allowed = set(lang_exts.get(language or "", []))

        results: List[ContentResult] = []
        for dirpath, _dirnames, filenames in os.walk(root):
            if any(part.startswith(".") for part in Path(dirpath).parts):
                continue
            for name in filenames:
                if name.startswith("."):
                    continue
                if allowed and Path(name).suffix not in allowed:
                    continue
                path = Path(dirpath) / name
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except (OSError, UnicodeDecodeError):
                    continue
                lines = text.splitlines()
                for i, line in enumerate(lines, start=1):
                    m = compiled.search(line)
                    if m:
                        before = tuple(lines[max(0, i - 3) : i - 1])
                        after = tuple(lines[i : i + 2])
                        results.append(
                            ContentResult(
                                file=str(path),
                                line=i,
                                col=m.start() + 1,
                                context_before=before,
                                context_after=after,
                                match_line=line,
                                match_text=m.group(0),
                            )
                        )
        return results

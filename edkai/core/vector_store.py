"""Vector store for semantic code search (RAG).

Fully local -- no API calls needed. Uses ChromaDB for storage
and sentence-transformers for embeddings.

Example:
    store = VectorStore(project_root)
    await store.initialize()
    await store.index_project()
    results = await store.search("where is authentication handled", k=5)
    # Returns [{"file": "auth.py", "text": "def login()", "score": 0.92}, ...]
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SearchResult:
    """A single search result."""

    file: str
    text: str
    score: float
    line_start: int = 0
    line_end: int = 0


class VectorStore:
    """Semantic code search using ChromaDB.

    Falls back to simple keyword search if ChromaDB is not available.
    All operations that touch the DB are async-friendly (the DB calls
    themselves are synchronous but the public API is ``async`` so callers
    can run them in a thread pool later without changing signatures).
    """

    # File extensions to index
    CODE_EXTENSIONS: set[str] = {
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".go",
        ".rs",
        ".java",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
        ".rb",
        ".php",
        ".swift",
        ".kt",
        ".scala",
        ".r",
        ".m",
        ".sh",
        ".yaml",
        ".yml",
        ".json",
        ".toml",
        ".md",
        ".css",
        ".scss",
        ".html",
        ".xml",
        ".sql",
    }

    # Paths / directory names to ignore
    IGNORE_PATTERNS: list[str] = [
        "__pycache__",
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "dist",
        "build",
        ".pytest_cache",
        ".mypy_cache",
        ".tox",
        ".eggs",
        "*.egg-info",
        "htmlcov",
        ".coverage",
    ]

    # Tuning knobs
    _CHUNK_WINDOW: int = 30        # lines per chunk
    _CHUNK_OVERLAP: int = 5        # lines of overlap between chunks
    _MAX_FILES: int = 500          # cap to keep indexing fast
    _BATCH_SIZE: int = 100         # ChromaDB add batch size
    _MAX_RESULT_LEN: int = 500     # characters of text per result

    def __init__(self, project_root: Path | str) -> None:
        self.root = Path(project_root).resolve()
        self._db_path = self.root / ".edkai" / "vector_db"
        self._client: Any | None = None
        self._collection: Any | None = None
        self._embedding_func: Any | None = None
        self._available = False
        # Delayed imports -- modules are stashed here so we don't need
        # them at class-import time.
        self._chromadb: Any | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _try_import_chromadb(self) -> bool:
        """Attempt to import ChromaDB and default embedding function."""
        try:
            import chromadb
            from chromadb.utils.embedding_functions import (
                DefaultEmbeddingFunction,
            )

            self._chromadb = chromadb
            self._embedding_func = DefaultEmbeddingFunction()
            return True
        except ImportError:
            return False

    async def initialize(self) -> bool:
        """Initialise (or re-open) the persistent vector store.

        Returns ``True`` when the store is ready for queries.
        """
        if not self._try_import_chromadb():
            return False

        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._client = self._chromadb.PersistentClient(
                path=str(self._db_path)
            )
            self._collection = self._client.get_or_create_collection(
                name="code",
                embedding_function=self._embedding_func,
            )
            self._available = True
            return True
        except Exception:
            self._available = False
            return False

    def is_available(self) -> bool:
        """Return whether the vector store is ready to use."""
        return self._available

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _should_ignore(self, path: Path) -> bool:
        """Check if *path* lives inside an ignored directory."""
        # Use path.parts so we catch directory names anywhere in the tree.
        parts = path.parts
        for pattern in self.IGNORE_PATTERNS:
            # Patterns like ``*.egg-info`` are matched against the string rep
            if any(pattern in part for part in parts):
                return True
        return False

    def _chunk_file(self, file_path: Path) -> list[dict[str, Any]]:
        """Split *file_path* into overlapping line windows.

        Each chunk contains:
            - ``text``      -- the source lines
            - ``file``      -- repo-relative path
            - ``line_start``-- 1-based start line
            - ``line_end``  -- 1-based end line (inclusive)
            - ``id``        -- deterministic identifier for upserts
        """
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            return []

        lines = content.splitlines()
        if not lines:
            return []

        rel_path = str(file_path.relative_to(self.root))
        chunks: list[dict[str, Any]] = []
        step = self._CHUNK_WINDOW - self._CHUNK_OVERLAP

        i = 0
        while i < len(lines):
            end = min(i + self._CHUNK_WINDOW, len(lines))
            chunk_text = "\n".join(lines[i:end])

            if chunk_text.strip():
                chunks.append(
                    {
                        "text": chunk_text,
                        "file": rel_path,
                        "line_start": i + 1,
                        "line_end": end,
                        "id": f"{rel_path}:{i}",
                    }
                )

            i += step
            # Prevent infinite loop when window_size <= overlap
            if step <= 0:
                break

        return chunks

    def _collect_source_files(self) -> list[Path]:
        """Return up to :pyattr:`_MAX_FILES` source files to index."""
        files: list[Path] = []
        for ext in self.CODE_EXTENSIONS:
            for f in self.root.rglob(f"*{ext}"):
                if not self._should_ignore(f):
                    files.append(f)
                    if len(files) >= self._MAX_FILES:
                        return files
        return files

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    async def index_project(self) -> dict[str, int]:
        """Index every source file under the project root.

        Returns a dict with ``indexed`` and ``failed`` counts.
        """
        if not self._available or self._collection is None:
            return {"indexed": 0, "failed": 0, "error": "ChromaDB not available"}

        files = self._collect_source_files()

        # Flatten into chunks
        all_chunks: list[dict[str, Any]] = []
        for f in files:
            all_chunks.extend(self._chunk_file(f))

        indexed = 0
        failed = 0

        for i in range(0, len(all_chunks), self._BATCH_SIZE):
            batch = all_chunks[i : i + self._BATCH_SIZE]
            try:
                self._collection.add(
                    ids=[c["id"] for c in batch],
                    documents=[c["text"] for c in batch],
                    metadatas=[
                        {
                            "file": c["file"],
                            "line_start": c["line_start"],
                            "line_end": c["line_end"],
                        }
                        for c in batch
                    ],
                )
                indexed += len(batch)
            except Exception:
                failed += len(batch)

        return {"indexed": indexed, "failed": failed}

    async def update_file(self, file_path: Path | str) -> None:
        """Re-index a single file after it has been edited.

        Old chunks for that file are removed before the new ones are added.
        """
        if not self._available or self._collection is None:
            return

        path = Path(file_path)
        rel_path = str(path.relative_to(self.root))

        # Delete previous chunks for this file
        try:
            self._collection.delete(where={"file": rel_path})
        except Exception:
            pass

        # Re-chunk and add
        chunks = self._chunk_file(path)
        if not chunks:
            return

        try:
            self._collection.add(
                ids=[c["id"] for c in chunks],
                documents=[c["text"] for c in chunks],
                metadatas=[
                    {
                        "file": c["file"],
                        "line_start": c["line_start"],
                        "line_end": c["line_end"],
                    }
                    for c in chunks
                ],
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    async def search(self, query: str, k: int = 5) -> list[SearchResult]:
        """Semantic search over the indexed codebase.

        Args:
            query: Natural-language query, e.g. ``"where is auth handled"``.
            k: Maximum number of results to return.

        Returns:
            List of :class:`SearchResult` sorted by relevance (highest first).
        """
        if not self._available or self._collection is None:
            return []

        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=min(k, 20),
            )
        except Exception:
            return []

        output: list[SearchResult] = []
        docs = results.get("documents")
        metas = results.get("metadatas")
        dists = results.get("distances")

        if not docs or not docs[0]:
            return output

        for i, doc in enumerate(docs[0]):
            metadata = metas[0][i] if metas and metas[0] else {}
            distance = dists[0][i] if dists and dists[0] else 0.0

            # ChromaDB returns cosine distance by default with the
            # default embedding function. Map to a 0..1 score.
            score = max(0.0, 1.0 - float(distance))

            output.append(
                SearchResult(
                    file=metadata.get("file", "unknown"),
                    text=doc[: self._MAX_RESULT_LEN],
                    score=round(score, 4),
                    line_start=metadata.get("line_start", 0),
                    line_end=metadata.get("line_end", 0),
                )
            )

        output.sort(key=lambda r: r.score, reverse=True)
        return output

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Return metadata about the vector store."""
        if not self._available or self._collection is None:
            return {"available": False}

        try:
            count = self._collection.count()
            return {
                "available": True,
                "indexed_chunks": count,
                "db_path": str(self._db_path),
            }
        except Exception:
            return {"available": False}


# ---------------------------------------------------------------------------
# Fallback keyword search (no embeddings required)
# ---------------------------------------------------------------------------


class KeywordFallback:
    """Lightweight grep-based fallback when ChromaDB is unavailable."""

    # Same ignore patterns as VectorStore for consistency
    IGNORE_DIRS: set[str] = {
        "__pycache__",
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "dist",
        "build",
        ".pytest_cache",
        ".mypy_cache",
    }

    def __init__(self, project_root: Path | str) -> None:
        self.root = Path(project_root).resolve()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _should_ignore_dir(self, path: Path) -> bool:
        """Check if any component of *path* is an ignored directory."""
        return any(part in self.IGNORE_DIRS for part in path.parts)

    def _grep_fallback(
        self, query: str, k: int
    ) -> list[SearchResult]:
        """Use system ``grep`` to find keyword matches."""
        try:
            proc = subprocess.run(
                ["grep", "-ri", "-n", "-C", "2", query, "."],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

        if proc.returncode != 0 and not proc.stdout:
            return []

        # Parse grep output:  file.c-1-context
        #                     file.c:2:match
        #                     file.c-3-context
        output: list[SearchResult] = []
        file_blocks: dict[str, list[str]] = {}

        for line in proc.stdout.splitlines():
            if line.startswith("--"):
                continue

            # Format: filename:line_num:content   or   filename-line_num:content
            if ":" not in line:
                continue

            file_part, rest = line.split(":", 1)
            # Remove leading "./"
            file_name = file_part.lstrip("./")
            file_path = self.root / file_name
            if self._should_ignore_dir(file_path):
                continue

            content = rest.strip()
            file_blocks.setdefault(file_name, []).append(content)

        # Build results from aggregated blocks
        for file_name, lines in file_blocks.items():
            text_block = "\n".join(lines[-5:])  # keep last 5 matching lines
            output.append(
                SearchResult(
                    file=file_name,
                    text=text_block[:500],
                    score=0.5,
                )
            )
            if len(output) >= k:
                break

        return output

    def _python_fallback(
        self, query: str, k: int
    ) -> list[SearchResult]:
        """Pure-Python fallback when ``grep`` is not available."""
        results: list[SearchResult] = []
        query_lower = query.lower()

        for path in self.root.rglob("*"):
            if not path.is_file():
                continue
            if self._should_ignore_dir(path):
                continue
            if path.stat().st_size > 200_000:  # skip large files
                continue

            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except (OSError, UnicodeDecodeError):
                continue

            if query_lower in content.lower():
                lines = content.splitlines()
                # Find first matching line
                for idx, line in enumerate(lines):
                    if query_lower in line.lower():
                        start = max(0, idx - 1)
                        end = min(len(lines), idx + 3)
                        context = "\n".join(lines[start:end])
                        results.append(
                            SearchResult(
                                file=str(path.relative_to(self.root)),
                                text=context[:500],
                                score=0.5,
                                line_start=idx + 1,
                                line_end=end,
                            )
                        )
                        break  # one result per file

                if len(results) >= k:
                    break

        return results

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search(self, query: str, k: int = 5) -> list[SearchResult]:
        """Keyword search over the codebase.

        Tries ``grep`` first, falls back to a pure-Python scan if ``grep``
        is not installed or times out.
        """
        grep_results = self._grep_fallback(query, k)
        if grep_results:
            return grep_results
        return self._python_fallback(query, k)

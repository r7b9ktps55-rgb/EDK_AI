"""Syntax highlighting utilities for Terminal Studio.

Provides language detection from file extensions and lexer retrieval
for Pygments-based highlighting fallback.
"""

from __future__ import annotations

import os
from typing import Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from pygments.lexers import Lexer


# Mapping of file extensions to language names used by Textual's TextArea
# and Pygments.
_EXTENSION_TO_LANGUAGE: Dict[str, str] = {
    # Python
    ".py": "python",
    ".pyw": "python",
    ".pyi": "python",
    # JavaScript
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    # TypeScript (falls back to javascript for Textual highlighting)
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    # Rust
    ".rs": "rust",
    # Go
    ".go": "go",
    # C / C++
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    # Java
    ".java": "java",
    # HTML
    ".html": "html",
    ".htm": "html",
    ".xhtml": "html",
    # CSS
    ".css": "css",
    ".scss": "css",
    ".sass": "css",
    ".less": "css",
    # JSON
    ".json": "json",
    ".jsonc": "json",
    # YAML
    ".yaml": "yaml",
    ".yml": "yaml",
    # Markdown
    ".md": "markdown",
    ".mdx": "markdown",
    ".mkd": "markdown",
    # Bash / Shell
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".fish": "bash",
    # XML
    ".xml": "xml",
    ".svg": "xml",
    # SQL
    ".sql": "sql",
    # TOML
    ".toml": "toml",
    # Regex
    ".regex": "regex",
}

# Mapping from our language names to Pygments lexer names.
_LANGUAGE_TO_PYGMENTS: Dict[str, str] = {
    "python": "python",
    "javascript": "javascript",
    "typescript": "typescript",
    "rust": "rust",
    "go": "go",
    "c": "c",
    "cpp": "cpp",
    "java": "java",
    "html": "html",
    "css": "css",
    "json": "json",
    "yaml": "yaml",
    "markdown": "markdown",
    "bash": "bash",
    "xml": "xml",
    "sql": "sql",
    "toml": "toml",
    "regex": "regex",
}


def detect_language(file_path: str) -> str:
    """Detect the programming language from a file path.

    Args:
        file_path: Path to the file.

    Returns:
        The language name (e.g., ``"python"``, ``"javascript"``).
        Returns an empty string if the extension is not recognised.
    """
    _, ext = os.path.splitext(file_path.lower())
    return _EXTENSION_TO_LANGUAGE.get(ext, "")


def get_lexer(language: str) -> "Lexer | None":
    """Return a Pygments lexer for the given language name.

    Args:
        language: The language name (e.g., ``"python"``).

    Returns:
        A Pygments ``Lexer`` instance, or ``None`` if the language is
        not supported or Pygments is not available.
    """
    try:
        from pygments.lexers import get_lexer_by_name
    except Exception:  # pragma: no cover
        return None

    pygments_name = _LANGUAGE_TO_PYGMENTS.get(language)
    if pygments_name is None:
        return None

    try:
        return get_lexer_by_name(pygments_name)
    except Exception:
        return None

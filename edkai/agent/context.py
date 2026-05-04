"""Project context builder for the AI agent.

Gathers a concise but informative overview of the project directory including
file tree, key configuration files, and git status.  The result is capped at
*max_chars* so it fits comfortably inside the LLM context window.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


class ProjectContext:
    """Builds project context for the AI agent."""

    def __init__(self, project_root: str | Path) -> None:
        self.root = Path(project_root).resolve()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def build_context(self, max_chars: int = 12000) -> str:
        """Build project summary including structure and key files.

        Parameters
        ----------
        max_chars:
            Hard upper-bound on the length of the returned string.  Content is
            truncated with an ellipsis if it exceeds this limit.
        """
        parts: list[str] = []
        parts.append(f"Project: {self.root.name}")
        parts.append(f"Path: {self.root}")
        parts.append("")

        # File tree (max 150 files)
        tree = self._get_file_tree(max_files=150)
        parts.append("## File Structure")
        parts.append(tree)
        parts.append("")

        # Key config files
        key_files = self._get_key_files()
        if key_files:
            parts.append("## Key Files")
            for name, content in key_files:
                parts.append(f"### {name}")
                parts.append(content[:2000])  # Truncate
                parts.append("")

        # Git status
        git_info = self._get_git_status()
        if git_info:
            parts.append("## Git Status")
            parts.append(git_info)

        result = "\n".join(parts)
        if len(result) > max_chars:
            result = result[:max_chars] + "\n... (truncated)"
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_file_tree(self, max_files: int = 150) -> str:
        """Generate tree-like file listing.

        Directories commonly containing build artefacts or dependencies are
        skipped automatically (``.git``, ``node_modules``, ``__pycache__``,
        virtual-env folders, …).
        """
        lines: list[str] = []
        count = 0

        skip_dirs = {
            ".git",
            "__pycache__",
            "node_modules",
            ".venv",
            "venv",
            "dist",
            "build",
            ".pytest_cache",
            ".mypy_cache",
            ".tox",
        }

        for root, dirs, files in os.walk(self.root):
            # Skip common non-source dirs
            dirs[:] = [d for d in dirs if d not in skip_dirs]

            rel = Path(root).relative_to(self.root)
            level = len(rel.parts) if str(rel) != "." else 0
            indent = "  " * level
            dir_name = Path(root).name
            lines.append(f"{indent}{dir_name}/")

            subindent = "  " * (level + 1)
            for f in sorted(files):
                # Hide hidden files except a few well-known ones
                if f.startswith(".") and f not in {
                    ".gitignore",
                    ".env",
                    ".dockerignore",
                }:
                    continue
                lines.append(f"{subindent}{f}")
                count += 1
                if count >= max_files:
                    lines.append(f"{subindent}... ({max_files}+ files total)")
                    return "\n".join(lines)

        return "\n".join(lines)

    def _get_key_files(self) -> list[tuple[str, str]]:
        """Read key project configuration files.

        Returns a list of *(filename, content)* tuples.  Content is truncated
        to 3000 characters per file.
        """
        key_names = [
            "README.md",
            "pyproject.toml",
            "package.json",
            "requirements.txt",
            "Dockerfile",
            "Makefile",
            "Cargo.toml",
            "go.mod",
        ]
        result: list[tuple[str, str]] = []
        for name in key_names:
            path = self.root / name
            if path.exists():
                try:
                    content = path.read_text(encoding="utf-8", errors="replace")[:3000]
                    result.append((name, content))
                except OSError:
                    pass
        return result

    def _get_git_status(self) -> str:
        """Get git status and the 5 most recent commits.

        Returns an empty string when git is not available or the directory is
        not inside a git repository.
        """
        try:
            result = subprocess.run(
                ["git", "status", "--short"],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=10,
            )
            status = result.stdout.strip()

            result2 = subprocess.run(
                ["git", "log", "--oneline", "-5"],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=10,
            )
            log = result2.stdout.strip()

            parts: list[str] = []
            if status:
                parts.append("Modified files:")
                parts.append(status)
            if log:
                if parts:
                    parts.append("")
                parts.append("Recent commits:")
                parts.append(log)

            if not parts:
                return "Clean working tree"
            return "\n".join(parts)

        except Exception:
            return "Not a git repository"

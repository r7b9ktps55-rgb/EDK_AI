"""Tool implementations for the Terminal Studio Agent.

Provides 10 built-in tools:
- ReadFile: Read file contents with optional offset/limit
- WriteFile: Write content to a file (creates directories)
- EditFile: Surgical string replacement in files
- Shell: Execute shell commands with security guards
- SearchCode: Search code using ripgrep or fallback to Python
- SearchFiles: Find files by glob pattern
- ListDir: List directory contents with type indicators
- GitStatus: Show git status and short diff
- GitCommit: Stage and commit changes
- AskUser: Request input from the user

All tools implement the BaseTool interface and are registered in ToolRegistry.
"""

from __future__ import annotations

import asyncio
import fnmatch
import json
import os
import re
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ToolResult:
    """Result of a tool execution."""

    output: str = ""
    error: str | None = None
    is_error: bool = False

    def __str__(self) -> str:
        if self.is_error and self.error:
            return f"[ERROR] {self.error}"
        return self.output


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class BaseTool(ABC):
    """Abstract base class for all agent tools."""

    name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    parameters: ClassVar[dict[str, Any]] = {}

    # Set by orchestrator for path-security checks
    project_root: Path = Path.cwd()

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the tool and return a ``ToolResult``."""

    def to_prompt(self) -> str:
        """Return a human-readable description for the system prompt."""
        lines = [
            f"### {self.name}",
            self.description,
            "Parameters:",
        ]
        for param_name, param_info in self.parameters.items():
            req = "required" if param_info.get("required") else "optional"
            default = param_info.get("default")
            type_ = param_info.get("type", "string")
            desc = param_info.get("description", "")
            extra = f" (default: {default!r})" if default is not None else ""
            lines.append(f'  - {param_name}: {type_} — {desc} ({req}){extra}')
        return "\n".join(lines)

    # --- path security helpers ---

    def _resolve_path(self, path: str) -> Path:
        """Resolve *path* relative to ``project_root``.

        Raises ``ValueError`` if the resolved path escapes the project.
        """
        target = (self.project_root / path).resolve()
        # On Windows, pathlib does not have ``is_relative_to`` before 3.9,
        # so we normalise to strings for the check.
        try:
            target.relative_to(self.project_root)
        except ValueError as exc:
            raise ValueError(
                f"Path '{path}' resolves outside project root '{self.project_root}'"
            ) from exc
        return target


# ---------------------------------------------------------------------------
# Individual tool implementations
# ---------------------------------------------------------------------------

class ReadFile(BaseTool):
    """Read a file's contents with optional offset / limit."""

    name = "ReadFile"
    description = "Read the contents of a file. Returns content with line numbers."
    parameters = {
        "path": {
            "type": "string",
            "description": "Relative path to the file within the project",
            "required": True,
        },
        "offset": {
            "type": "integer",
            "description": "Starting line number (1-based)",
            "required": False,
            "default": 1,
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of lines to read",
            "required": False,
            "default": 100,
        },
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        path_str: str = kwargs["path"]
        offset: int = int(kwargs.get("offset", 1))
        limit: int = int(kwargs.get("limit", 100))

        try:
            target = self._resolve_path(path_str)
        except ValueError as exc:
            return ToolResult(error=str(exc), is_error=True)

        if not target.exists():
            return ToolResult(error=f"File not found: {path_str}", is_error=True)
        if not target.is_file():
            return ToolResult(error=f"Not a file: {path_str}", is_error=True)

        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return ToolResult(error=f"Cannot read file: {exc}", is_error=True)

        lines = text.splitlines()
        start = max(0, offset - 1)
        end = start + limit
        selected = lines[start:end]

        if not selected:
            return ToolResult(output="(empty file or offset beyond file length)")

        # Build output with line numbers
        width = len(str(start + len(selected)))
        numbered = [f"{start + i + 1:{width}} | {line}" for i, line in enumerate(selected)]

        header = f"--- {path_str} (lines {start + 1}-{start + len(selected)}) ---"
        return ToolResult(output=header + "\n" + "\n".join(numbered))


class WriteFile(BaseTool):
    """Write content to a file, creating parent directories automatically."""

    name = "WriteFile"
    description = "Write content to a file. Creates parent directories if needed."
    parameters = {
        "path": {
            "type": "string",
            "description": "Relative path to the file within the project",
            "required": True,
        },
        "content": {
            "type": "string",
            "description": "Content to write to the file",
            "required": True,
        },
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        path_str: str = kwargs["path"]
        content: str = kwargs["content"]

        try:
            target = self._resolve_path(path_str)
        except ValueError as exc:
            return ToolResult(error=str(exc), is_error=True)

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except OSError as exc:
            return ToolResult(error=f"Cannot write file: {exc}", is_error=True)

        return ToolResult(output=f"Wrote {len(content)} chars to {path_str}")


class EditFile(BaseTool):
    """Surgical edit: replace *exactly one* occurrence of *old_string* with *new_string*."""

    name = "EditFile"
    description = "Replace an exact string in a file. old_string must exist exactly once."
    parameters = {
        "path": {
            "type": "string",
            "description": "Relative path to the file within the project",
            "required": True,
        },
        "old_string": {
            "type": "string",
            "description": "Exact text to replace (must appear exactly once)",
            "required": True,
        },
        "new_string": {
            "type": "string",
            "description": "Replacement text",
            "required": True,
        },
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        path_str: str = kwargs["path"]
        old: str = kwargs["old_string"]
        new: str = kwargs["new_string"]

        try:
            target = self._resolve_path(path_str)
        except ValueError as exc:
            return ToolResult(error=str(exc), is_error=True)

        if not target.exists():
            return ToolResult(error=f"File not found: {path_str}", is_error=True)

        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return ToolResult(error=f"Cannot read file: {exc}", is_error=True)

        count = text.count(old)
        if count == 0:
            return ToolResult(
                error=f"old_string not found in {path_str}", is_error=True
            )
        if count > 1:
            return ToolResult(
                error=(
                    f"old_string appears {count} times in {path_str}; "
                    "it must appear exactly once for a safe replacement"
                ),
                is_error=True,
            )

        new_text = text.replace(old, new, 1)
        try:
            target.write_text(new_text, encoding="utf-8")
        except OSError as exc:
            return ToolResult(error=f"Cannot write file: {exc}", is_error=True)

        return ToolResult(
            output=f"Edited {path_str}: replaced {len(old)} chars with {len(new)} chars"
        )


class Shell(BaseTool):
    """Run a shell command with security guards and timeout."""

    name = "Shell"
    description = "Execute a shell command in the project directory."
    parameters = {
        "command": {
            "type": "string",
            "description": "Shell command to execute",
            "required": True,
        },
        "timeout": {
            "type": "integer",
            "description": "Timeout in seconds",
            "required": False,
            "default": 30,
        },
    }

    # Dangerous patterns that are blocked unconditionally
    BLOCKED_PATTERNS: ClassVar[list[str]] = [
        r"rm\s+-rf\s+/\s*;?\s*$",           # rm -rf /
        r">\s*/dev/sda",                       # overwrite disk
        r"mkfs\.\w+\s+/dev/sda",
        r":\(\)\{\s*:\|:&\s*\};:",           # fork bomb
        r"dd\s+if=.*\s+of=/dev/sda",
        r"chmod\s+-R\s+777\s+/",
    ]

    async def execute(self, **kwargs: Any) -> ToolResult:
        command: str = kwargs["command"]
        timeout: int = int(kwargs.get("timeout", 30))

        # Security check
        for pattern in self.BLOCKED_PATTERNS:
            if re.search(pattern, command):
                return ToolResult(
                    error=f"Command blocked for security: '{command}' matches forbidden pattern",
                    is_error=True,
                )

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.project_root,
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return ToolResult(
                    error=f"Command timed out after {timeout}s", is_error=True
                )

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            output_parts: list[str] = []
            if stdout:
                output_parts.append(f"STDOUT:\n{stdout}")
            if stderr:
                output_parts.append(f"STDERR:\n{stderr}")

            combined = "\n\n".join(output_parts) if output_parts else "(no output)"

            if proc.returncode != 0:
                return ToolResult(
                    output=combined,
                    error=f"Exit code {proc.returncode}",
                    is_error=True,
                )
            return ToolResult(output=combined)

        except Exception as exc:
            return ToolResult(error=f"Failed to run command: {exc}", is_error=True)


class SearchCode(BaseTool):
    """Search code for a pattern using ripgrep when available, Python fallback otherwise."""

    name = "SearchCode"
    description = "Search for a regex pattern in the codebase. Uses ripgrep if available."
    parameters = {
        "pattern": {
            "type": "string",
            "description": "Regex pattern to search for",
            "required": True,
        },
        "path": {
            "type": "string",
            "description": "Directory to search in (relative to project root)",
            "required": False,
            "default": ".",
        },
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        pattern: str = kwargs["pattern"]
        path_str: str = kwargs.get("path", ".")

        try:
            search_root = self._resolve_path(path_str)
        except ValueError as exc:
            return ToolResult(error=str(exc), is_error=True)

        if not search_root.exists():
            return ToolResult(error=f"Path not found: {path_str}", is_error=True)

        # Prefer ripgrep
        if shutil.which("rg"):
            return await self._search_ripgrep(pattern, search_root)
        return await self._search_python(pattern, search_root)

    async def _search_ripgrep(self, pattern: str, search_root: Path) -> ToolResult:
        cmd = [
            "rg",
            "--json",
            "--line-number",
            "--max-count=50",
            "--max-columns=300",
            "--no-heading",
            "-g", "!node_modules",
            "-g", "!__pycache__",
            "-g", "!.git",
            "-g", "!.venv",
            "-g", "!venv",
            "-g", "!dist",
            "-g", "!build",
            "-g", "!*.min.js",
            "-g", "!*.min.css",
            "--", pattern, str(search_root),
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
            output = stdout.decode("utf-8", errors="replace").strip()
            if not output:
                return ToolResult(output="No matches found.")

            # Parse rg JSON output into human-readable lines
            lines: list[str] = []
            for raw in output.splitlines():
                try:
                    entry = json.loads(raw)
                    if entry.get("type") == "match":
                        data = entry["data"]
                        file_path = data["path"]["text"]
                        line_no = data["line_number"]
                        subline = data["lines"]["text"].rstrip("\n")
                        try:
                            rel = Path(file_path).relative_to(self.project_root)
                        except ValueError:
                            rel = file_path
                        lines.append(f"{rel}:{line_no}: {subline}")
                except (json.JSONDecodeError, KeyError):
                    continue
            if lines:
                return ToolResult(output="\n".join(lines[:50]))
            return ToolResult(output="No matches found.")

        except asyncio.TimeoutError:
            return ToolResult(error="Search timed out", is_error=True)
        except Exception as exc:
            return ToolResult(error=f"Search failed: {exc}", is_error=True)

    async def _search_python(self, pattern: str, search_root: Path) -> ToolResult:
        compiled = re.compile(pattern)
        matches: list[str] = []
        max_matches = 50

        def _scan() -> list[str]:
            results: list[str] = []
            skip_dirs = {
                ".git", "__pycache__", "node_modules", ".venv", "venv",
                "dist", "build", ".pytest_cache", ".mypy_cache",
            }
            for root, dirs, files in os.walk(search_root):
                dirs[:] = [d for d in dirs if d not in skip_dirs]
                for filename in files:
                    if filename.endswith((".min.js", ".min.css")):
                        continue
                    fpath = Path(root) / filename
                    try:
                        text = fpath.read_text(encoding="utf-8", errors="replace")
                        for lineno, line in enumerate(text.splitlines(), 1):
                            if compiled.search(line):
                                try:
                                    rel = fpath.relative_to(self.project_root)
                                except ValueError:
                                    rel = fpath
                                results.append(f"{rel}:{lineno}: {line.rstrip()}")
                                if len(results) >= max_matches:
                                    return results
                    except OSError:
                        continue
            return results

        matches = await asyncio.to_thread(_scan)
        if matches:
            return ToolResult(output="\n".join(matches))
        return ToolResult(output="No matches found.")


class SearchFiles(BaseTool):
    """Find files by glob pattern."""

    name = "SearchFiles"
    description = "Find files matching a glob pattern (e.g. '*.py', '**/*.js')."
    parameters = {
        "pattern": {
            "type": "string",
            "description": "Glob pattern to match filenames against",
            "required": True,
        },
        "path": {
            "type": "string",
            "description": "Directory to search in (relative to project root)",
            "required": False,
            "default": ".",
        },
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        pattern: str = kwargs["pattern"]
        path_str: str = kwargs.get("path", ".")

        try:
            search_root = self._resolve_path(path_str)
        except ValueError as exc:
            return ToolResult(error=str(exc), is_error=True)

        if not search_root.exists():
            return ToolResult(error=f"Path not found: {path_str}", is_error=True)

        results: list[str] = []
        max_results = 100
        skip_dirs = {
            ".git", "__pycache__", "node_modules", ".venv", "venv",
            "dist", "build", ".pytest_cache", ".mypy_cache",
        }

        for root, dirs, files in os.walk(search_root):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for filename in files:
                if fnmatch.fnmatch(filename, pattern):
                    full = Path(root) / filename
                    try:
                        rel = full.relative_to(self.project_root)
                    except ValueError:
                        rel = full
                    results.append(str(rel))
                    if len(results) >= max_results:
                        break
            if len(results) >= max_results:
                break

        if results:
            return ToolResult(output="\n".join(results))
        return ToolResult(output="No files found.")


class ListDir(BaseTool):
    """List directory contents with ``/`` for directories and ``*`` for executables."""

    name = "ListDir"
    description = "List files in a directory. Directories end with '/', executables with '*'."
    parameters = {
        "path": {
            "type": "string",
            "description": "Directory path (relative to project root)",
            "required": False,
            "default": ".",
        },
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        path_str: str = kwargs.get("path", ".")

        try:
            target = self._resolve_path(path_str)
        except ValueError as exc:
            return ToolResult(error=str(exc), is_error=True)

        if not target.exists():
            return ToolResult(error=f"Directory not found: {path_str}", is_error=True)
        if not target.is_dir():
            return ToolResult(error=f"Not a directory: {path_str}", is_error=True)

        entries: list[str] = []
        try:
            items = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError as exc:
            return ToolResult(error=f"Cannot list directory: {exc}", is_error=True)

        for item in items:
            name = item.name
            if item.is_dir():
                name += "/"
            elif item.is_file() and os.access(item, os.X_OK):
                name += "*"
            entries.append(name)

        header = f"--- {path_str}/ ---"
        return ToolResult(output=header + "\n" + "\n".join(entries))


class GitStatus(BaseTool):
    """Show git status and a short diff."""

    name = "GitStatus"
    description = "Show git status and a short diff of modified files."
    parameters: ClassVar[dict[str, Any]] = {}

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            # git status --short
            proc1 = await asyncio.create_subprocess_exec(
                "git", "status", "--short",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.project_root,
            )
            stdout1, stderr1 = await asyncio.wait_for(proc1.communicate(), timeout=10)

            status_out = stdout1.decode("utf-8", errors="replace").strip()
            status_err = stderr1.decode("utf-8", errors="replace").strip()

            if status_err and "not a git repository" in status_err.lower():
                return ToolResult(output="Not a git repository.")

            parts: list[str] = []
            if status_out:
                parts.append("Status:")
                parts.append(status_out)
            else:
                parts.append("Status: clean")

            # Short diff (max 200 lines)
            proc2 = await asyncio.create_subprocess_exec(
                "git", "diff", "--stat",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.project_root,
            )
            stdout2, _ = await asyncio.wait_for(proc2.communicate(), timeout=10)
            diff_stat = stdout2.decode("utf-8", errors="replace").strip()
            if diff_stat:
                parts.append("")
                parts.append("Diff stat:")
                parts.append(diff_stat)

            return ToolResult(output="\n".join(parts))

        except asyncio.TimeoutError:
            return ToolResult(error="Git status timed out", is_error=True)
        except Exception as exc:
            return ToolResult(error=f"Git error: {exc}", is_error=True)


class GitCommit(BaseTool):
    """Stage and commit changes."""

    name = "GitCommit"
    description = "Stage files and create a git commit."
    parameters = {
        "message": {
            "type": "string",
            "description": "Commit message",
            "required": True,
        },
        "files": {
            "type": "list[string]",
            "description": "Specific files to stage (default: all modified)",
            "required": False,
            "default": None,
        },
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        message: str = kwargs["message"]
        files: list[str] | None = kwargs.get("files")

        try:
            # Stage files
            if files:
                # Resolve and validate each file
                resolved: list[str] = []
                for f in files:
                    self._resolve_path(f)  # raises ValueError if outside project
                    resolved.append(f)
                proc_stage = await asyncio.create_subprocess_exec(
                    "git", "add", *resolved,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=self.project_root,
                )
            else:
                proc_stage = await asyncio.create_subprocess_exec(
                    "git", "add", "-A",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=self.project_root,
                )
            _, stderr_s = await asyncio.wait_for(proc_stage.communicate(), timeout=10)
            stage_err = stderr_s.decode("utf-8", errors="replace").strip()
            if stage_err and "not a git repository" in stage_err.lower():
                return ToolResult(output="Not a git repository.")

            # Commit
            proc_commit = await asyncio.create_subprocess_exec(
                "git", "commit", "-m", message,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.project_root,
            )
            stdout_c, stderr_c = await asyncio.wait_for(
                proc_commit.communicate(), timeout=10
            )
            out = stdout_c.decode("utf-8", errors="replace").strip()
            err = stderr_c.decode("utf-8", errors="replace").strip()

            if proc_commit.returncode != 0:
                return ToolResult(error=err or "Commit failed", is_error=True)
            return ToolResult(output=out or f"Committed: {message}")

        except asyncio.TimeoutError:
            return ToolResult(error="Git commit timed out", is_error=True)
        except Exception as exc:
            return ToolResult(error=f"Git error: {exc}", is_error=True)


class AskUser(BaseTool):
    """Request input from the user — raises a special exception for the REPL layer."""

    name = "AskUser"
    description = "Ask the user a question when clarification is needed."
    parameters = {
        "question": {
            "type": "string",
            "description": "Question to ask the user",
            "required": True,
        },
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        question: str = kwargs["question"]
        raise UserInputRequired(question)


# ---------------------------------------------------------------------------
# Exception raised by AskUser
# ---------------------------------------------------------------------------

class UserInputRequired(Exception):
    """Raised when the agent needs input from the user.

    The REPL layer catches this and prompts the human.
    """

    def __init__(self, question: str) -> None:
        self.question = question
        super().__init__(f"User input required: {question}")


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

class ToolRegistry:
    """Registry that holds all available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        # Register all built-in tools
        for tool_cls in (
            ReadFile,
            WriteFile,
            EditFile,
            Shell,
            SearchCode,
            SearchFiles,
            ListDir,
            GitStatus,
            GitCommit,
            AskUser,
        ):
            instance = tool_cls()
            self._tools[instance.name] = instance

    def get_tool(self, name: str) -> BaseTool | None:
        """Retrieve a tool by name."""
        return self._tools.get(name)

    def to_prompt(self) -> str:
        """Return formatted descriptions of all tools for the system prompt."""
        blocks = [tool.to_prompt() for tool in self._tools.values()]
        return "\n\n".join(blocks)

    def __iter__(self):
        return iter(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)

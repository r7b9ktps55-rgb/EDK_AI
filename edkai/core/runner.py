"""Code execution engine for Terminal Studio.

Provides language detection and async execution of source files with
appropriate command mappings and timeouts.
"""

from __future__ import annotations

import asyncio
import os
import shlex
from pathlib import Path
from typing import Any, Dict, List, Optional


# Mapping from language name to default file extensions.
LANGUAGE_EXTENSIONS: Dict[str, List[str]] = {
    "python": [".py"],
    "javascript": [".js", ".mjs"],
    "typescript": [".ts", ".tsx"],
    "rust": [".rs"],
    "go": [".go"],
    "c": [".c"],
    "cpp": [".cpp", ".cc", ".cxx", ".hpp"],
    "bash": [".sh", ".bash"],
}

# Reverse lookup: extension -> language.
EXTENSION_LANGUAGE: Dict[str, str] = {
    ext: lang
    for lang, exts in LANGUAGE_EXTENSIONS.items()
    for ext in exts
}

# Base compilation / run commands.
# {file} is a placeholder for the source file path.
RUN_COMMANDS: Dict[str, List[str]] = {
    "python": ["python", "{file}"],
    "javascript": ["node", "{file}"],
    "typescript": ["npx", "ts-node", "{file}"],
    "rust": ["rustc", "{file}", "-o", "/tmp/rust_out", "&&", "/tmp/rust_out"],
    "go": ["go", "run", "{file}"],
    "c": ["gcc", "{file}", "-o", "/tmp/c_out", "&&", "/tmp/c_out"],
    "cpp": ["g++", "{file}", "-o", "/tmp/cpp_out", "&&", "/tmp/cpp_out"],
    "bash": ["bash", "{file}"],
}

# Languages that must run through a shell (contain && or similar).
SHELL_LANGUAGES: set[str] = {"rust", "c", "cpp"}


class CodeRunner:
    """Detects the programming language of a file and executes it asynchronously.

    Attributes:
        timeout_seconds: Maximum time a process is allowed to run.
    """

    def __init__(self, timeout_seconds: float = 30.0) -> None:
        """Initialise the code runner.

        Args:
            timeout_seconds: Maximum runtime per command in seconds.
        """
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def detect_language(file_path: str) -> str:
        """Detect the programming language from a file path.

        Args:
            file_path: Path to the source file.

        Returns:
            The detected language name, or an empty string if unknown.
        """
        path = Path(file_path)
        ext = path.suffix.lower()
        return EXTENSION_LANGUAGE.get(ext, "")

    @staticmethod
    def get_run_command(
        file_path: str,
        language: Optional[str] = None,
    ) -> List[str]:
        """Get the command list for running a source file.

        Args:
            file_path: Path to the source file.
            language: Language override. If not provided, it is auto-detected.

        Returns:
            A list of command arguments with ``{file}`` replaced by the
            actual file path.

        Raises:
            ValueError: If the language is unknown or unsupported.
        """
        lang = language or CodeRunner.detect_language(file_path)
        if not lang:
            raise ValueError(f"Could not detect language for: {file_path}")

        template = RUN_COMMANDS.get(lang)
        if template is None:
            raise ValueError(f"Unsupported language: {lang}")

        return [arg.replace("{file}", file_path) for arg in template]

    def run(self, file_path: str) -> tuple[List[str], bool]:
        """Prepare a command for running a source file.

        Args:
            file_path: Path to the source file.

        Returns:
            A tuple of ``(command_args, needs_shell)``.

        Raises:
            ValueError: If the language cannot be detected or is unsupported.
        """
        lang = self.detect_language(file_path)
        if not lang:
            raise ValueError(f"Could not detect language for: {file_path}")

        cmd = self.get_run_command(file_path, language=lang)
        needs_shell = lang in SHELL_LANGUAGES
        return cmd, needs_shell

    async def execute(
        self,
        file_path: str,
        language: Optional[str] = None,
        cwd: Optional[str] = None,
    ) -> tuple[str, Optional[int]]:
        """Execute a source file asynchronously.

        Stdout and stderr are captured and returned together. The process is
        killed if it exceeds ``timeout_seconds``.

        Args:
            file_path: Path to the source file.
            language: Language override.
            cwd: Working directory for the subprocess.

        Returns:
            A tuple of ``(combined_output, return_code)``. If the process is
            killed by timeout, ``return_code`` may be ``-1`` or ``None``.

        Raises:
            ValueError: If the language is unsupported.
            FileNotFoundError: If the source file does not exist.
            OSError: For other subprocess execution errors.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Source file not found: {file_path}")

        cmd, needs_shell = self.run(file_path)
        work_dir = cwd or os.getcwd()

        if needs_shell:
            # Join for shell execution; shlex.join handles spaces safely.
            command_line = shlex.join(cmd)
            process = await asyncio.create_subprocess_shell(
                command_line,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=work_dir,
            )
        else:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=work_dir,
            )

        try:
            stdout, _ = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout_seconds,
            )
            output = stdout.decode("utf-8", errors="replace")
            return output, process.returncode
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return f"[timed out after {self.timeout_seconds}s]", -1
        except asyncio.CancelledError:
            process.kill()
            await process.wait()
            raise

    async def run_streaming(
        self,
        file_path: str,
        language: Optional[str] = None,
        cwd: Optional[str] = None,
    ) -> Any:
        """Run a source file and yield output lines as they are produced.

        This is an async generator; use ``async for`` to consume it.

        Args:
            file_path: Path to the source file.
            language: Language override.
            cwd: Working directory.

        Yields:
            Individual lines of output (including trailing newline characters).

        Raises:
            ValueError: If the language is unsupported.
            FileNotFoundError: If the source file does not exist.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Source file not found: {file_path}")

        cmd, needs_shell = self.run(file_path)
        work_dir = cwd or os.getcwd()

        if needs_shell:
            command_line = shlex.join(cmd)
            process = await asyncio.create_subprocess_shell(
                command_line,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=work_dir,
            )
        else:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=work_dir,
            )

        assert process.stdout is not None
        try:
            while True:
                try:
                    line = await asyncio.wait_for(
                        process.stdout.readline(),
                        timeout=self.timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                    yield f"[timed out after {self.timeout_seconds}s]\n"
                    return

                if not line:
                    break
                yield line.decode("utf-8", errors="replace")

            return_code = await process.wait()
            if return_code != 0:
                yield f"[exit code: {return_code}]\n"
        except asyncio.CancelledError:
            process.kill()
            await process.wait()
            raise

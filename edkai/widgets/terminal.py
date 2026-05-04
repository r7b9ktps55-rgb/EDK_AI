"""Terminal panel widget for Terminal Studio.

Provides an embedded terminal / subprocess runner with async streaming of
stdout/stderr, ANSI colour support, and controls for running, clearing,
and stopping shell commands.
"""

from __future__ import annotations

import asyncio
import os
import shlex
from pathlib import Path
from typing import Any, Optional

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Button, Input, RichLog, Static


class TerminalPanel(Static):
    """A terminal/output panel that runs shell commands asynchronously.

    Streams stdout and stderr to a scrollable log widget in real time,
    supports ANSI colour codes, and provides Run, Clear, and Stop controls.
    """

    DEFAULT_CSS = """
    TerminalPanel {
        layout: vertical;
        height: 1fr;
        border: solid $primary;
    }
    TerminalPanel #output-log {
        height: 1fr;
        background: $surface-darken-1;
        color: $text;
    }
    TerminalPanel #controls {
        height: auto;
        dock: bottom;
    }
    TerminalPanel #command-input {
        width: 1fr;
    }
    """

    _process: asyncio.subprocess.Process | None = None
    _cancel_event: asyncio.Event | None = None
    _current_cwd: Optional[str] = None
    running: reactive[bool] = reactive(False)

    def __init__(
        self,
        cwd: Optional[str] = None,
        *,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ) -> None:
        """Initialise the terminal panel.

        Args:
            cwd: Default working directory for commands.
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._current_cwd = cwd or os.getcwd()

    def compose(self) -> ComposeResult:
        """Compose the terminal panel UI."""
        with Vertical():
            yield RichLog(id="output-log", wrap=False, markup=True, highlight=True)
            with Horizontal(id="controls"):
                yield Button("Run", id="run-btn", variant="primary")
                yield Button("Stop", id="stop-btn", variant="error")
                yield Button("Clear", id="clear-btn", variant="default")
                yield Input(
                    placeholder="Type a command and press Enter...",
                    id="command-input",
                )

    def watch_running(self, running: bool) -> None:  # noqa: FBT001
        """Update button states when running status changes."""
        run_btn = self.query_one("#run-btn", Button)
        stop_btn = self.query_one("#stop-btn", Button)
        if running:
            run_btn.disabled = True
            stop_btn.disabled = False
        else:
            run_btn.disabled = False
            stop_btn.disabled = True

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        button_id = event.button.id
        if button_id == "run-btn":
            cmd = self.query_one("#command-input", Input).value.strip()
            if cmd:
                await self.run_command(cmd, cwd=self._current_cwd)
        elif button_id == "stop-btn":
            await self.stop_command()
        elif button_id == "clear-btn":
            self.clear_output()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle command input submission (Enter key)."""
        if event.input.id == "command-input":
            cmd = event.value.strip()
            if cmd:
                await self.run_command(cmd, cwd=self._current_cwd)
                event.input.value = ""

    def clear_output(self) -> None:
        """Clear the output log."""
        self.query_one("#output-log", RichLog).clear()

    def _append_output(self, text: str) -> None:
        """Append text to the output log, parsing ANSI codes if present."""
        log = self.query_one("#output-log", RichLog)
        # RichLog.write handles ANSI via Rich markup / console
        # We pass the raw text; RichLog will render ANSI if highlight=True
        log.write(text, scroll_end=True)

    def run_command(self, cmd: str, cwd: Optional[str] = None) -> asyncio.Task[Any]:
        """Run a shell command asynchronously and stream output.

        Args:
            cmd: The command string to execute.
            cwd: Working directory for the subprocess. Defaults to the
                panel's current working directory.

        Returns:
            The asyncio Task running the command.
        """
        task = asyncio.create_task(self._run_command_async(cmd, cwd))
        return task

    async def _run_command_async(self, cmd: str, cwd: Optional[str] = None) -> None:
        """Async worker that executes a command and streams its output.

        Args:
            cmd: Command string.
            cwd: Working directory.
        """
        if self.running:
            self._append_output("[already running a command; stop it first]\n")
            return

        work_dir = cwd or self._current_cwd or os.getcwd()
        self.running = True
        self._append_output(f"$ {cmd}\n")

        try:
            # Use shell=True for complex commands (e.g., pipes, &&)
            # but parse safely for simple commands.
            shell_mode = any(c in cmd for c in "|&;<>" if c in cmd) or " && " in cmd
            if shell_mode:
                self._process = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    cwd=work_dir,
                )
            else:
                args = shlex.split(cmd)
                self._process = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    cwd=work_dir,
                )

            assert self._process.stdout is not None
            while True:
                try:
                    line_bytes = await asyncio.wait_for(
                        self._process.stdout.readline(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    # Yield control and check if we should stop.
                    await asyncio.sleep(0.05)
                    if self._cancel_event is not None and self._cancel_event.is_set():
                        break
                    continue

                if not line_bytes:
                    break

                line = line_bytes.decode("utf-8", errors="replace")
                self._append_output(line)

            # Wait for process to finish (with a short grace period).
            try:
                return_code = await asyncio.wait_for(
                    self._process.wait(), timeout=5.0
                )
            except asyncio.TimeoutError:
                self._process.kill()
                return_code = -1
                self._append_output("\n[process killed after timeout]\n")

            if return_code != 0 and not (self._cancel_event and self._cancel_event.is_set()):
                self._append_output(f"\n[exit code: {return_code}]\n")
            elif not (self._cancel_event and self._cancel_event.is_set()):
                self._append_output("\n[done]\n")

        except asyncio.CancelledError:
            if self._process is not None:
                self._process.kill()
                await self._process.wait()
            self._append_output("\n[cancelled]\n")
            raise
        except FileNotFoundError as exc:
            self._append_output(f"\n[error: command not found: {exc.filename}]\n")
        except PermissionError as exc:
            self._append_output(f"\n[error: permission denied: {exc.filename}]\n")
        except OSError as exc:
            self._append_output(f"\n[error: {exc}]\n")
        finally:
            self._process = None
            self._cancel_event = None
            self.running = False

    async def stop_command(self) -> None:
        """Stop the currently running command."""
        if self._process is None:
            return

        self._cancel_event = asyncio.Event()
        self._cancel_event.set()

        self._append_output("\n[stopping...]\n")
        self._process.terminate()
        try:
            await asyncio.wait_for(self._process.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            self._process.kill()
            await self._process.wait()
        self._append_output("[stopped]\n")
        self._process = None
        self._cancel_event = None
        self.running = False

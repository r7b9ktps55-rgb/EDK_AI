"""AI-enhanced terminal panel for Terminal Studio.

Extends :class:`TerminalPanel` with AI error analysis, command suggestions,
and keyboard shortcuts for AI-powered terminal workflows.
"""

from __future__ import annotations

import asyncio
from typing import Any, List, Optional

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Button, Input, RichLog, Static

from edkai.widgets.terminal import TerminalPanel
from edkai.ai.terminal_copilot import TerminalCopilot
from edkai.ai.client import AIClient


class AITerminalPanel(TerminalPanel):
    """Terminal with AI error analysis and command suggestions.

    In addition to the standard terminal functionality this panel:

    * Shows **[Explain]** and **[Fix]** buttons when a command exits with a
      non-zero code.
    * Provides AI command autocomplete based on shell history.
    * ``Ctrl+Shift+E`` — ask AI to explain the last command/output.
    * ``Ctrl+Shift+C`` — ask AI to suggest a command for a task.

    Attributes:
        copilot: The :class:`TerminalCopilot` instance used for AI calls.
        _last_command: The most recently executed command string.
        _last_output: Accumulated output from the last command.
        _last_exit_code: Exit code of the last command.
        _command_history: List of previously run commands for autocomplete.
    """

    DEFAULT_CSS = """
    AITerminalPanel {
        layout: vertical;
        height: 1fr;
        border: solid $primary;
    }
    AITerminalPanel #output-log {
        height: 1fr;
        background: $surface-darken-1;
        color: $text;
    }
    AITerminalPanel #controls {
        height: auto;
        dock: bottom;
    }
    AITerminalPanel #command-input {
        width: 1fr;
    }
    AITerminalPanel #ai-actions {
        height: auto;
        dock: bottom;
        display: none;
    }
    AITerminalPanel #ai-explain-btn {
        width: auto;
    }
    AITerminalPanel #ai-fix-btn {
        width: auto;
    }
    AITerminalPanel #ai-apply-btn {
        width: auto;
    }
    AITerminalPanel #ai-suggestion-text {
        height: auto;
        background: $surface-darken-2;
        color: $text;
        padding: 1 2;
        display: none;
    }
    """

    _last_command: str = ""
    _last_output: str = ""
    _last_exit_code: int = 0
    _command_history: List[str] = []
    _pending_suggestion: Optional[str] = None

    copilot: TerminalCopilot | None = None

    show_ai_actions: reactive[bool] = reactive(False)
    show_suggestion: reactive[bool] = reactive(False)

    def __init__(
        self,
        client: AIClient | None = None,
        cwd: Optional[str] = None,
        *,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ) -> None:
        """Initialise the AI terminal panel.

        Args:
            client: An optional :class:`AIClient` for AI features.
            cwd: Default working directory for commands.
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(cwd=cwd, name=name, id=id, classes=classes)
        if client is not None:
            self.copilot = TerminalCopilot(client)

    def compose(self) -> ComposeResult:
        """Compose the AI terminal panel UI."""
        with Vertical():
            yield RichLog(id="output-log", wrap=False, markup=True, highlight=True)
            yield Static(id="ai-suggestion-text")
            with Horizontal(id="ai-actions"):
                yield Button("Explain", id="ai-explain-btn", variant="primary")
                yield Button("Fix", id="ai-fix-btn", variant="warning")
                yield Button("Apply", id="ai-apply-btn", variant="success")
            with Horizontal(id="controls"):
                yield Button("Run", id="run-btn", variant="primary")
                yield Button("Stop", id="stop-btn", variant="error")
                yield Button("Clear", id="clear-btn", variant="default")
                yield Input(
                    placeholder="Type a command and press Enter…",
                    id="command-input",
                )

    def watch_show_ai_actions(self, show: bool) -> None:  # noqa: FBT001
        """Toggle visibility of the AI action buttons."""
        actions = self.query_one("#ai-actions", Horizontal)
        actions.display = show

    def watch_show_suggestion(self, show: bool) -> None:  # noqa: FBT001
        """Toggle visibility of the AI suggestion text."""
        suggestion = self.query_one("#ai-suggestion-text", Static)
        suggestion.display = show

    # ------------------------------------------------------------------
    # Override run_command to capture output and exit codes.
    # ------------------------------------------------------------------

    def run_command(self, cmd: str, cwd: Optional[str] = None) -> asyncio.Task[Any]:
        """Run a command and hook into its lifecycle for AI features.

        Args:
            cmd: The command string to execute.
            cwd: Working directory override.

        Returns:
            The asyncio Task running the command.
        """
        self._last_command = cmd
        self._last_output = ""
        self._last_exit_code = 0
        self._pending_suggestion = None
        self.show_ai_actions = False
        self.show_suggestion = False
        if cmd not in self._command_history:
            self._command_history.append(cmd)
        return super().run_command(cmd, cwd=cwd)

    def _append_output(self, text: str) -> None:
        """Override to also accumulate output for AI analysis."""
        super()._append_output(text)
        self._last_output += text

    async def _run_command_async(self, cmd: str, cwd: Optional[str] = None) -> None:
        """Run a command and show AI buttons on non-zero exit."""
        await super()._run_command_async(cmd, cwd)
        # After the base implementation the process has finished.
        # Heuristic: if the accumulated output contains an exit-code line
        # we can treat it as a failure.
        if self._last_exit_code != 0 or "[exit code:" in self._last_output:
            if self.copilot is not None:
                self.show_ai_actions = True

    # ------------------------------------------------------------------
    # Event handlers — AI buttons
    # ------------------------------------------------------------------

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle AI action buttons as well as base buttons."""
        bid = event.button.id
        if bid == "ai-explain-btn":
            await self._ai_explain()
        elif bid == "ai-fix-btn":
            await self._ai_fix()
        elif bid == "ai-apply-btn":
            await self._ai_apply()
        else:
            await super().on_button_pressed(event)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle command input and Ctrl+Shift shortcuts."""
        if event.input.id == "command-input":
            value = event.value.strip()
            if not value:
                return
            # Hidden shortcuts via input prefix.
            if value.startswith("?explain "):
                self._last_command = value[9:]
                await self._ai_explain()
                event.input.value = ""
                return
            if value.startswith("?fix "):
                self._last_command = value[5:]
                await self._ai_fix()
                event.input.value = ""
                return
            if value.startswith("?cmd "):
                task = value[5:]
                await self._ai_suggest_command(task)
                event.input.value = ""
                return
            await super().on_input_submitted(event)

    # ------------------------------------------------------------------
    # AI workflows
    # ------------------------------------------------------------------

    async def _ai_explain(self) -> None:
        """Ask the AI to explain the last command failure."""
        if self.copilot is None or not self._last_command:
            self._append_output("\n[AI copilot not available]\n")
            return
        self._append_output("\n[AI analyzing …]\n")
        try:
            explanation = await self.copilot.explain_error(
                self._last_output, self._last_command
            )
            self._append_output(f"\n[bold]Explanation[/bold]:\n{explanation}\n")
        except Exception as exc:  # noqa: BLE001
            self._append_output(f"\n[AI error: {exc}]\n")

    async def _ai_fix(self) -> None:
        """Ask the AI to suggest a fix for the last command failure."""
        if self.copilot is None or not self._last_command:
            self._append_output("\n[AI copilot not available]\n")
            return
        self._append_output("\n[AI suggesting fix …]\n")
        try:
            fix = await self.copilot.suggest_fix(
                self._last_output,
                self._last_command,
                self._current_cwd or "",
            )
            if fix is None:
                self._append_output("\n[AI: No automatic fix available]\n")
                self.show_ai_actions = False
                return
            self._pending_suggestion = fix
            suggestion_widget = self.query_one("#ai-suggestion-text", Static)
            suggestion_widget.update(f"Suggested fix: {fix}")
            self.show_suggestion = True
            self.show_ai_actions = True
            self._append_output(f"\n[bold]Suggested fix[/bold]: {fix}\n")
        except Exception as exc:  # noqa: BLE001
            self._append_output(f"\n[AI error: {exc}]\n")

    async def _ai_apply(self) -> None:
        """Run the AI-suggested fix command."""
        if self._pending_suggestion:
            self.show_suggestion = False
            await self.run_command(self._pending_suggestion, cwd=self._current_cwd)
            self._pending_suggestion = None

    async def _ai_suggest_command(self, task: str) -> None:
        """Ask the AI to convert a task description into a command."""
        if self.copilot is None:
            self._append_output("\n[AI copilot not available]\n")
            return
        self._append_output(f"\n[AI suggesting command for: {task} …]\n")
        try:
            command = await self.copilot.suggest_command(
                task, self._current_cwd or ""
            )
            self._pending_suggestion = command
            suggestion_widget = self.query_one("#ai-suggestion-text", Static)
            suggestion_widget.update(f"AI suggestion: {command}")
            self.show_suggestion = True
            self.show_ai_actions = True
            self._append_output(f"\n[bold]AI suggestion[/bold]: {command}\n")
        except Exception as exc:  # noqa: BLE001
            self._append_output(f"\n[AI error: {exc}]\n")

    # ------------------------------------------------------------------
    # Keyboard shortcuts (handled by the app binding layer)
    # ------------------------------------------------------------------

    def action_ai_explain(self) -> None:
        """Action hook for Ctrl+Shift+E — explain last output."""
        asyncio.create_task(self._ai_explain())

    def action_ai_suggest_command(self) -> None:
        """Action hook for Ctrl+Shift+C — open AI command suggestion."""
        # The app should push an overlay; here we just trigger a placeholder.
        asyncio.create_task(self._ai_suggest_command(""))

    # ------------------------------------------------------------------
    # Autocomplete helpers
    # ------------------------------------------------------------------

    def get_suggestions(self, prefix: str) -> List[str]:
        """Return matching commands from history + AI suggestions.

        Args:
            prefix: The current input prefix.

        Returns:
            A list of suggested command strings.
        """
        prefix_lower = prefix.lower()
        hits: List[str] = []
        for cmd in reversed(self._command_history):
            if cmd.lower().startswith(prefix_lower) and cmd not in hits:
                hits.append(cmd)
                if len(hits) >= 5:
                    break
        return hits

    async def autocomplete(self, prefix: str) -> Optional[str]:
        """Return the best autocomplete match for *prefix*.

        Falls back to asking the AI for a command suggestion when no
        history match is found.

        Args:
            prefix: The current input prefix.

        Returns:
            A command string or ``None``.
        """
        suggestions = self.get_suggestions(prefix)
        if suggestions:
            return suggestions[0]
        if self.copilot is not None and prefix:
            try:
                return await self.copilot.suggest_command(prefix, self._current_cwd or "")
            except Exception:  # noqa: BLE001, S110
                pass
        return None

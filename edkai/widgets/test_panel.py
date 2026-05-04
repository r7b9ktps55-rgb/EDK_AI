"""Test panel widget for Terminal Studio.

Displays test results with clickable failures, progress spinners, action
buttons, and collapsible sections per test file. Integrates with the
:class:`TestRunner`, :class:`TestGenerator`, and :class:`AutoFixEngine`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Optional

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.message import Message
from textual.widgets import Button, Collapsible, Label, Static

from edkai.core.test_runner import Failure, TestResult, TestRunner
from edkai.ai.test_generator import TestGenerator
from edkai.core.auto_fix import AutoFixEngine


# ---------------------------------------------------------------------------
# Individual failure row
# ---------------------------------------------------------------------------


class FailureRow(Static):
    """A clickable test failure row.

    Displays the test name, file, and line number. Clicking the row posts
    a :class:`JumpToFile` message that the app can handle to navigate to
    the failure location.
    """

    DEFAULT_CSS = """
    FailureRow {
        height: auto;
        margin: 0 0 1 0;
        padding: 0 2;
        color: $error;
        text-style: bold;
    }
    FailureRow:hover {
        background: $error-darken-3;
    }
    """

    def __init__(
        self,
        failure: Failure,
        *,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ) -> None:
        """Initialise a failure row.

        Args:
            failure: The :class:`Failure` to display.
            name: Widget name.
            id: Widget identifier.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self.failure = failure

    def compose(self) -> ComposeResult:
        """Compose the failure row UI."""
        line_info = f":{self.failure.line}" if self.failure.line else ""
        yield Label(
            f"❌ {self.failure.test_name}  ({self.failure.file}{line_info})",
            classes="failure-label",
        )

    def on_click(self) -> None:
        """Post a jump-to-file message when the row is clicked."""
        self.post_message(self.JumpToFile(self.failure.file, self.failure.line))

    class JumpToFile(Message):
        """Message sent when a failure row is clicked.

        Attributes:
            file_path: Path to the source file.
            line: 1-based line number.
        """

        def __init__(self, file_path: str, line: int) -> None:
            super().__init__()
            self.file_path = file_path
            self.line = line


# ---------------------------------------------------------------------------
# Result section (collapsible)
# ---------------------------------------------------------------------------


class ResultSection(Collapsible):
    """A collapsible section for a single test file's results."""

    def __init__(
        self,
        title: str,
        result: TestResult,
        *,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ) -> None:
        """Initialise a result section.

        Args:
            title: Section title (usually the framework or file name).
            result: The :class:`TestResult` to render inside.
            name: Widget name.
            id: Widget identifier.
            classes: CSS classes.
        """
        super().__init__(title=title, name=name, id=id, classes=classes)
        self.result = result

    def compose(self) -> ComposeResult:
        """Compose the section content."""
        summary = (
            f"✅ {self.result.passed} passed  "
            f"❌ {self.result.failed} failed  "
            f"⚠ {self.result.errors} errors"
        )
        yield Label(summary, classes="result-summary")
        for failure in self.result.failures:
            yield FailureRow(failure)


# ---------------------------------------------------------------------------
# Main test panel
# ---------------------------------------------------------------------------


class TestPanel(Static):
    """Displays test results with clickable failures.

    Provides action buttons, a progress spinner, and collapsible sections
    per test file / framework. Integrates with :class:`TestRunner`,
    :class:`TestGenerator`, and :class:`AutoFixEngine`.
    """

    DEFAULT_CSS = """
    TestPanel {
        layout: vertical;
        height: 1fr;
        border: solid $accent;
        background: $surface-darken-1;
    }
    TestPanel #results-scroll {
        height: 1fr;
        background: $surface-darken-1;
    }
    TestPanel #results-container {
        height: auto;
    }
    TestPanel #button-row {
        height: auto;
        dock: top;
        padding: 0 1;
    }
    TestPanel #spinner-label {
        height: auto;
        content-align: center middle;
        color: $warning;
        text-style: bold;
    }
    TestPanel .result-summary {
        height: auto;
        padding: 0 1;
        text-style: bold;
    }
    TestPanel .empty-state {
        height: auto;
        content-align: center middle;
        color: $text-muted;
    }
    """

    _running: bool = False
    _runner: TestRunner | None = None
    _generator: TestGenerator | None = None
    _auto_fix: AutoFixEngine | None = None
    _project_root: str = ""
    _language: str = ""

    def __init__(
        self,
        runner: TestRunner | None = None,
        generator: TestGenerator | None = None,
        auto_fix: AutoFixEngine | None = None,
        *,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ) -> None:
        """Initialise the test panel.

        Args:
            runner: A :class:`TestRunner` instance (created if omitted).
            generator: A :class:`TestGenerator` instance (created if omitted).
            auto_fix: An :class:`AutoFixEngine` instance (created if omitted).
            name: Widget name.
            id: Widget identifier.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._runner = runner
        self._generator = generator
        self._auto_fix = auto_fix

    def compose(self) -> ComposeResult:
        """Compose the test panel UI."""
        with Horizontal(id="button-row"):
            yield Button("Run All", id="btn-run-all", variant="primary")
            yield Button("Run Failed", id="btn-run-failed", variant="warning")
            yield Button("Generate Tests", id="btn-gen-tests", variant="success")
        yield Label("", id="spinner-label")
        with VerticalScroll(id="results-scroll"):
            yield Vertical(id="results-container")

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def set_project(self, project_root: str, language: str = "") -> None:
        """Set the project context for test operations.

        Args:
            project_root: Root directory of the project.
            language: Programming language of the project.
        """
        self._project_root = project_root
        self._language = language

    def set_context_code(self, file_path: str, code: str) -> None:
        """Set the current file context for test generation.

        Args:
            file_path: Path to the active source file.
            code: Content of the active source file.
        """
        self._context_file = file_path
        self._context_code = code

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------

    def _show_spinner(self, message: str = "Running tests …") -> None:
        """Show the spinner label with *message*."""
        spinner = self.query_one("#spinner-label", Label)
        spinner.update(f"⏳ {message}")

    def _hide_spinner(self) -> None:
        """Clear the spinner label."""
        spinner = self.query_one("#spinner-label", Label)
        spinner.update("")

    def _clear_results(self) -> None:
        """Remove all result sections from the container."""
        container = self.query_one("#results-container", Vertical)
        container.remove_children()

    def _add_result(self, result: TestResult) -> None:
        """Add a :class:`ResultSection` for *result*.

        Args:
            result: The test result to display.
        """
        container = self.query_one("#results-container", Vertical)
        title = f"{result.framework} — {result.passed} passed / {result.failed} failed"
        section = ResultSection(title, result)
        container.mount(section)

    def _show_empty(self, message: str) -> None:
        """Display an empty-state message.

        Args:
            message: Text to display.
        """
        container = self.query_one("#results-container", Vertical)
        container.mount(Label(message, classes="empty-state"))

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id
        if button_id == "btn-run-all":
            await self._action_run_all()
        elif button_id == "btn-run-failed":
            await self._action_run_failed()
        elif button_id == "btn-gen-tests":
            await self._action_generate_tests()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    async def _action_run_all(self) -> None:
        """Run all tests in the configured project."""
        if not self._project_root:
            self._clear_results()
            self._show_empty("No project configured — open a project first.")
            return

        if self._running:
            return

        self._running = True
        self._clear_results()
        self._show_spinner("Running all tests …")

        runner = self._runner or TestRunner()
        try:
            result = await runner.run_tests(self._project_root, self._language)
            self._clear_results()
            if result.raw_output and not result.failures and result.passed == 0 and result.failed == 0:
                # Likely a raw / unparseable run — show output.
                self._show_empty(result.raw_output[:2000])
            else:
                self._add_result(result)
                if result.failures:
                    for failure in result.failures:
                        self._add_result(TestResult(
                            framework=f"fail: {failure.test_name}",
                            failures=[failure],
                        ))
        except Exception as exc:
            self._clear_results()
            self._show_empty(f"Error running tests: {exc}")
        finally:
            self._hide_spinner()
            self._running = False

    async def _action_run_failed(self) -> None:
        """Re-run only the previously failed tests.

        This is a placeholder that re-runs the full suite; a production
        implementation could track failed test names and run selectively.
        """
        # For now, re-run the full suite — the runner will report only
        # currently-failing tests.
        await self._action_run_all()

    async def _action_generate_tests(self) -> None:
        """Generate tests for the current file context using AI."""
        if not getattr(self, "_context_code", None) or not getattr(self, "_context_file", None):
            self._clear_results()
            self._show_empty("No file context — open a source file first.")
            return

        if self._running:
            return

        self._running = True
        self._clear_results()
        self._show_spinner("Generating tests with AI …")

        generator = self._generator or TestGenerator()
        try:
            language = self._detect_language(self._context_file)
            test_code = await generator.generate_tests_clean(
                self._context_code,
                language,
            )
            self._clear_results()
            # Show the generated test code in a collapsible section.
            container = self.query_one("#results-container", Vertical)
            from textual.widgets import TextArea
            text_area = TextArea(
                test_code,
                language=language,
                theme="vscode_dark",
                soft_wrap=False,
                id="generated-tests",
            )
            container.mount(Collapsible(title="Generated Tests", children=[text_area]))
        except Exception as exc:
            self._clear_results()
            self._show_empty(f"Error generating tests: {exc}")
        finally:
            self._hide_spinner()
            self._running = False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_language(file_path: str) -> str:
        """Guess language from file extension.

        Args:
            file_path: Path to the source file.

        Returns:
            Language name suitable for :class:`TestGenerator`.
        """
        ext = Path(file_path).suffix.lstrip(".").lower()
        mapping = {
            "py": "python",
            "js": "javascript",
            "ts": "typescript",
            "tsx": "typescript",
            "rs": "rust",
            "go": "go",
            "c": "c",
            "cpp": "cpp",
            "cc": "cpp",
            "sh": "bash",
        }
        return mapping.get(ext, ext)

    def __repr__(self) -> str:
        """Return a developer-friendly representation."""
        return (
            f"<{type(self).__name__} "
            f"project={self._project_root!r} "
            f"language={self._language!r}>"
        )

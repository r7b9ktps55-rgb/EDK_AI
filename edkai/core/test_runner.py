"""Test runner for Terminal Studio.

Discovers the appropriate test framework for a project, executes tests via
subprocess, and parses the output into structured :class:`TestResult` and
:class:`Failure` objects with file / line metadata for jump-to-error.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class Failure:
    """A single test failure with jump-to-error metadata.

    Attributes:
        test_name: Human-readable test identifier.
        file: Absolute or relative path to the source file.
        line: 1-based line number where the failure originated.
        message: Short failure description.
        traceback: Full traceback or failure details (may be multi-line).
    """

    test_name: str = ""
    file: str = ""
    line: int = 0
    message: str = ""
    traceback: str = ""


@dataclass
class TestResult:
    """Aggregated result of a test run.

    Attributes:
        passed: Number of tests that passed.
        failed: Number of tests that failed.
        errors: Number of tests with errors (unexpected exceptions).
        failures: List of individual :class:`Failure` records.
        raw_output: Complete stdout / stderr combined output.
        duration_ms: Approximate duration of the run in milliseconds.
        framework: The test framework that was used.
    """

    passed: int = 0
    failed: int = 0
    errors: int = 0
    failures: List[Failure] = field(default_factory=list)
    raw_output: str = ""
    duration_ms: float = 0.0
    framework: str = ""


# ---------------------------------------------------------------------------
# Framework detection
# ---------------------------------------------------------------------------


TEST_FRAMEWORK_FILES: Dict[str, List[str]] = {
    "pytest": ["pytest.ini", "setup.cfg", "pyproject.toml", "conftest.py"],
    "jest": ["jest.config.js", "jest.config.ts", "package.json"],
    "cargo": ["Cargo.toml"],
    "go": ["go.mod"],
}

FRAMEWORK_COMMANDS: Dict[str, List[str]] = {
    "pytest": ["python", "-m", "pytest"],
    "jest": ["npx", "jest"],
    "cargo": ["cargo", "test"],
    "go": ["go", "test", "./..."],
}


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class TestRunner:
    """Runs tests and captures results with jump-to-error.

    The runner auto-detects the test framework, executes the appropriate
    command, and parses the output into structured dataclasses.

    Attributes:
        timeout_seconds: Maximum time a test process is allowed to run.
    """

    def __init__(self, timeout_seconds: float = 120.0) -> None:
        """Initialise the test runner.

        Args:
            timeout_seconds: Maximum runtime per test command in seconds.
        """
        self.timeout_seconds = timeout_seconds

    # ------------------------------------------------------------------
    # Framework detection
    # ------------------------------------------------------------------

    @staticmethod
    def detect_framework(project_root: str) -> Optional[str]:
        """Detect the test framework used in *project_root*.

        Args:
            project_root: Path to the project directory.

        Returns:
            Framework name (``"pytest"``, ``"jest"``, ``"cargo"``, ``"go"``)
            or ``None`` if no framework is detected.
        """
        root = Path(project_root)
        for framework, markers in TEST_FRAMEWORK_FILES.items():
            for marker in markers:
                if (root / marker).exists():
                    # For package.json, do a quick contents check for jest.
                    if marker == "package.json":
                        try:
                            content = (root / marker).read_text(encoding="utf-8")
                            if "jest" not in content.lower():
                                continue
                        except OSError:
                            continue
                    return framework
        # Fallback: look for *.py test files -> pytest
        if list(root.rglob("test_*.py")) or list(root.rglob("*_test.py")):
            return "pytest"
        return None

    @staticmethod
    def framework_for_language(language: str) -> Optional[str]:
        """Return a default framework for a given programming language.

        Args:
            language: Programming language name.

        Returns:
            Framework name or ``None``.
        """
        mapping = {
            "python": "pytest",
            "javascript": "jest",
            "typescript": "jest",
            "rust": "cargo",
            "go": "go",
        }
        return mapping.get(language.lower())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_tests(
        self,
        project_root: str,
        language: Optional[str] = None,
    ) -> TestResult:
        """Run all tests in *project_root*.

        The framework is detected automatically; *language* is used as a
        fallback hint when detection fails.

        Args:
            project_root: Directory containing the project.
            language: Optional language hint for framework selection.

        Returns:
            A :class:`TestResult` with parsed statistics and failures.
        """
        framework = self.detect_framework(project_root)
        if framework is None and language:
            framework = self.framework_for_language(language)
        if framework is None:
            return TestResult(
                raw_output="[no test framework detected]",
                framework="unknown",
            )

        cmd = FRAMEWORK_COMMANDS.get(framework, [])
        if not cmd:
            return TestResult(
                raw_output=f"[no command configured for {framework}]",
                framework=framework,
            )

        return await self._run_subprocess(cmd, project_root, framework)

    async def run_single_test(self, test_path: str) -> TestResult:
        """Run a single test file.

        The framework is inferred from the file extension and surrounding
        project structure.

        Args:
            test_path: Path to the test file.

        Returns:
            A :class:`TestResult` with parsed statistics and failures.
        """
        path = Path(test_path)
        if not path.exists():
            return TestResult(
                raw_output=f"[file not found: {test_path}]",
                framework="unknown",
            )

        project_root = str(path.parent)
        framework = self.detect_framework(project_root)

        ext = path.suffix.lower()
        if framework is None:
            ext_map = {
                ".py": "pytest",
                ".js": "jest",
                ".ts": "jest",
                ".tsx": "jest",
                ".go": "go",
                ".rs": "cargo",
            }
            framework = ext_map.get(ext)

        if framework is None:
            return TestResult(
                raw_output="[could not determine test framework]",
                framework="unknown",
            )

        # Build file-specific command.
        cmd: List[str] = []
        if framework == "pytest":
            cmd = ["python", "-m", "pytest", str(path), "-v"]
        elif framework == "jest":
            cmd = ["npx", "jest", str(path)]
        elif framework == "go":
            cmd = ["go", "test", str(path)]
        elif framework == "cargo":
            # Cargo runs from the crate root; use --test or file path logic.
            cmd = ["cargo", "test", "--", str(path.name)]
        else:
            cmd = FRAMEWORK_COMMANDS.get(framework, []) + [str(path)]

        return await self._run_subprocess(cmd, project_root, framework)

    # ------------------------------------------------------------------
    # Subprocess execution
    # ------------------------------------------------------------------

    async def _run_subprocess(
        self,
        cmd: List[str],
        cwd: str,
        framework: str,
    ) -> TestResult:
        """Execute *cmd* and parse the output.

        Args:
            cmd: Command tokens.
            cwd: Working directory.
            framework: Framework name for parser selection.

        Returns:
            Parsed :class:`TestResult`.
        """
        import time

        start = time.monotonic()
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=cwd,
            )
            stdout, _ = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout_seconds,
            )
            output = stdout.decode("utf-8", errors="replace")
        except asyncio.TimeoutError:
            output = f"[timed out after {self.timeout_seconds}s]"
            return TestResult(
                raw_output=output,
                framework=framework,
                duration_ms=self.timeout_seconds * 1000,
            )
        except FileNotFoundError as exc:
            output = f"[command not found: {exc.filename}]"
            return TestResult(
                raw_output=output,
                framework=framework,
            )
        except OSError as exc:
            output = f"[OS error: {exc}]"
            return TestResult(
                raw_output=output,
                framework=framework,
            )

        duration_ms = (time.monotonic() - start) * 1000

        if framework == "pytest":
            return self._parse_pytest(output, duration_ms)
        if framework == "jest":
            return self._parse_jest(output, duration_ms)
        if framework == "go":
            return self._parse_go(output, duration_ms)
        if framework == "cargo":
            return self._parse_cargo(output, duration_ms)

        return TestResult(
            raw_output=output,
            framework=framework,
            duration_ms=duration_ms,
        )

    # ------------------------------------------------------------------
    # Pytest parser
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_pytest(output: str, duration_ms: float) -> TestResult:
        """Parse pytest verbose / default output.

        Args:
            output: Combined stdout / stderr.
            duration_ms: Duration of the run.

        Returns:
            Parsed :class:`TestResult`.
        """
        result = TestResult(raw_output=output, framework="pytest", duration_ms=duration_ms)

        # Summary line patterns.
        summary_match = re.search(
            r"(\d+) passed(?:, )?(\d+ failed)?(?:, )?(\d+ error)?",
            output,
        )
        if summary_match:
            result.passed = int(summary_match.group(1)) if summary_match.group(1) else 0
            result.failed = int(summary_match.group(2)) if summary_match.group(2) else 0
            result.errors = int(summary_match.group(3)) if summary_match.group(3) else 0

        # Parse failures: pytest verbose format.
        failure_blocks = re.findall(
            r"FAILED\s+([^\s]+)\s+-\s+(.*?)(?=\nPASSED|\nFAILED|\n=+|$)",
            output,
            re.DOTALL,
        )
        for test_name, details in failure_blocks:
            # Try to extract file:line from traceback inside details.
            file_line_match = re.search(
                r'File\s+"([^"]+)",\s+line\s+(\d+)',
                details,
            )
            file_path = file_line_match.group(1) if file_line_match else ""
            line_num = int(file_line_match.group(2)) if file_line_match else 0
            # Extract the assertion / error line.
            msg_match = re.search(r">\s*(.*?)(?:\n|$)", details)
            message = msg_match.group(1).strip() if msg_match else details.strip()[:200]
            result.failures.append(
                Failure(
                    test_name=test_name.strip(),
                    file=file_path,
                    line=line_num,
                    message=message,
                    traceback=details.strip(),
                )
            )

        # Also catch ERROR blocks.
        error_blocks = re.findall(
            r"ERROR\s+([^\s]+)\s+-\s+(.*?)(?=\nPASSED|\nFAILED|\nERROR|\n=+|$)",
            output,
            re.DOTALL,
        )
        for test_name, details in error_blocks:
            file_line_match = re.search(
                r'File\s+"([^"]+)",\s+line\s+(\d+)',
                details,
            )
            file_path = file_line_match.group(1) if file_line_match else ""
            line_num = int(file_line_match.group(2)) if file_line_match else 0
            msg_match = re.search(r">\s*(.*?)(?:\n|$)", details)
            message = msg_match.group(1).strip() if msg_match else details.strip()[:200]
            result.failures.append(
                Failure(
                    test_name=test_name.strip(),
                    file=file_path,
                    line=line_num,
                    message=message,
                    traceback=details.strip(),
                )
            )

        return result

    # ------------------------------------------------------------------
    # Jest parser
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_jest(output: str, duration_ms: float) -> TestResult:
        """Parse Jest JSON or text output.

        Args:
            output: Combined stdout / stderr.
            duration_ms: Duration of the run.

        Returns:
            Parsed :class:`TestResult`.
        """
        result = TestResult(raw_output=output, framework="jest", duration_ms=duration_ms)

        # Try JSON summary first.
        json_match = re.search(r"\{.*\"numTotalTests\".*\}", output, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                result.passed = data.get("numPassedTests", 0)
                result.failed = data.get("numFailedTests", 0)
                # Jest doesn't separate "errors" from failures.
                result.errors = 0
                for suite in data.get("testResults", []):
                    for test in suite.get("assertionResults", []):
                        if test.get("status") == "failed":
                            result.failures.append(
                                Failure(
                                    test_name=test.get("title", "unknown"),
                                    file=suite.get("name", ""),
                                    line=0,
                                    message=test.get("failureMessages", [""])[0][:500],
                                    traceback="\n".join(test.get("failureMessages", [])),
                                )
                            )
                return result
            except json.JSONDecodeError:
                pass

        # Fallback text parsing.
        passed_match = re.search(r"Tests:\s+(\d+) passed", output)
        failed_match = re.search(r"Tests:\s+(?:\d+ passed,\s+)?(\d+) failed", output)
        if passed_match:
            result.passed = int(passed_match.group(1))
        if failed_match:
            result.failed = int(failed_match.group(1))

        return result

    # ------------------------------------------------------------------
    # Go parser
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_go(output: str, duration_ms: float) -> TestResult:
        """Parse ``go test -v`` output.

        Args:
            output: Combined stdout / stderr.
            duration_ms: Duration of the run.

        Returns:
            Parsed :class:`TestResult`.
        """
        result = TestResult(raw_output=output, framework="go", duration_ms=duration_ms)

        passed_count = len(re.findall(r"^---\s+PASS:", output, re.MULTILINE))
        failed_count = len(re.findall(r"^---\s+FAIL:", output, re.MULTILINE))
        result.passed = passed_count
        result.failed = failed_count

        # Extract failure details.
        fail_blocks = re.findall(
            r"^---\s+FAIL:\s+(.*?)\s+\((.*?\))\n(.*?)(?=\n---\s+(PASS|FAIL):|\nFAIL\s|$)",
            output,
            re.MULTILINE | re.DOTALL,
        )
        for test_name, _duration, details in fail_blocks:
            file_match = re.search(r"(\S+\.go):(\d+)", details)
            file_path = file_match.group(1) if file_match else ""
            line_num = int(file_match.group(2)) if file_match else 0
            result.failures.append(
                Failure(
                    test_name=test_name.strip(),
                    file=file_path,
                    line=line_num,
                    message=details.strip()[:500],
                    traceback=details.strip(),
                )
            )

        return result

    # ------------------------------------------------------------------
    # Cargo / Rust parser
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_cargo(output: str, duration_ms: float) -> TestResult:
        """Parse ``cargo test`` output.

        Args:
            output: Combined stdout / stderr.
            duration_ms: Duration of the run.

        Returns:
            Parsed :class:`TestResult`.
        """
        result = TestResult(raw_output=output, framework="cargo", duration_ms=duration_ms)

        passed_count = len(re.findall(r"^test\s+\S+\s+\.\.\.\s+ok", output, re.MULTILINE))
        failed_count = len(re.findall(r"^test\s+\S+\s+\.\.\.\s+FAILED", output, re.MULTILINE))
        result.passed = passed_count
        result.failed = failed_count

        # Extract failure blocks.
        fail_blocks = re.findall(
            r"^failures:\n\n(.*?)(?=\nfailures:\n|$)",
            output,
            re.MULTILINE | re.DOTALL,
        )
        for block in fail_blocks:
            for line in block.splitlines():
                line = line.strip()
                if line and not line.startswith("----"):
                    # Try to get file:line from the panic location.
                    loc_match = re.search(r"(\S+\.rs):(\d+):(\d+)", block)
                    file_path = loc_match.group(1) if loc_match else ""
                    line_num = int(loc_match.group(2)) if loc_match else 0
                    result.failures.append(
                        Failure(
                            test_name=line,
                            file=file_path,
                            line=line_num,
                            message=block.strip()[:500],
                            traceback=block.strip(),
                        )
                    )
                    break

        return result

    def __repr__(self) -> str:
        """Return a developer-friendly representation."""
        return f"<{type(self).__name__} timeout={self.timeout_seconds}s>"

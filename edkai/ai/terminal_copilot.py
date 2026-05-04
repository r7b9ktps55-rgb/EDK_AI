"""Terminal AI Copilot for Terminal Studio.

Analyzes terminal output and suggests fixes/explanations using the
:class:`AIClient`.
"""

from __future__ import annotations
from typing import Optional

from edkai.ai.client import AIClient


class TerminalCopilot:
    """Analyzes terminal output and suggests fixes/explanations.

    Wraps the :class:`AIClient` with terminal-specific prompts for
    error explanation, command suggestion, and command explanation.

    Attributes:
        client: The AI client used to generate responses.
    """

    def __init__(self, client: AIClient) -> None:
        """Initialise the copilot with an AI client.

        Args:
            client: An initialised :class:`AIClient`.
        """
        self.client = client

    async def explain_error(self, output: str, command: str) -> str:
        """Explain why a command failed in human-readable terms.

        Args:
            output: The combined stdout/stderr output (or error text).
            command: The command that was executed.

        Returns:
            A concise explanation of what went wrong.
        """
        prompt = (
            "You are a helpful terminal assistant. A command failed.\n\n"
            f"Command: `{command}`\n\n"
            f"Output:\n```\n{output}\n```\n\n"
            "Explain what went wrong in simple terms. "
            "Include the likely root cause and how to fix it."
        )
        return await self.client.complete(
            prompt,
            temperature=0.3,
            max_tokens=512,
        )

    async def suggest_fix(self, output: str, command: str, cwd: str) -> Optional[str]:
        """Suggest a corrected command or steps to fix the failure.

        Args:
            output: The combined stdout/stderr output.
            command: The command that was executed.
            cwd: The working directory where the command ran.

        Returns:
            A corrected command string or step-by-step fix instructions,
            or ``None`` if no fix is applicable.
        """
        prompt = (
            "You are a helpful terminal assistant. A command failed.\n\n"
            f"Working directory: {cwd}\n"
            f"Command: `{command}`\n\n"
            f"Output:\n```\n{output}\n```\n\n"
            "Suggest a corrected command or concise steps to fix the issue. "
            "If a single corrected command is enough, respond with ONLY that command. "
            "If multiple steps are needed, list them briefly. "
            "If no fix is applicable, reply with the literal word: NONE"
        )
        result = await self.client.complete(
            prompt,
            temperature=0.2,
            max_tokens=512,
        )
        result = result.strip()
        if result == "NONE":
            return None
        # Extract command if wrapped in backticks.
        if result.startswith("`") and result.endswith("`"):
            result = result[1:-1]
        return result

    async def suggest_command(self, task: str, cwd: str) -> str:
        """Convert a natural language task into a shell command.

        Args:
            task: A natural language description of what the user wants,
                e.g. ``"find all python files modified today"``.
            cwd: The current working directory.

        Returns:
            A shell command string that fulfills the task.
        """
        prompt = (
            "You are a helpful terminal assistant. "
            "Convert the following task into a single shell command.\n\n"
            f"Working directory: {cwd}\n"
            f"Task: {task}\n\n"
            "Respond with ONLY the shell command, nothing else. "
            "Make it safe, portable, and idiomatic."
        )
        result = await self.client.complete(
            prompt,
            temperature=0.2,
            max_tokens=256,
        )
        return result.strip()

    async def explain_command(self, command: str) -> str:
        """Explain what a shell command does in simple terms.

        Args:
            command: The shell command to explain.

        Returns:
            A human-readable explanation of the command.
        """
        prompt = (
            "You are a helpful terminal assistant. Explain the following shell command\n"
            "in simple, concise terms suitable for a developer.\n\n"
            f"Command: `{command}`\n\n"
            "Break down each flag and argument."
        )
        return await self.client.complete(
            prompt,
            temperature=0.3,
            max_tokens=512,
        )

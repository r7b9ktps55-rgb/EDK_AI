"""Async REPL for the Terminal Studio Agent.

Provides an interactive command-line interface where the user can chat with
the agent, issue built-in slash-commands, and supply multi-line input.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from edkai.agent.nl_router import NLRouter, get_help_text

if TYPE_CHECKING:
    from edkai.agent.orchestrator import AgentOrchestrator


class AgentREPL:
    """Terminal REPL for the AI agent."""

    def __init__(self, orchestrator: AgentOrchestrator) -> None:
        self.orchestrator = orchestrator
        self._nl_router = NLRouter(str(orchestrator.project_root))
        self._current_file: str | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self, initial_prompt: str | None = None) -> None:
        """Enter the read-eval-print loop.

        Parameters
        ----------
        initial_prompt:
            An optional first user message that is processed *before* the
            interactive prompt is shown.
        """
        self._print_banner()

        if initial_prompt:
            print(f"> {initial_prompt}")
            async for chunk in self.orchestrator.process_message(initial_prompt):
                print(chunk, end="", flush=True)
            print("\n")

        while True:
            try:
                user_input = await self._get_input("> ")
                cmd = user_input.lower().strip()

                if cmd in ("/exit", "/quit", "quit", "exit"):
                    print("Goodbye!")
                    break

                if cmd == "/reset":
                    self.orchestrator.history.clear()
                    print("Conversation reset.")
                    continue

                if cmd in ("/help", "help"):
                    print(get_help_text())
                    continue

                if not user_input.strip():
                    continue

                # Try NL router for quick pattern matches before orchestrator
                nl_result = self._nl_router.parse(user_input, {"current_file": self._current_file or "unknown"})
                if nl_result and nl_result.confidence >= 0.9:
                    print(f"\n{nl_result.explanation}")
                    result = await self.orchestrator._execute_tool(nl_result.tool, nl_result.args)
                    print(f"{result.output}")
                    if result.error:
                        print(f"Error: {result.error}")
                    continue

                # Normal message — stream the response
                async for chunk in self.orchestrator.process_message(user_input):
                    print(chunk, end="", flush=True)
                print("\n")

            except KeyboardInterrupt:
                print("\nUse /exit to quit.")
            except EOFError:
                break

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _print_banner(self) -> None:
        print("╔══════════════════════════════════════════════════════════╗")
        print("║  Terminal Studio Agent v5 — AI Code Agent              ║")
        print("║  Type 'help' for available NL commands                 ║")
        print("╚══════════════════════════════════════════════════════════╝")
        print("")

    async def _get_input(self, prompt: str) -> str:
        """Get user input supporting simple multi-line entry.

        A trailing back-slash (``\\``) at the end of a line continues input
        on the next line.
        """
        lines: list[str] = []
        loop = asyncio.get_event_loop()

        while True:
            current_prompt = prompt if not lines else "... "
            # ``input`` is blocking so run it in the default executor
            line = await loop.run_in_executor(None, input, current_prompt)
            if line.endswith("\\"):
                lines.append(line[:-1])
            else:
                lines.append(line)
                break

        return "\n".join(lines)

    @staticmethod
    def _print_help() -> None:
        print(
            """Commands:
  /exit, /quit  - Exit agent
  /reset        - Clear conversation history
  /help         - Show this help

I can:
  - Read and write files
  - Run shell commands
  - Search your codebase
  - Help with git operations
  - Explain, refactor, and optimize code

Natural language commands are also supported. Type 'help' for a list.
"""
        )

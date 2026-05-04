"""Agent orchestrator — conversation loop with tool-use support.

The ``AgentOrchestrator`` class manages the full lifecycle of an agent turn:

1. Build a system prompt that describes available tools.
2. Gather project context (file tree, key files, git status).
3. Stream the LLM response to the user.
4. Parse XML-style ``<tool>…</tool>`` blocks from the response.
5. Execute each requested tool and feed results back for a follow-up turn.

All public methods are async and designed to work with the ``AgentREPL``.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, Protocol

from edkai.agent.context import ProjectContext
from edkai.agent.nl_router import NLRouter
from edkai.core.repo_map import RepoMap
from edkai.core.checkpoint import CheckpointManager
from edkai.agent.multi_edit import MultiEditEngine
from edkai.agent.diff_engine import DiffEngine
from edkai.agent.tools import ToolRegistry, ToolResult


# Minimal Protocol for the AI client so the orchestrator stays decoupled.
class AIClient(Protocol):
    """Anything that can stream chat completions."""

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        stream: bool = True,
    ) -> AsyncGenerator[str, None]:
        ...


class AgentOrchestrator:
    """Orchestrates the agent conversation loop."""

    SYSTEM_PROMPT_TEMPLATE = """You are Terminal Studio Agent, an expert software engineering AI.
You help users by reading files, running commands, searching code, and making changes.
You work in the project directory and have access to the following tools:

{tool_descriptions}

## How to use tools
When you need to use a tool, use this exact XML format:
<tool>tool_name</tool>
<args>
{{
  "param_name": "value"
}}
</args>

You can use multiple tools in sequence. After each tool result, decide if you need more tools or can provide the final answer.
When you're done, provide a clear, concise final response summarizing what you did.

Rules:
- Always check files before modifying them
- Prefer surgical edits (EditFile) over full rewrites (WriteFile)
- Run tests after making changes
- Ask the user if unsure about destructive operations
- Be concise in your final response
## Multi-File Editing Format
When editing files, use this exact format for EACH change:
File: path/to/file.py
<<<<<<< SEARCH
old code (exact match, 3-5 lines context)
=======
new code
>>>>>>> REPLACE

Rules:
- SEARCH must match EXACTLY one place
- Include 3-5 lines of context for uniqueness
- Can make multiple changes — one block per change

"""

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        ai_client: AIClient,
        project_root: str | Path,
        config: Any | None = None,
    ) -> None:
        self.ai_client = ai_client
        self.project_root = Path(project_root).resolve()
        self.config = config
        self.tools = ToolRegistry()
        self.context = ProjectContext(self.project_root)
        self.history: list[dict[str, str]] = []
        self.max_iterations: int = (
            getattr(config, "agent_max_iterations", 25) if config else 25
        )
        self._nl_router = NLRouter(str(self.project_root))
        self._context: dict[str, Any] = {"project_root": str(self.project_root)}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, initial_prompt: str | None = None) -> None:
        """Initialise the conversation and optionally process a first prompt.

        This method is used when the orchestrator is *not* driven by the REPL
        (e.g. a single-shot execution).  In REPL mode the REPL calls
        ``process_message`` directly.
        """
        # Build system prompt
        tool_desc = self.tools.to_prompt()
        system_prompt = self.SYSTEM_PROMPT_TEMPLATE.format(tool_descriptions=tool_desc)

        # Build project context
        project_ctx = await self.context.build_context()

        # Initialise conversation
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Here's the project context:\n{project_ctx}\n\n"
                    "Start working on my requests."
                ),
            },
        ]

        if initial_prompt:
            messages.append({"role": "user", "content": initial_prompt})
            await self._process_turn(messages)

    async def process_message(self, user_message: str) -> AsyncGenerator[str, None]:
        """Process a user message and yield response chunks.

        The conversation *history* is prepended so the LLM maintains context.
        After the initial response any embedded tool calls are executed and
        their results are fed back for a follow-up LLM turn.
        """
        # Try NL routing first — fast regex patterns for common commands
        nl_result = self._nl_router.parse(user_message, self._context)
        if nl_result and nl_result.confidence >= 0.9:
            yield f"\n{nl_result.explanation}\n"
            result = await self._execute_tool(nl_result.tool, nl_result.args)
            yield f"{result.output}\n"
            if result.error:
                yield f"Error: {result.error}\n"
            return

        messages: list[dict[str, str]] = list(self.history)
        messages.append({"role": "user", "content": user_message})

        # ---- First LLM turn ----
        full_response = ""
        async for chunk in self.ai_client.chat(messages, stream=True):
            full_response += chunk
            yield chunk

        # ---- Parse & execute tools ----
        tool_calls = self._parse_tool_calls(full_response)
        if tool_calls:
            results: list[str] = []
            for tool_name, args in tool_calls:
                result = await self._execute_tool(tool_name, args)
                results.append(f"Tool: {tool_name}\nResult:\n{result.output}")
                if result.error:
                    results.append(f"Error: {result.error}")

            # Inject tool results as a new user message and get follow-up
            tool_result_msg = "\n\n".join(results)
            messages.append({"role": "assistant", "content": full_response})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Tool results:\n{tool_result_msg}\n\n"
                        "Please continue or provide your final answer."
                    ),
                }
            )

            async for chunk in self.ai_client.chat(messages, stream=True):
                yield chunk

            # Persist history (last 20 messages to stay within context limits)
            self.history = messages[-20:]
        else:
            # No tools used — persist the exchange
            messages.append({"role": "assistant", "content": full_response})
            self.history = messages[-20:]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _process_turn(self, messages: list[dict[str, str]]) -> None:
        """Run a full turn: LLM call + optional tool execution loop.

        Used by ``run`` when operating outside the REPL.  Output is printed
        directly to stdout.
        """
        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1

            # Collect full response
            full_response = ""
            async for chunk in self.ai_client.chat(messages, stream=True):
                full_response += chunk
                print(chunk, end="", flush=True)
            print()

            # Parse and execute tools
            tool_calls = self._parse_tool_calls(full_response)
            if not tool_calls:
                break

            results: list[str] = []
            for tool_name, args in tool_calls:
                result = await self._execute_tool(tool_name, args)
                results.append(f"Tool: {tool_name}\nResult:\n{result.output}")
                if result.error:
                    results.append(f"Error: {result.error}")

            tool_result_msg = "\n\n".join(results)
            messages.append({"role": "assistant", "content": full_response})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Tool results:\n{tool_result_msg}\n\n"
                        "Please continue or provide your final answer."
                    ),
                }
            )

    @staticmethod
    def _parse_tool_calls(response: str) -> list[tuple[str, dict[str, Any]]]:
        """Parse XML-style tool calls from the LLM response.

        Expected format::

            <tool>tool_name</tool>
            <args>
            {
              "param_name": "value"
            }
            </args>
        """
        pattern = r"<tool>(\w+)</tool>\s*<args>(.*?)</args>"
        matches = re.findall(pattern, response, re.DOTALL)
        result: list[tuple[str, dict[str, Any]]] = []
        for name, args_str in matches:
            try:
                args = json.loads(args_str.strip())
                result.append((name, args))
            except json.JSONDecodeError:
                # Malformed JSON — silently skip so the LLM can recover
                pass
        return result

    async def _execute_tool(self, name: str, args: dict[str, Any]) -> ToolResult:
        """Look up a tool and execute it with the given arguments."""
        tool = self.tools.get_tool(name)
        if tool is None:
            return ToolResult(output="", error=f"Unknown tool: {name}", is_error=True)

        try:
            # Inject project_root for path-based tools
            if hasattr(tool, "project_root"):
                tool.project_root = self.project_root
            return await tool.execute(**args)
        except Exception as exc:
            return ToolResult(output="", error=str(exc), is_error=True)

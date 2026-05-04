"""Agent engine for EDK_AI — AI Code Agent."""
from edkai.agent.tools import ToolRegistry, ToolResult, BaseTool
from edkai.agent.context import ProjectContext
from edkai.agent.context_v2 import ContextEngine
from edkai.agent.orchestrator import AgentOrchestrator
from edkai.agent.repl import AgentREPL
from edkai.agent.nl_router import NLRouter, ToolCall
from edkai.agent.multi_edit import MultiEditEngine, EditBlock, ApplyResult
from edkai.agent.diff_engine import DiffEngine
from edkai.agent.parallel import ParallelExecutor
from edkai.agent.summarizer import ConversationSummarizer

__all__ = [
    "ToolRegistry",
    "ToolResult",
    "BaseTool",
    "ProjectContext",
    "ContextEngine",
    "AgentOrchestrator",
    "AgentREPL",
    "NLRouter",
    "ToolCall",
    "MultiEditEngine",
    "EditBlock",
    "ApplyResult",
    "DiffEngine",
    "ParallelExecutor",
    "ConversationSummarizer",
]

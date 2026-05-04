"""TUI widgets for EDK_AI."""
from edkai.widgets.ai_panel import AIPanel
from edkai.widgets.agent_panel import AgentPanel
from edkai.widgets.editor import Editor
from edkai.widgets.file_tree import FileTree
from edkai.widgets.ghost_overlay import GhostOverlay
from edkai.widgets.ai_terminal import AITerminalPanel
from edkai.widgets.git_panel import GitPanel
from edkai.widgets.nl_palette import NLPalette
from edkai.widgets.search_panel import SearchPanel
from edkai.widgets.snippet_bar import SnippetBar
from edkai.widgets.status_bar import StatusBar
from edkai.widgets.terminal import TerminalPanel
from edkai.widgets.test_panel import TestPanel
from edkai.widgets.diff_viewer import DiffViewer
from edkai.widgets.project_dashboard import ProjectDashboard
from edkai.widgets.typing_indicator import TypingIndicator

__all__ = [
    "AIPanel",
    "AgentPanel",
    "Editor",
    "FileTree",
    "GhostOverlay",
    "AITerminalPanel",
    "GitPanel",
    "NLPalette",
    "SearchPanel",
    "SnippetBar",
    "StatusBar",
    "TerminalPanel",
    "TestPanel",
    "DiffViewer",
    "ProjectDashboard",
    "TypingIndicator",
]

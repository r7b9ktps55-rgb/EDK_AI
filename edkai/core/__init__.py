"""Terminal Studio core modules."""

from __future__ import annotations

from edkai.core.config import StudioConfig
from edkai.core.project import Project
from edkai.core.runner import CodeRunner
from edkai.core.snippets import SnippetEngine
from edkai.core.macros import Macro, MacroRecorder
from edkai.core.templates import TemplateManager
from edkai.core.auto_fix import AutoFixEngine
from edkai.core.test_runner import TestRunner, TestResult, Failure
from edkai.core.fuzzy_search import FuzzySearcher, SearchResult, ContentResult
from edkai.core.symbols import SymbolExtractor, Symbol
from edkai.core.git_manager import GitManager, GitStatus, BlameInfo, CommitInfo

__all__ = [
    "StudioConfig",
    "Project",
    "CodeRunner",
    "SnippetEngine",
    "Macro",
    "MacroRecorder",
    "TemplateManager",
    "AutoFixEngine",
    "TestRunner",
    "TestResult",
    "Failure",
    "FuzzySearcher",
    "SearchResult",
    "ContentResult",
    "SymbolExtractor",
    "Symbol",
    "GitManager",
    "GitStatus",
    "BlameInfo",
    "CommitInfo",
]

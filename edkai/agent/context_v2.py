"""5-layer Context Engine for EDK_AI.

Builds rich context for AI by combining multiple information sources:
1. EDK_AI.md — project-specific instructions
2. Repo Map — tree-sitter symbol overview
3. Key Files — README, config files
4. Git Status — recent changes
5. Active Files — recently used files

Inspired by Claude Code's context building.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from edkai.core.repo_map import RepoMap


@dataclass
class ContextLayer:
    """A single layer of context."""
    name: str
    content: str
    priority: int = 0  # Higher = more important
    estimated_tokens: int = 0


class ContextEngine:
    """Builds AI context from multiple sources."""
    
    # Files considered "key" for context
    KEY_FILES = [
        "README.md", "README.rst", "README",
        "pyproject.toml", "setup.py", "setup.cfg",
        "package.json", "Cargo.toml", "go.mod",
        "requirements.txt", "Pipfile", "poetry.lock",
        "Dockerfile", "docker-compose.yml",
        "Makefile", "justfile",
        ".editorconfig", ".gitignore",
        "tox.ini", "pytest.ini",
    ]
    
    def __init__(self, project_root: Path | str) -> None:
        self.root = Path(project_root).resolve()
        self.repo_map = RepoMap(self.root)
        self._edkai_md: dict[str, str] | None = None
        self._context_cache: str | None = None
        self._cache_time: float = 0
    
    async def build_context(self, max_chars: int = 12000) -> str:
        """Build full context from all layers.
        
        Layers are combined in priority order, truncated to fit max_chars.
        """
        layers = await self._build_layers()
        
        # Sort by priority (highest first)
        layers.sort(key=lambda l: l.priority, reverse=True)
        
        # Combine until we hit the limit
        parts: list[str] = []
        total = 0
        
        for layer in layers:
            if total + len(layer.content) > max_chars:
                # Truncate this layer if possible
                remaining = max_chars - total
                if remaining > 200:
                    truncated = layer.content[:remaining] + "\n... (truncated)"
                    parts.append(self._format_layer(layer.name, truncated))
                    total += len(truncated)
                break
            
            parts.append(self._format_layer(layer.name, layer.content))
            total += len(layer.content)
        
        return "\n\n".join(parts)
    
    async def _build_layers(self) -> list[ContextLayer]:
        """Build all context layers."""
        layers: list[ContextLayer] = []
        
        # Layer 1: EDK_AI.md (highest priority — user instructions)
        edkai_layer = self._layer_edkai_md()
        if edkai_layer:
            layers.append(edkai_layer)
        
        # Layer 2: Repo Map
        layers.append(await self._layer_repo_map())
        
        # Layer 3: Key Files
        key_files_layer = self._layer_key_files()
        if key_files_layer:
            layers.append(key_files_layer)
        
        # Layer 4: Git Status
        git_layer = self._layer_git_status()
        if git_layer:
            layers.append(git_layer)
        
        # Layer 5: Active/Recent Files
        active_layer = self._layer_active_files()
        if active_layer:
            layers.append(active_layer)
        
        return layers
    
    def _layer_edkai_md(self) -> ContextLayer | None:
        """Parse EDK_AI.md if it exists."""
        edkai_md_path = self.root / "EDK_AI.md"
        if not edkai_md_path.exists():
            return None
        
        try:
            content = edkai_md_path.read_text(encoding="utf-8", errors="replace")
            if not content.strip():
                return None
            
            return ContextLayer(
                name="📋 Project Instructions (EDK_AI.md)",
                content=content[:4000],
                priority=100,  # Highest priority
                estimated_tokens=len(content) // 4,
            )
        except (OSError, UnicodeDecodeError):
            return None
    
    async def _layer_repo_map(self) -> ContextLayer:
        """Build repo map layer."""
        if not self.repo_map.is_built():
            await self.repo_map.build_map()
        
        map_text = self.repo_map.get_map_text(max_files=80)
        
        return ContextLayer(
            name="🗺️ Code Map",
            content=map_text,
            priority=80,
            estimated_tokens=len(map_text) // 4,
        )
    
    def _layer_key_files(self) -> ContextLayer | None:
        """Read key configuration files."""
        contents: list[str] = []
        
        for fname in self.KEY_FILES:
            fpath = self.root / fname
            if fpath.exists():
                try:
                    text = fpath.read_text(encoding="utf-8", errors="replace")
                    # Truncate large files
                    if len(text) > 2000:
                        text = text[:2000] + "\n... (truncated)"
                    contents.append(f"### {fname}\n{text}")
                except (OSError, UnicodeDecodeError):
                    pass
        
        if not contents:
            return None
        
        full = "\n\n".join(contents)
        return ContextLayer(
            name="📁 Key Files",
            content=full,
            priority=60,
            estimated_tokens=len(full) // 4,
        )
    
    def _layer_git_status(self) -> ContextLayer | None:
        """Get git status and recent commits."""
        if not (self.root / ".git").exists():
            return None
        
        parts: list[str] = []
        
        # Status
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=self.root, capture_output=True, text=True, timeout=10,
        )
        if result.stdout.strip():
            parts.append("## Modified Files\n" + result.stdout.strip())
        
        # Recent commits
        result = subprocess.run(
            ["git", "log", "--oneline", "-10", "--graph"],
            cwd=self.root, capture_output=True, text=True, timeout=10,
        )
        if result.stdout.strip():
            parts.append("## Recent Commits\n" + result.stdout.strip())
        
        # Branch
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=self.root, capture_output=True, text=True, timeout=10,
        )
        branch = result.stdout.strip()
        if branch:
            parts.insert(0, f"## Branch: {branch}")
        
        if not parts:
            return None
        
        full = "\n\n".join(parts)
        return ContextLayer(
            name="🌿 Git Status",
            content=full,
            priority=40,
            estimated_tokens=len(full) // 4,
        )
    
    def _layer_active_files(self) -> ContextLayer | None:
        """Recently modified files (via git)."""
        if not (self.root / ".git").exists():
            return None
        
        # Get files modified in last 10 commits
        result = subprocess.run(
            ["git", "diff", "HEAD~10", "--name-only"],
            cwd=self.root, capture_output=True, text=True, timeout=10,
        )
        
        files = result.stdout.strip().split("\n")
        files = [f for f in files if f and not f.startswith(".")]
        
        if not files:
            return None
        
        content = "## Recently Modified\n" + "\n".join(f"- {f}" for f in files[:20])
        
        return ContextLayer(
            name="📝 Active Files",
            content=content,
            priority=30,
            estimated_tokens=len(content) // 4,
        )
    
    @staticmethod
    def _format_layer(name: str, content: str) -> str:
        """Format a layer with header."""
        separator = "=" * 50
        return f"{separator}\n# {name}\n{separator}\n{content}"
    
    def get_edkai_md_template(self) -> str:
        """Return a template for EDK_AI.md."""
        return '''# EDK_AI Project Instructions

## Project Overview
<!-- Brief description of what this project does -->

## Tech Stack
<!-- Languages, frameworks, databases -->

## Architecture
<!-- Key directories and their purposes -->

## Coding Conventions
<!-- Style guide, naming conventions -->

## Important Rules
<!-- Things AI should NEVER do -->
- 

## Common Commands
<!-- How to run, test, build -->
- Run: 
- Test: 
- Lint: 

## Dependencies
<!-- Key external libraries -->
'''

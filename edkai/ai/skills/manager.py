"""Skill management system inspired by gstack.

Each skill is a self-contained module with SKILL.md, prompts.py, and optional handler.py.
Skills are discovered automatically from built-in and user directories.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SkillInfo:
    name: str
    description: str
    triggers: list[str]
    path: Path


@dataclass
class SkillResult:
    prompt: str
    context: dict[str, Any] = field(default_factory=dict)


class BaseSkill(ABC):
    """Base class for all skills."""

    name: str = ""
    description: str = ""
    triggers: list[str] = field(default_factory=list)

    @abstractmethod
    def build_prompt(self, user_input: str, context: dict[str, Any]) -> SkillResult:
        """Build a prompt for this skill based on user input."""
        ...


class BuiltinSkill(BaseSkill):
    """A skill loaded from the built-in skills directory."""

    def __init__(self, info: SkillInfo, prompts_module: Any):
        self.info = info
        self.name = info.name
        self.description = info.description
        self.triggers = info.triggers
        self._prompts = prompts_module

    def build_prompt(self, user_input: str, context: dict[str, Any]) -> SkillResult:
        """Delegate to the skill's prompt builder if available."""
        if hasattr(self._prompts, "build_prompt"):
            result = self._prompts.build_prompt(user_input, context)
            if isinstance(result, SkillResult):
                return result
            elif isinstance(result, str):
                return SkillResult(prompt=result, context=context)
        # Generic fallback
        return SkillResult(
            prompt=f"{self.description}\n\nUser request: {user_input}",
            context=context,
        )


class SkillManager:
    """Discovers and manages skills."""

    BUILTIN_DIR = Path(__file__).parent
    USER_SKILLS_DIR = Path.home() / ".config" / "edkai" / "skills"

    def __init__(self):
        self._skills: dict[str, BaseSkill] = {}
        self._discover_builtin()
        self._discover_user()

    def _discover_builtin(self) -> None:
        """Scan built-in skills directory."""
        if not self.BUILTIN_DIR.exists():
            return
        for item in self.BUILTIN_DIR.iterdir():
            if item.is_dir() and not item.name.startswith("_"):
                self._load_skill_from_dir(item)

    def _discover_user(self) -> None:
        """Scan user skills directory."""
        if not self.USER_SKILLS_DIR.exists():
            return
        for item in self.USER_SKILLS_DIR.iterdir():
            if item.is_dir() and not item.name.startswith("_"):
                self._load_skill_from_dir(item)

    def _load_skill_from_dir(self, path: Path) -> None:
        """Load a skill from a directory containing SKILL.md."""
        skill_md = path / "SKILL.md"
        if not skill_md.exists():
            return

        # Parse SKILL.md for triggers and description
        content = skill_md.read_text(encoding="utf-8")
        name = path.name
        description = ""
        triggers: list[str] = []

        in_triggers = False
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("## Description"):
                continue
            elif line.startswith("## Triggers") or line.startswith("### Triggers"):
                in_triggers = True
                continue
            elif line.startswith("## ") or line.startswith("# "):
                in_triggers = False

            if in_triggers and line.startswith("-"):
                trigger = line.lstrip("- ").strip()
                if trigger:
                    triggers.append(trigger.lower())
            elif not description and line and not line.startswith("#"):
                description = line

        info = SkillInfo(
            name=name, description=description, triggers=triggers, path=path
        )

        # Load prompts module if exists
        prompts = None
        prompts_path = path / "prompts.py"
        if prompts_path.exists():
            try:
                import importlib.util

                spec = importlib.util.spec_from_file_location(
                    f"skill_{name}_prompts", prompts_path
                )
                if spec and spec.loader:
                    prompts = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(prompts)
            except Exception:
                pass

        self._skills[name] = BuiltinSkill(info, prompts)

    @property
    def all_skills(self) -> list[SkillInfo]:
        """List all available skills."""
        return [s.info for s in self._skills.values()]

    def find_skill(self, user_input: str) -> BaseSkill | None:
        """Find best matching skill by trigger keywords."""
        user_lower = user_input.lower()
        best_score = 0
        best_skill = None

        for skill in self._skills.values():
            score = 0
            for trigger in skill.triggers:
                if trigger in user_lower:
                    # Exact match scores higher
                    if trigger == user_lower.strip():
                        score += 10
                    elif f" {trigger} " in f" {user_lower} ":
                        score += 5
                    else:
                        score += 1
            if score > best_score:
                best_score = score
                best_skill = skill

        return best_skill

    def get_skill(self, name: str) -> BaseSkill | None:
        """Get skill by exact name."""
        return self._skills.get(name)

    def get_system_prompt_addon(self) -> str:
        """Generate system prompt section listing skills."""
        lines = [
            "## Available Skills",
            "You can use these skills by mentioning their trigger words:",
            "",
        ]
        for info in self.all_skills:
            triggers_str = '", "'.join(info.triggers[:5])
            lines.append(
                f'- **{info.name}**: "{triggers_str}" \u2014 {info.description[:80]}'
            )
        return "\n".join(lines)

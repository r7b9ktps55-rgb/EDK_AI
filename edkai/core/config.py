"""Terminal Studio v5 configuration — multi-provider AI system."""
from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# ProviderConfig
# ---------------------------------------------------------------------------

class ProviderConfig(BaseModel):
    """Configuration for a single AI provider.

    Attributes:
        name: Machine-friendly provider identifier (e.g., ``"github_models"``).
        enabled: Whether the provider is active.
        api_key: API key for authentication (falls back to env var).
        base_url: Provider's base API URL.
        default_model: Default model to use when none is specified.
    """

    name: str
    enabled: bool = True
    api_key: str = ""
    base_url: str = ""
    default_model: str = ""


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

def _default_providers() -> list[ProviderConfig]:
    """Return the built-in default provider list.

    The order matters: providers are tried in this sequence when
    ``active_provider == "auto"``.
    """
    return [
        ProviderConfig(
            name="github_models",
            enabled=True,
            base_url="https://models.inference.ai.azure.com",
            default_model="phi-4",
        ),
        ProviderConfig(
            name="ollama",
            enabled=True,
            base_url="http://localhost:11434",
            default_model="qwen2.5-coder:14b",
        ),
        ProviderConfig(
            name="gemini",
            enabled=True,
            base_url="https://generativelanguage.googleapis.com/v1beta",
            default_model="gemini-2.0-flash-lite",
        ),
        ProviderConfig(
            name="openai_compat",
            enabled=True,
            base_url="https://api.openai.com/v1",
            default_model="gpt-4o-mini",
        ),
    ]


# ---------------------------------------------------------------------------
# StudioConfig
# ---------------------------------------------------------------------------

class StudioConfig(BaseModel):
    """Top-level configuration for Terminal Studio.

    Attributes:
        theme: UI theme name (``"dark"`` | ``"light"``).
        providers: List of AI provider configurations.
        active_provider: Name of the currently active provider or ``"auto"``.
        agent_max_iterations: Maximum loop iterations per agent session.
        agent_auto_confirm: Whether to auto-confirm low-risk agent actions.
    """

    theme: str = "dark"
    providers: list[ProviderConfig] = Field(default_factory=_default_providers)
    active_provider: str = "auto"
    agent_max_iterations: int = 25
    agent_auto_confirm: bool = False

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, path: str | os.PathLike[str] | None = None) -> "StudioConfig":
        """Load configuration from disk.

        Args:
            path: Explicit config file path.  When ``None``, the default
                ``~/.config/edkai/config.json`` is used.

        Returns:
            A :class:`StudioConfig` instance — either loaded from disk or
            the built-in defaults when the file is missing / corrupt.
        """
        config_path = path or (Path.home() / ".config" / "edkai" / "config.json")
        config_path = Path(config_path)

        if not config_path.exists():
            return cls()

        try:
            with open(config_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return cls.model_validate(data)
        except (json.JSONDecodeError, OSError, ValueError):
            return cls()

    def save(self, path: str | os.PathLike[str] | None = None) -> None:
        """Persist configuration to disk.

        Args:
            path: Explicit config file path.  When ``None``, the default
                ``~/.config/edkai/config.json`` is used.
        """
        config_path = path or (Path.home() / ".config" / "edkai" / "config.json")
        config_path = Path(config_path)
        config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(config_path, "w", encoding="utf-8") as fh:
            json.dump(self.model_dump(), fh, indent=2)

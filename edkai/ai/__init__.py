"""Terminal Studio AI layer -- multi-provider client system.

Provides a unified interface to multiple AI inference backends:
GitHub Models, Ollama (local), Google Gemini, and generic OpenAI-compatible
endpoints.  The :class:`~edkai.ai.client.AIClient` delegates to a
:class:`~edkai.ai.providers.base.BaseProvider` implementation, while
:class:`~edkai.ai.providers.ProviderRegistry` manages provider discovery
from configuration.
"""
from edkai.ai.client import AIClient
from edkai.ai.providers.base import BaseProvider
from edkai.ai.providers.fallback import AutoFallbackProvider
from edkai.ai.providers.gemini import GeminiProvider
from edkai.ai.providers.github_models import GitHubModelsProvider
from edkai.ai.providers.ollama import OllamaProvider
from edkai.ai.providers.openai_compat import OpenAICompatibleProvider
from edkai.ai.providers import ProviderRegistry

__all__ = [
    "AIClient",
    "AutoFallbackProvider",
    "BaseProvider",
    "GitHubModelsProvider",
    "OllamaProvider",
    "GeminiProvider",
    "OpenAICompatibleProvider",
    "ProviderRegistry",
]

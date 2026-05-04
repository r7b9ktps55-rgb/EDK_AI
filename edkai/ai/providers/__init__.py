"""Provider registry and factory.

The :class:`ProviderRegistry` inspects a :class:`~edkai.core.config.StudioConfig`
and instantiates the appropriate :class:`BaseProvider` subclass for each
enabled entry.  It then serves as the lookup mechanism for the rest of the
application via ``get_provider("auto")`` → first configured provider.
"""
from __future__ import annotations

from edkai.ai.exceptions import AIError
from edkai.ai.providers.base import BaseProvider
from edkai.ai.providers.fallback import AutoFallbackProvider
from edkai.ai.providers.gemini import GeminiProvider
from edkai.ai.providers.github_models import GitHubModelsProvider
from edkai.ai.providers.ollama import OllamaProvider
from edkai.ai.providers.openai_compat import OpenAICompatibleProvider
from edkai.core.config import ProviderConfig, StudioConfig


# ---------------------------------------------------------------------------
# ProviderRegistry
# ---------------------------------------------------------------------------

class ProviderRegistry:
    """Registry that creates and manages AI provider instances from config.

    Iterates over the ``providers`` list in :class:`~edkai.core.config.StudioConfig`,
    instantiates the matching :class:`BaseProvider` for each enabled entry,
    and exposes lookup methods.

    Args:
        config: The studio configuration to build providers from.
    """

    def __init__(self, config: StudioConfig) -> None:
        self._providers: dict[str, BaseProvider] = {}
        for pc in config.providers:
            if not pc.enabled:
                continue
            provider = self._create_provider(pc)
            if provider is not None:
                self._providers[provider.name] = provider

    # -- factory ---------------------------------------------------------

    def _create_provider(self, pc: ProviderConfig) -> BaseProvider | None:
        """Instantiate the correct provider class from a config entry.

        Args:
            pc: A single provider configuration.

        Returns:
            The instantiated provider, or ``None`` if the name is unknown.
        """
        name = pc.name.lower()

        if name == "github_models":
            return GitHubModelsProvider(
                api_key=pc.api_key or None,
                base_url=pc.base_url or None,
                default_model=pc.default_model or None,
            )

        if name == "ollama":
            return OllamaProvider(
                base_url=pc.base_url or None,
                default_model=pc.default_model or None,
            )

        if name == "gemini":
            return GeminiProvider(
                api_key=pc.api_key or None,
                base_url=pc.base_url or None,
                default_model=pc.default_model or None,
            )

        if name in ("openai_compat", "openai"):
            return OpenAICompatibleProvider(
                api_key=pc.api_key or None,
                base_url=pc.base_url or None,
                default_model=pc.default_model or None,
            )

        # Unknown provider name -- silently skip.
        return None

    # -- accessors -------------------------------------------------------

    @property
    def providers(self) -> list[BaseProvider]:
        """All successfully created providers."""
        return list(self._providers.values())

    @property
    def default_provider(self) -> BaseProvider | None:
        """Return the first configured provider, or the first available."""
        for p in self.providers:
            if p.is_configured:
                return p
        return self.providers[0] if self.providers else None

    def get_provider(self, name: str) -> BaseProvider | None:
        """Look up a provider by name.

        The special name ``"auto"`` resolves to :pyattr:`default_provider`.

        Args:
            name: Provider name or ``"auto"``.

        Returns:
            The matching provider, or ``None``.
        """
        if name == "auto":
            return self.default_provider
        return self._providers.get(name)

    def get_client(self, provider_name: str = "auto") -> AIClient:
        """Create an :class:`~edkai.ai.client.AIClient` backed by a provider.

        When *provider_name* is ``"auto"`` and multiple providers are
        configured, the returned client uses :class:`AutoFallbackProvider`
        to cycle through them on failures.

        Args:
            provider_name: Provider name or ``"auto"``.

        Returns:
            A configured :class:`AIClient`.

        Raises:
            AIError: If the requested provider is not found.
        """
        from edkai.ai.client import AIClient

        if provider_name == "auto":
            configured = self.providers
            if len(configured) > 1:
                fallback = AutoFallbackProvider(configured)
                return AIClient(provider=fallback)
            # Single provider (or none) -- fall through to normal lookup

        provider = self.get_provider(provider_name)
        if not provider:
            raise AIError(f"No provider found for: {provider_name}")
        return AIClient(provider=provider)

"""AI client exceptions.

All exception classes live in this module so that both :mod:`edkai.ai.client`
and :mod:`edkai.ai.providers` can import them without creating circular
import dependencies.
"""


class AIError(Exception):
    """Base exception for all AI client errors."""


class AIAuthError(AIError):
    """Raised when authentication with an AI provider fails (HTTP 401 / 403)."""


class AIRateLimitError(AIError):
    """Raised when the AI provider rate limit is exceeded (HTTP 429)."""


class AINetworkError(AIError):
    """Raised when a network-level error occurs (DNS, timeout, connection reset)."""

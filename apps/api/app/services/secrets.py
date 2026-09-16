"""Secrets provider interface for secure credential management."""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class SecretsProvider(ABC):
    """Abstract interface for secrets retrieval."""

    @abstractmethod
    async def get_secret(self, ref: str) -> str | None:
        """Retrieve a secret by reference.

        Args:
            ref: Secret reference (e.g., env var name, Vault path, ARN)

        Returns:
            The secret value, or None if not found.
        """
        ...


class EnvironmentSecretsProvider(SecretsProvider):
    """Reads secrets from environment variables."""

    async def get_secret(self, ref: str) -> str | None:
        value = os.environ.get(ref)
        if value is None:
            logger.debug("Secret not found in environment: %s", ref)
        return value


# Default provider — can be swapped at startup
_default_provider: SecretsProvider | None = None


def get_secrets_provider() -> SecretsProvider:
    """Get the configured secrets provider."""
    global _default_provider
    if _default_provider is None:
        _default_provider = EnvironmentSecretsProvider()
    return _default_provider


def set_secrets_provider(provider: SecretsProvider) -> None:
    """Override the default secrets provider."""
    global _default_provider
    _default_provider = provider

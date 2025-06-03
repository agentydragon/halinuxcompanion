"""Base classes for secure secret storage backends."""

import logging
from abc import ABC, abstractmethod
from enum import Enum

from ..oauth import OAuthTokens

logger = logging.getLogger(__name__)


class SecretStorageBackend(str, Enum):
    """Available storage backends for secrets."""

    FILE = "file"
    LIBSECRET = "libsecret"


class SecretStorage(ABC):
    """Abstract base class for secret storage backends."""

    @property
    @abstractmethod
    def oauth_tokens(self) -> OAuthTokens | None:
        """Load OAuth tokens from storage."""

    @oauth_tokens.setter
    @abstractmethod
    def oauth_tokens(self, tokens: OAuthTokens) -> None:
        """Save OAuth tokens to storage."""

    @property
    @abstractmethod
    def long_lived_token(self) -> str | None:
        """Load long-lived access token from storage."""

    @long_lived_token.setter
    @abstractmethod
    def long_lived_token(self, token: str) -> None:
        """Save long-lived access token to storage."""

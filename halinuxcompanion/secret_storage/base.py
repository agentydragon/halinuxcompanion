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

    @abstractmethod
    def load_oauth_tokens(self) -> OAuthTokens | None:
        """Load OAuth tokens from storage."""

    @abstractmethod
    def save_oauth_tokens(self, tokens: OAuthTokens) -> None:
        """Save OAuth tokens to storage."""

    @abstractmethod
    def delete_oauth_tokens(self) -> None:
        """Delete OAuth tokens from storage."""

    @abstractmethod
    def load_long_lived_token(self) -> str | None:
        """Load long-lived access token from storage."""

    @abstractmethod
    def save_long_lived_token(self, token: str) -> None:
        """Save long-lived access token to storage."""

    @abstractmethod
    def delete_long_lived_token(self) -> None:
        """Delete long-lived access token from storage."""

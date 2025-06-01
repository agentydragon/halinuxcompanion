"""Secure secret storage backends for authentication tokens."""

import json
import logging
from abc import ABC, abstractmethod
from enum import Enum
from functools import cached_property

from .oauth import OAuthTokens

logger = logging.getLogger(__name__)

# Try to import libsecret, but make it optional
try:
    import gi

    gi.require_version("Secret", "1")
    from gi.repository import Secret
except (ImportError, ValueError):
    Secret = None
    GLib = None


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


class LibSecretStorage(SecretStorage):
    """libsecret-based secure storage using system keyring."""

    APP_ID = "io.github.halinuxcompanion"

    def __init__(self):
        if Secret is None:
            raise ImportError("libsecret is not available. Install python3-gi and libsecret.")

    @cached_property
    def schema(self):
        """Get the Secret schema (cached)."""
        return Secret.Schema.new(
            self.APP_ID,
            Secret.SchemaFlags.NONE,
            {
                "application": Secret.SchemaAttributeType.STRING,
                "service": Secret.SchemaAttributeType.STRING,
                "type": Secret.SchemaAttributeType.STRING,
            },
        )

    def _get_attributes(self, secret_type: str) -> dict[str, str]:
        """Get attributes for secret lookup."""
        return {
            "application": self.APP_ID,
            "service": "home-assistant",
            "type": secret_type,
        }

    def _store_password(self, label: str, secret_type: str, password: str) -> None:
        """Store a password in the keyring."""
        Secret.password_store_sync(
            self.schema,
            self._get_attributes(secret_type),
            Secret.COLLECTION_DEFAULT,
            label,
            password,
            None,
        )

    def _lookup_password(self, secret_type: str) -> str | None:
        """Look up a password from the keyring."""
        result = Secret.password_lookup_sync(
            self.schema,
            self._get_attributes(secret_type),
            None,
        )
        return result  # type: ignore[no-any-return]

    def _clear_password(self, secret_type: str) -> None:
        """Clear a password from the keyring."""
        Secret.password_clear_sync(
            self.schema,
            self._get_attributes(secret_type),
            None,
        )

    def load_oauth_tokens(self) -> OAuthTokens | None:
        """Load OAuth tokens from keyring."""
        try:
            secret = self._lookup_password("oauth")
            if not secret:
                return None
            return OAuthTokens.model_validate(json.loads(secret))  # type: ignore[no-any-return]
        except (json.JSONDecodeError, ValueError):
            logger.exception("Error loading OAuth tokens from libsecret")
            return None

    def save_oauth_tokens(self, tokens: OAuthTokens) -> None:
        """Save OAuth tokens to keyring."""
        self._store_password(
            "Home Assistant OAuth Tokens",
            "oauth",
            tokens.model_dump_json(),
        )
        logger.info("OAuth tokens saved to system keyring")

    def delete_oauth_tokens(self) -> None:
        """Delete OAuth tokens from keyring."""
        self._clear_password("oauth")

    def load_long_lived_token(self) -> str | None:
        """Load long-lived token from keyring."""
        return self._lookup_password("long_lived_token")

    def save_long_lived_token(self, token: str) -> None:
        """Save long-lived token to keyring."""
        self._store_password(
            "Home Assistant Long-Lived Token",
            "long_lived_token",
            token,
        )
        logger.info("Long-lived token saved to system keyring")

    def delete_long_lived_token(self) -> None:
        """Delete long-lived token from keyring."""
        self._clear_password("long_lived_token")

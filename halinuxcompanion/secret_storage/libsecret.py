"""libsecret-based secure storage using system keyring."""

import json
import logging
from functools import cached_property

from ..oauth import OAuthTokens
from .base import SecretStorage

logger = logging.getLogger(__name__)

# Try to import libsecret, but make it optional
try:
    import gi

    gi.require_version("Secret", "1")
    from gi.repository import Secret
except (ImportError, ValueError):
    Secret = None
    GLib = None


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

    def _attributes(self, secret_type: str) -> dict[str, str]:
        """Get attributes for secret lookup."""
        return {
            "application": self.APP_ID,
            "service": "home-assistant",
            "type": secret_type,
        }

    def _store(self, label: str, secret_type: str, password: str) -> None:
        """Store a password in the keyring."""
        Secret.password_store_sync(
            self.schema,
            self._attributes(secret_type),
            Secret.COLLECTION_DEFAULT,
            label,
            password,
            None,
        )

    def _lookup(self, secret_type: str) -> str | None:
        """Look up a password from the keyring."""
        result = Secret.password_lookup_sync(
            self.schema,
            self._attributes(secret_type),
            None,
        )
        return result  # type: ignore[no-any-return]

    @property
    def oauth_tokens(self) -> OAuthTokens | None:
        """Load OAuth tokens from keyring."""
        if not (secret := self._lookup("oauth")):
            return None
        return OAuthTokens.model_validate(json.loads(secret))

    @oauth_tokens.setter
    def oauth_tokens(self, tokens: OAuthTokens) -> None:
        """Save OAuth tokens to keyring."""
        self._store("Home Assistant OAuth Tokens", "oauth", tokens.model_dump_json())

    @property
    def long_lived_token(self) -> str | None:
        """Load long-lived token from keyring."""
        return self._lookup("long_lived_token")

    @long_lived_token.setter
    def long_lived_token(self, token: str) -> None:
        """Save long-lived token to keyring."""
        self._store("Home Assistant Long-Lived Token", "long_lived_token", token)

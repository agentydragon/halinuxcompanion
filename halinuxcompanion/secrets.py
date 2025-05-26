"""Secure secret storage backends for authentication tokens."""

import json
import logging
import os
import stat
from abc import ABC, abstractmethod
from enum import Enum
from functools import cached_property
from pathlib import Path
from typing import Dict, Literal, Optional

from .oauth import OAuthTokens, check_file_permissions

logger = logging.getLogger(__name__)

# Try to import libsecret, but make it optional
try:
    import gi

    gi.require_version("Secret", "1")
    from gi.repository import GLib, Secret
except (ImportError, ValueError):
    Secret = None
    GLib = None


class StorageBackend(str, Enum):
    """Available storage backends for secrets."""

    FILE = "file"
    LIBSECRET = "libsecret"
    AUTO = "auto"  # Automatically choose best available


class SecretStorage(ABC):
    """Abstract base class for secret storage backends."""

    @abstractmethod
    def load_oauth_tokens(self) -> Optional[OAuthTokens]:
        """Load OAuth tokens from storage."""
        pass

    @abstractmethod
    def save_oauth_tokens(self, tokens: OAuthTokens) -> None:
        """Save OAuth tokens to storage."""
        pass

    @abstractmethod
    def delete_oauth_tokens(self) -> None:
        """Delete OAuth tokens from storage."""
        pass

    @abstractmethod
    def load_long_lived_token(self) -> Optional[str]:
        """Load long-lived access token from storage."""
        pass

    @abstractmethod
    def save_long_lived_token(self, token: str) -> None:
        """Save long-lived access token to storage."""
        pass

    @abstractmethod
    def delete_long_lived_token(self) -> None:
        """Delete long-lived access token from storage."""
        pass


class FileSecretStorage(SecretStorage):
    """File-based secret storage with permission checks."""

    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.oauth_token_file = state_dir / "oauth_tokens.json"
        self.lat_file = state_dir / "long_lived_token"

    def _ensure_secure_directory(self, path: Path) -> None:
        """Ensure directory exists with secure permissions.

        Creates the directory if needed and validates security.
        """
        # Create with restrictive permissions
        path.mkdir(parents=True, exist_ok=True, mode=0o700)

        # Check parent directory security
        parent = path.parent
        # Parent directory should not be world-writable
        if parent.stat().st_mode & stat.S_IWOTH:
            raise PermissionError(
                f"Parent directory {parent} is world-writable. "
                f"This is a security risk. Fix with: chmod o-w {parent}"
            )

    def _write_secure_file(self, file_path: Path, content: str) -> None:
        """Write content to file with security checks."""
        # Ensure directory exists and is secure
        self._ensure_secure_directory(file_path.parent)

        # Write file
        with open(file_path, "w") as f:
            f.write(content)

        # Set restrictive permissions immediately
        os.chmod(file_path, 0o600)

    def _read_secure_file(self, file_path: Path) -> Optional[str]:
        """Read content from file with security checks."""
        if not file_path.exists():
            return None

        # Check file permissions for security
        try:
            check_file_permissions(file_path)
        except PermissionError as e:
            logger.error("Security error")
            raise

        try:
            with open(file_path, "r") as f:
                return f.read()
        except OSError as e:
            logger.error(f"Error reading {file_path}")
            raise

    def load_oauth_tokens(self) -> Optional[OAuthTokens]:
        """Load OAuth tokens from file."""
        content = self._read_secure_file(self.oauth_token_file)
        if not content:
            return None

        try:
            return OAuthTokens.model_validate(json.loads(content))
        except ValueError as e:
            logger.error("Error parsing OAuth tokens")
            return None

    def save_oauth_tokens(self, tokens: OAuthTokens) -> None:
        """Save OAuth tokens to file."""
        self._write_secure_file(self.oauth_token_file, tokens.model_dump_json())

    def delete_oauth_tokens(self) -> None:
        """Delete OAuth tokens file."""
        if self.oauth_token_file.exists():
            self.oauth_token_file.unlink()

    def load_long_lived_token(self) -> Optional[str]:
        """Load long-lived token from file."""
        content = self._read_secure_file(self.lat_file)
        return content.strip() if content else None

    def save_long_lived_token(self, token: str) -> None:
        """Save long-lived token to file."""
        self._write_secure_file(self.lat_file, token)

    def delete_long_lived_token(self) -> None:
        """Delete long-lived token file."""
        if self.lat_file.exists():
            self.lat_file.unlink()


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

    def _get_attributes(self, secret_type: str) -> Dict[str, str]:
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

    def _lookup_password(self, secret_type: str) -> Optional[str]:
        """Look up a password from the keyring."""
        return Secret.password_lookup_sync(
            self.schema,
            self._get_attributes(secret_type),
            None,
        )

    def _clear_password(self, secret_type: str) -> None:
        """Clear a password from the keyring."""
        Secret.password_clear_sync(
            self.schema,
            self._get_attributes(secret_type),
            None,
        )

    def load_oauth_tokens(self) -> Optional[OAuthTokens]:
        """Load OAuth tokens from keyring."""
        try:
            secret = self._lookup_password("oauth")
            if not secret:
                return None
            return OAuthTokens.model_validate(json.loads(secret))
        except (json.JSONDecodeError, ValueError):
            logger.error("Error loading OAuth tokens from libsecret")
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

    def load_long_lived_token(self) -> Optional[str]:
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


def get_secret_storage(backend: StorageBackend, state_dir: Path) -> SecretStorage:
    """Get the appropriate secret storage backend.

    Args:
        backend: The storage backend to use
        state_dir: Directory for file-based storage

    Returns:
        SecretStorage implementation

    Raises:
        ValueError: If invalid backend
        ImportError: If libsecret requested but not available
    """
    if backend == StorageBackend.AUTO:
        # Try libsecret first, fall back to file
        if Secret is not None:
            try:
                return LibSecretStorage()
            except ImportError:
                logger.warning("Failed to initialize libsecret, falling back to file storage")
        return FileSecretStorage(state_dir)

    if backend == StorageBackend.LIBSECRET:
        return LibSecretStorage()

    if backend == StorageBackend.FILE:
        return FileSecretStorage(state_dir)

    raise ValueError(f"Unknown storage backend: {backend}")

"""File-based secret storage with comprehensive security checks."""

import json
import logging
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..oauth import OAuthTokens
from ..paths import get_state_dir
from .base import SecretStorage

logger = logging.getLogger(__name__)


@dataclass
class SecureFile:
    path: Path

    def read(self) -> str | None:
        """Read file content with security checks."""
        if not self.path.exists():
            return None

        # Comprehensive security checks for files containing secrets:
        # - Permissions must be 0o600 (owner read/write only)
        # - Must be owned by current user
        # - Must not be a symlink
        # - Parent directory must have secure permissions
        # - Must be a regular file (not device, socket, etc.)
        if not self.path.is_file():
            raise PermissionError(f"{self.path} is not a regular file.")
        try:
            file_stat = self.path.stat()
        except OSError:
            raise PermissionError(f"Cannot stat {self.path}")
        if file_stat.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise PermissionError(f"{self.path} permissions are too open. Fix with: chmod 600 {self.path}")
        if file_stat.st_uid != os.getuid():
            raise PermissionError(f"{self.path} owned by uid {file_stat.st_uid}, not current uid {os.getuid()}.")

        parent = self.path.parent
        dir_stat = parent.stat()

        if dir_stat.st_mode & stat.S_IWOTH:
            raise PermissionError(f"{parent} is world-writable. Fix with: chmod o-w {parent}")
        if dir_stat.st_uid not in (os.getuid(), 0):
            raise PermissionError(f"{parent} owned by uid {dir_stat.st_uid}, not current user or root.")

        try:
            return self.path.read_text(encoding="utf-8")
        except OSError:
            logger.exception(f"Error reading {self.path}")
            raise

    def write(self, content: str) -> None:
        """Write content to file with security checks."""
        # Ensure directory exists with secure permissions.
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

        # Check parent directory security
        parent = self.path.parent
        if parent.stat().st_mode & stat.S_IWOTH:
            raise PermissionError(f"Parent directory {parent} is world-writable. Fix with: chmod o-w {parent}")

        # Write with temporary file to ensure atomicity
        # Use a unique temp file to avoid conflicts in concurrent access
        fd, temp_path_str = tempfile.mkstemp(dir=self.path.parent, prefix=self.path.stem)
        temp_path = Path(temp_path_str)

        try:
            # mkstemp already creates the file, no need to touch()
            # Set secure permissions (mkstemp creates with 0o600 by default, but be explicit)
            os.fchmod(fd, 0o600)

            # Write content to temp file
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)

            # Atomically replace the target file
            temp_path.replace(self.path)
        except Exception:
            # Clean up temp file on error
            try:
                os.close(fd)  # Ensure fd is closed
            except Exception:
                pass
            try:
                temp_path.unlink()
            except Exception:
                logger.exception(f"Error cleaning up temporary file {temp_path}")
            raise


class FileSecretStorage(SecretStorage):
    """File-based secret storage with permission checks."""

    def __init__(self, state_dir: Path | None = None) -> None:
        self.state_dir = state_dir or get_state_dir()

    @property
    def oauth_token_file(self) -> SecureFile:
        return SecureFile(self.state_dir / "oauth_tokens.json")

    @property
    def lat_file(self) -> SecureFile:
        return SecureFile(self.state_dir / "long_lived_token")

    @property
    def oauth_tokens(self) -> OAuthTokens | None:
        if not (content := self.oauth_token_file.read()):
            return None
        try:
            return OAuthTokens.model_validate(json.loads(content))
        except ValueError:
            logger.exception("Error parsing OAuth tokens")
            raise

    @oauth_tokens.setter
    def oauth_tokens(self, tokens: OAuthTokens) -> None:
        self.oauth_token_file.write(tokens.model_dump_json())

    @property
    def long_lived_token(self) -> str | None:
        content = self.lat_file.read()
        return content.strip() if content else None

    @long_lived_token.setter
    def long_lived_token(self, token: str) -> None:
        self.lat_file.write(token)

"""File-based secret storage with comprehensive security checks."""

import json
import logging
import os
import stat
from pathlib import Path

from ..oauth import OAuthTokens
from ..secrets import SecretStorage

logger = logging.getLogger(__name__)


def check_file_permissions(path: Path) -> None:
    """Check that a file has secure permissions and ownership.

    Comprehensive security checks for files containing secrets:
    - Permissions must be 0o600 (owner read/write only)
    - Must be owned by current user
    - Must not be a symlink
    - Parent directory must have secure permissions
    - Must be a regular file (not device, socket, etc.)

    Raises:
        PermissionError: If file permissions are insecure
        OSError: If unable to check file stats
    """
    try:
        file_stat = path.stat()
    except OSError:
        raise PermissionError(f"Cannot stat {path}")

    if not stat.S_ISREG(file_stat.st_mode):
        raise PermissionError(f"Sensitive file {path} is not a regular file.")

    if (mode := file_stat.st_mode) & (stat.S_IRWXG | stat.S_IRWXO):
        raise PermissionError(
            f"{path} has overly permissive permissions ({oct(stat.S_IMODE(mode))}). Fix with: chmod 600 {path}"
        )

    if file_stat.st_uid != os.getuid():
        raise PermissionError(f"{path} is owned by uid {file_stat.st_uid}, not current user ({os.getuid()}).")

    parent = path.parent
    parent_stat = parent.stat()

    if parent_stat.st_mode & stat.S_IWOTH:
        raise PermissionError(f"{parent} is world-writable. Fix with: chmod o-w {parent}")

    if parent_stat.st_uid not in (os.getuid(), 0):
        raise PermissionError(f"{parent} owned by uid {parent_stat.st_uid}, not current user or root.")


class FileSecretStorage(SecretStorage):
    """File-based secret storage with permission checks."""

    def __init__(self, state_dir: Path):
        self.state_dir = state_dir

    @property
    def oauth_token_file(self) -> Path:
        return self.state_dir / "oauth_tokens.json"

    @property
    def lat_file(self) -> Path:
        return self.state_dir / "long_lived_token"

    def _ensure_secure_directory(self, path: Path) -> None:
        """Ensure directory exists with secure permissions.

        Creates the directory if needed and validates security.
        """
        # Create with restrictive permissions
        path.mkdir(parents=True, exist_ok=True, mode=0o700)

        # Check parent directory security
        parent = path.parent
        if parent.stat().st_mode & stat.S_IWOTH:
            raise PermissionError(f"Parent directory {parent} is world-writable. Fix with: chmod o-w {parent}")

    def _write_secure_file(self, file_path: Path, content: str) -> None:
        """Write content to file with security checks."""
        import tempfile

        # Ensure directory exists and is secure
        self._ensure_secure_directory(file_path.parent)

        # Write with temporary file to ensure atomicity
        # Use a unique temp file to avoid conflicts in concurrent access
        fd, temp_path_str = tempfile.mkstemp(dir=file_path.parent, prefix=file_path.stem)
        temp_path = Path(temp_path_str)

        try:
            # Write content to temp file
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)

            # Set secure permissions
            temp_path.chmod(0o600)

            # Atomically replace the target file
            temp_path.replace(file_path)
        except Exception:
            # Clean up temp file on error
            try:
                temp_path.unlink()
            except Exception:
                pass
            raise

    def _read_secure_file(self, file_path: Path) -> str | None:
        """Read content from file with security checks."""
        if not file_path.exists():
            return None

        # Check file permissions for security
        try:
            check_file_permissions(file_path)
        except PermissionError:
            logger.error("Security error")  # noqa: TRY400
            raise

        try:
            return file_path.read_text(encoding="utf-8")
        except OSError:
            logger.error(f"Error reading {file_path}")  # noqa: TRY400
            raise

    def load_oauth_tokens(self) -> OAuthTokens | None:
        if not (content := self._read_secure_file(self.oauth_token_file)):
            return None
        try:
            return OAuthTokens.model_validate(json.loads(content))  # type: ignore[no-any-return]
        except ValueError:
            logger.exception("Error parsing OAuth tokens")
            return None

    def save_oauth_tokens(self, tokens: OAuthTokens) -> None:
        self._write_secure_file(self.oauth_token_file, tokens.model_dump_json())

    def delete_oauth_tokens(self) -> None:
        if self.oauth_token_file.exists():
            self.oauth_token_file.unlink()

    def load_long_lived_token(self) -> str | None:
        content = self._read_secure_file(self.lat_file)
        return content.strip() if content else None

    def save_long_lived_token(self, token: str) -> None:
        self._write_secure_file(self.lat_file, token)

    def delete_long_lived_token(self) -> None:
        if self.lat_file.exists():
            self.lat_file.unlink()

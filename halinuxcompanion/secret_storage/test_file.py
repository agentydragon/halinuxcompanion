"""Tests for file-based secret storage."""

import stat
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from halinuxcompanion.secret_storage.file import (
    FileSecretStorage,
    check_file_permissions,
)
from halinuxcompanion.oauth import OAuthTokens


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a secure subdirectory since /tmp might be world-writable
        secure_dir = Path(tmpdir) / "secure_test_dir"
        secure_dir.mkdir(mode=0o700)
        yield secure_dir


@pytest.fixture
def storage(temp_dir):
    """Create a FileSecretStorage instance with a temporary directory."""
    return FileSecretStorage(temp_dir)


@pytest.fixture
def sample_oauth_tokens():
    """Create sample OAuth tokens for testing."""
    return OAuthTokens(
        access_token="test_access_token",
        refresh_token="test_refresh_token",
        expires_in=3600,
        token_type="Bearer",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )


class TestCheckFilePermissions:
    """Test the check_file_permissions function."""

    def test_valid_file(self, temp_dir):
        """Test that a properly secured file passes all checks."""
        file_path = temp_dir / "test_file"
        file_path.write_text("test content")
        file_path.chmod(0o600)

        # Should not raise
        check_file_permissions(file_path)

    def test_nonexistent_file(self, temp_dir):
        """Test that checking a nonexistent file raises PermissionError."""
        file_path = temp_dir / "nonexistent"

        with pytest.raises(PermissionError, match="Cannot stat"):
            check_file_permissions(file_path)

    def test_group_readable_file(self, temp_dir):
        """Test that group-readable files are rejected."""
        file_path = temp_dir / "group_readable"
        file_path.write_text("test content")
        file_path.chmod(0o640)  # Owner read/write, group read

        with pytest.raises(PermissionError, match="overly permissive permissions"):
            check_file_permissions(file_path)

    def test_directory_instead_of_file(self, temp_dir):
        """Test that directories are rejected."""
        dir_path = temp_dir / "subdir"
        dir_path.mkdir()
        dir_path.chmod(0o700)

        with pytest.raises(PermissionError, match="not a regular file"):
            check_file_permissions(dir_path)

    def test_symlink(self, temp_dir):
        """Test that symlinks are rejected."""
        target_file = temp_dir / "target"
        target_file.write_text("test content")
        target_file.chmod(0o600)

        symlink_path = temp_dir / "symlink"
        symlink_path.symlink_to(target_file)

        # stat() follows symlinks by default, so this should check the target file
        # and pass if the target has correct permissions
        check_file_permissions(symlink_path)

    @patch("os.getuid")
    def test_wrong_owner(self, mock_getuid, temp_dir):
        """Test that files owned by other users are rejected."""
        mock_getuid.return_value = 1000  # Simulate current user

        file_path = temp_dir / "wrong_owner"
        file_path.write_text("test content")

        # Mock the file as owned by a different user
        with patch.object(Path, "stat") as mock_stat:
            mock_stat.return_value.st_mode = stat.S_IFREG | 0o600
            mock_stat.return_value.st_uid = 1001  # Different user

            with pytest.raises(PermissionError, match="owned by uid 1001"):
                check_file_permissions(file_path)

    def test_world_writable_parent(self, temp_dir):
        """Test that files in world-writable directories are rejected."""
        subdir = temp_dir / "subdir"
        subdir.mkdir()
        subdir.chmod(0o777)  # World writable

        file_path = subdir / "test_file"
        file_path.write_text("test content")
        file_path.chmod(0o600)

        with pytest.raises(PermissionError, match="is world-writable"):
            check_file_permissions(file_path)


class TestFileSecretStorage:
    """Test the FileSecretStorage class."""

    def test_oauth_token_save_and_load(self, storage, sample_oauth_tokens):
        """Test saving and loading OAuth tokens."""
        # Save tokens
        storage.save_oauth_tokens(sample_oauth_tokens)

        # Verify file was created with correct permissions
        assert storage.oauth_token_file.exists()
        assert oct(storage.oauth_token_file.stat().st_mode)[-3:] == "600"

        # Load tokens
        assert storage.load_oauth_tokens() == sample_oauth_tokens

    def test_oauth_token_delete(self, storage, sample_oauth_tokens):
        """Test deleting OAuth tokens."""
        # Save tokens first
        storage.save_oauth_tokens(sample_oauth_tokens)
        assert storage.oauth_token_file.exists()

        # Delete tokens
        storage.delete_oauth_tokens()
        assert not storage.oauth_token_file.exists()

        # Loading should return None
        assert storage.load_oauth_tokens() is None

    def test_oauth_token_delete_nonexistent(self, storage):
        """Test deleting OAuth tokens when file doesn't exist."""
        # Should not raise even if file doesn't exist
        storage.delete_oauth_tokens()

    def test_long_lived_token_save_and_load(self, storage):
        """Test saving and loading long-lived tokens."""
        token = "test_long_lived_token_123"
        storage.save_long_lived_token(token)

        # Verify file was created with correct permissions
        assert storage.lat_file.exists()
        assert oct(storage.lat_file.stat().st_mode)[-3:] == "600"

        # Load token
        assert storage.load_long_lived_token() == token

    def test_long_lived_token_with_whitespace(self, storage):
        """Test that whitespace is stripped from long-lived tokens."""
        token = "  test_token_with_spaces  \n"

        storage.save_long_lived_token(token)
        assert storage.load_long_lived_token() == "test_token_with_spaces"

    def test_long_lived_token_delete(self, storage):
        """Test deleting long-lived tokens."""
        # Save token first
        storage.save_long_lived_token("test_token")
        assert storage.lat_file.exists()

        # Delete token
        storage.delete_long_lived_token()
        assert not storage.lat_file.exists()

        # Loading should return None
        assert storage.load_long_lived_token() is None

    def test_directory_creation(self, temp_dir):
        """Test that directories are created if they don't exist."""
        # Create storage with nested directory structure
        nested_dir = temp_dir / "level1" / "level2" / "level3"
        storage = FileSecretStorage(nested_dir)

        # Save a token
        storage.save_long_lived_token("test_token")

        # Verify directory structure was created
        assert nested_dir.exists()
        assert nested_dir.is_dir()
        assert oct(nested_dir.stat().st_mode)[-3:] == "700"

    def test_load_corrupted_oauth_tokens(self, storage):
        """Test loading corrupted OAuth token file."""
        # Write invalid JSON
        storage.oauth_token_file.parent.mkdir(parents=True, exist_ok=True)
        storage.oauth_token_file.write_text("{ invalid json }")
        storage.oauth_token_file.chmod(0o600)

        # Should return None instead of raising
        assert storage.load_oauth_tokens() is None

    def test_load_oauth_tokens_missing_fields(self, storage):
        """Test loading OAuth tokens with missing required fields."""
        # Write valid JSON but missing required fields
        storage.oauth_token_file.parent.mkdir(parents=True, exist_ok=True)
        storage.oauth_token_file.write_text('{"access_token": "test"}')
        storage.oauth_token_file.chmod(0o600)

        # Should return None due to validation error
        assert storage.load_oauth_tokens() is None

    def test_world_writable_parent_rejected(self, temp_dir):
        """Test that files cannot be saved in world-writable directories."""
        # Create world-writable directory inside our secure temp dir
        insecure_parent = temp_dir / "world_writable"
        insecure_parent.mkdir()
        insecure_parent.chmod(0o777)

        # Create the actual storage directory inside the world-writable one
        storage = FileSecretStorage(insecure_parent / "storage")

        # Should raise when trying to save because parent is world-writable
        with pytest.raises(PermissionError, match="is world-writable"):
            storage.save_long_lived_token("test_token")

    def test_read_file_with_wrong_permissions(self, storage):
        """Test that reading files with wrong permissions is rejected."""
        # Create file with wrong permissions
        storage.lat_file.parent.mkdir(parents=True, exist_ok=True)
        storage.lat_file.write_text("test_token")
        storage.lat_file.chmod(0o644)  # World readable

        # Should raise when trying to read
        with pytest.raises(PermissionError, match="overly permissive permissions"):
            storage.load_long_lived_token()

    def test_empty_token_handling(self, storage):
        """Test handling of empty tokens."""
        # Save empty long-lived token
        storage.save_long_lived_token("")

        # Empty tokens get stripped and become None
        assert storage.load_long_lived_token() is None

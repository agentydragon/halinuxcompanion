"""Tests for file-based secret storage."""

import stat
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from halinuxcompanion.oauth import OAuthTokens
from halinuxcompanion.secret_storage.file import FileSecretStorage, SecureFile


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a secure subdirectory since /tmp might be world-writable
        secure_dir = Path(tmpdir) / "secure_test_dir"
        secure_dir.mkdir(mode=0o700)
        yield secure_dir


@pytest.fixture
def storage(temp_dir, monkeypatch):
    """Create a FileSecretStorage instance with a temporary directory."""
    # Mock get_state_dir to return our temp directory
    monkeypatch.setattr("halinuxcompanion.secret_storage.file.get_state_dir", lambda: temp_dir)
    return FileSecretStorage()


class TestCheckFilePermissions:
    """Test the check_file_permissions function."""

    def test_valid_file(self, temp_dir):
        """Test that a properly secured file passes all checks."""
        file_path = temp_dir / "test_file"
        file_path.write_text("test content")
        file_path.chmod(0o600)

        # Should not raise
        SecureFile(file_path).read()

    def test_nonexistent_file(self, temp_dir):
        """Test that reading a nonexistent file returns None."""
        file_path = temp_dir / "nonexistent"

        # Should return None for non-existent files
        assert SecureFile(file_path).read() is None

    def test_group_readable_file(self, temp_dir):
        """Test that group-readable files are rejected."""
        file_path = temp_dir / "group_readable"
        file_path.write_text("test content")
        file_path.chmod(0o640)  # Owner read/write, group read

        with pytest.raises(PermissionError):
            SecureFile(file_path).read()

    def test_directory_instead_of_file(self, temp_dir):
        """Test that directories are rejected."""
        dir_path = temp_dir / "subdir"
        dir_path.mkdir()
        dir_path.chmod(0o700)

        with pytest.raises(PermissionError, match="not a regular file"):
            SecureFile(dir_path).read()

    def test_symlink(self, temp_dir):
        """Test that symlinks are rejected."""
        target_file = temp_dir / "target"
        target_file.write_text("test content")
        target_file.chmod(0o600)

        symlink_path = temp_dir / "symlink"
        symlink_path.symlink_to(target_file)

        # stat() follows symlinks by default, so this should check the target file
        # and pass if the target has correct permissions
        SecureFile(symlink_path).read()

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
                SecureFile(file_path).read()

    def test_world_writable_parent(self, temp_dir):
        """Test that files in world-writable directories are rejected."""
        subdir = temp_dir / "subdir"
        subdir.mkdir()
        subdir.chmod(0o777)  # World writable

        file_path = subdir / "test_file"
        file_path.write_text("test content")
        file_path.chmod(0o600)

        with pytest.raises(PermissionError, match="is world-writable"):
            SecureFile(file_path).read()


class TestFileSecretStorage:
    """Test the FileSecretStorage class."""

    def test_oauth_token_save_and_load(self, storage):
        """Test saving and loading OAuth tokens."""
        sample_tokens = OAuthTokens(
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            expires_in=3600,
            token_type="Bearer",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        storage.oauth_tokens = sample_tokens

        # Verify file was created with correct permissions
        assert storage.oauth_token_file.path.exists()
        assert oct(storage.oauth_token_file.path.stat().st_mode)[-3:] == "600"

        assert storage.oauth_tokens == sample_tokens

    def test_long_lived_token_save_and_load(self, storage):
        """Test saving and loading long-lived tokens."""
        storage.long_lived_token = "foo123"

        # Verify file was created with correct permissions
        assert storage.lat_file.path.exists()
        assert oct(storage.lat_file.path.stat().st_mode)[-3:] == "600"

        assert storage.long_lived_token == "foo123"

    def test_long_lived_token_with_whitespace(self, storage):
        """Test that whitespace is stripped from long-lived tokens."""
        storage.long_lived_token = "  test_token_with_spaces  \n"
        assert storage.long_lived_token == "test_token_with_spaces"

    def test_directory_creation(self, temp_dir):
        """Test that directories are created if they don't exist."""
        # Create storage with nested directory structure
        nested_dir = temp_dir / "level1" / "level2" / "level3"
        storage = FileSecretStorage(nested_dir)

        storage.long_lived_token = "test_token"

        # Verify directory structure was created
        assert nested_dir.exists()
        assert nested_dir.is_dir()
        assert oct(nested_dir.stat().st_mode)[-3:] == "700"

    def test_world_writable_parent_rejected(self, temp_dir):
        """Test that files cannot be saved in world-writable directories."""
        # Create world-writable directory inside our secure temp dir
        insecure_parent = temp_dir / "world_writable"
        insecure_parent.mkdir()
        insecure_parent.chmod(0o777)

        # Use the world-writable directory directly as storage
        storage = FileSecretStorage(insecure_parent)

        # Should raise when trying to save because parent is world-writable
        with pytest.raises(PermissionError, match="is world-writable"):
            storage.long_lived_token = "test_token"

    def test_read_file_with_wrong_permissions(self, storage):
        """Test that reading files with wrong permissions is rejected."""
        # Create file with wrong permissions
        storage.lat_file.path.parent.mkdir(parents=True, exist_ok=True)
        storage.lat_file.path.write_text("test_token")
        storage.lat_file.path.chmod(0o644)  # World readable

        # Should raise when trying to read
        with pytest.raises(PermissionError, match="permissions are too open"):
            _ = storage.long_lived_token

    def test_empty_token_handling(self, storage):
        """Test handling of empty tokens."""
        storage.long_lived_token = ""

        # Empty tokens get stripped and become None
        assert storage.long_lived_token is None

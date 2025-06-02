"""Centralized path management for configuration and state files."""

from pathlib import Path

from xdg_base_dirs import xdg_config_home, xdg_state_home


def get_config_dir() -> Path:
    """Get the configuration directory path using XDG_CONFIG_HOME."""
    return Path(xdg_config_home()) / "halinuxcompanion"


def get_default_config_path() -> Path:
    """Get the default config file path."""
    return get_config_dir() / "config.toml"


def get_state_dir() -> Path:
    """Get the state directory path using XDG_STATE_HOME."""
    return Path(xdg_state_home()) / "halinuxcompanion"


def get_state_file_path() -> Path:
    """Get the state file path."""
    return get_state_dir() / "state.json"


def get_secret_file_path() -> Path:
    """Get the file-based secret storage path."""
    return get_state_dir() / "secrets.json"

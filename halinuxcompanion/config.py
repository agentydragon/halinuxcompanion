"""Configuration for Home Assistant Linux Companion."""

import platform
from dataclasses import dataclass, field


@dataclass
class Config:
    """Application configuration."""

    device_name: str = field(default_factory=platform.node)  # Default to hostname
    modules: dict[str, bool] = field(
        default_factory=lambda: {
            "battery": True,
            "bluetooth": True,
        }
    )
    bluetooth_device_macs: list[str] = field(default_factory=list)


def load_config() -> Config:
    """Load configuration.

    For now, returns hardcoded defaults.
    Future: Load from TOML file.

    Returns:
        The configuration.
    """
    # TODO: Load from ~/.config/halinuxcompanion/config.toml
    return Config(
        device_name=platform.node(),
        modules={
            "battery": True,
            "bluetooth": True,
        },
        bluetooth_device_macs=[
            "A8:F5:E1:77:2C:59",  # Shokz OpenRun Pro 2
            "78:2B:64:A1:0E:1E",  # Bose QC45
            # TODO: Move to config file
        ],
    )

"""Hierarchical hardware configuration models."""

import re
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


class HardwareClassConfig(BaseModel):
    """Base configuration for a hardware class."""

    enabled: bool = False


class BatteryConfig(HardwareClassConfig):
    """Configuration for battery hardware class."""

    implementation: Literal["psutil", "upower"] = "psutil"
    # All sensors enabled by default
    # TODO: Add support for multiple batteries (battery_ids)


class NetworkConfig(HardwareClassConfig):
    """Configuration for network hardware class."""

    interfaces: list[str] = Field(
        default_factory=list,
        description="List of network interfaces to monitor (e.g., ['eth0', 'wlan0'])",
    )
    # Feature flags that control groups of sensors
    show_status: bool = True  # status binary sensor
    show_counters: bool = True  # tx_bytes, rx_bytes sensors
    show_ip_addresses: bool = False  # ipv4_address, ipv6_address sensors


class CPUConfig(HardwareClassConfig):
    """Configuration for CPU hardware class."""

    # Always shows usage_percent and frequency


class MemoryConfig(HardwareClassConfig):
    """Configuration for memory hardware class."""

    # Always shows usage_percent, used_mb, available_mb
    # TODO: Expose more precise units - psutil returns bytes, we could expose as kB/MB/GB with proper unit


class CameraConfig(HardwareClassConfig):
    """Configuration for camera hardware class."""

    # Creates binary_sensor per camera for in_use status
    # TODO: Add support for selecting specific cameras (camera_ids)


class LidConfig(HardwareClassConfig):
    """Configuration for lid hardware class."""

    # Single binary_sensor for lid open/closed


Mac = Annotated[
    str,
    StringConstraints(
        pattern=r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$",  # XX:XX:XX:XX:XX:XX
        strip_whitespace=True,
    ),
]


class BluetoothConfig(HardwareClassConfig):
    """Configuration for bluetooth hardware class."""

    devices: list[Mac] = Field(
        default_factory=list,
        description="List of Bluetooth MAC addresses to monitor",
    )


class UptimeConfig(HardwareClassConfig):
    """Configuration for uptime hardware class."""

    # Single sensor showing system uptime


class TemperatureConfig(HardwareClassConfig):
    """Configuration for temperature hardware class."""

    # TODO: Add sensor filtering/selection - for now expose all available temperature sensors


class HardwareConfig(BaseModel):
    """Root hardware configuration containing all hardware classes."""

    battery: BatteryConfig = BatteryConfig()
    network: NetworkConfig = NetworkConfig()
    cpu: CPUConfig = CPUConfig()
    memory: MemoryConfig = MemoryConfig()
    camera: CameraConfig = CameraConfig()
    lid: LidConfig = LidConfig()
    bluetooth: BluetoothConfig = BluetoothConfig()
    uptime: UptimeConfig = UptimeConfig()
    temperature: TemperatureConfig = TemperatureConfig()

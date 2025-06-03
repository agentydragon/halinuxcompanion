"""Hierarchical module configuration models."""

from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

if TYPE_CHECKING:
    from halinuxcompanion.module_base import Module


class ModuleConfig(BaseModel):
    """Base configuration for a module."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False


class BatteryConfig(ModuleConfig):
    """Configuration for battery module."""

    implementation: Literal["psutil", "upower"] = "psutil"
    # All sensors enabled by default
    # TODO: Add support for multiple batteries (battery_ids)


class NetworkConfig(ModuleConfig):
    """Configuration for network module."""

    interfaces: list[str] = Field(
        default_factory=list,
        description="List of network interfaces to monitor (e.g., ['eth0', 'wlan0'])",
    )
    # Feature flags that control groups of sensors
    show_status: bool = True  # status binary sensor
    show_counters: bool = True  # tx_bytes, rx_bytes sensors
    show_ip_addresses: bool = False  # ipv4_address, ipv6_address sensors


class CPUConfig(ModuleConfig):
    """Configuration for CPU module."""


class MemoryConfig(ModuleConfig):
    """Configuration for memory module."""


class CameraConfig(ModuleConfig):
    """Configuration for camera module."""

    # Creates binary_sensor per camera for in_use status
    # TODO: Add support for selecting specific cameras (camera_ids)


class LidConfig(ModuleConfig):
    """Configuration for lid module."""


Mac = Annotated[
    str,
    StringConstraints(
        pattern=r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$",  # XX:XX:XX:XX:XX:XX
        strip_whitespace=True,
    ),
]


class BluetoothConfig(ModuleConfig):
    """Configuration for bluetooth module."""

    devices: list[Mac] = Field(
        default_factory=list,
        description="List of Bluetooth MAC addresses to monitor",
    )


class UptimeConfig(ModuleConfig):
    """Configuration for uptime module."""


class TemperatureConfig(ModuleConfig):
    """Configuration for temperature module."""

    # TODO: Add sensor filtering/selection - for now expose all available temperature sensors


class ModulesConfig(BaseModel):
    """Root module configuration containing all modules."""

    model_config = ConfigDict(extra="forbid")

    battery: BatteryConfig = BatteryConfig()
    network: NetworkConfig = NetworkConfig()
    cpu: CPUConfig = CPUConfig()
    memory: MemoryConfig = MemoryConfig()
    camera: CameraConfig = CameraConfig()
    lid: LidConfig = LidConfig()
    bluetooth: BluetoothConfig = BluetoothConfig()
    uptime: UptimeConfig = UptimeConfig()
    temperature: TemperatureConfig = TemperatureConfig()

    def get_enabled_module_classes(self) -> list[tuple[type["Module"], "ModuleConfig"]]:
        """Get list of (module_class, config) for enabled modules.

        This method avoids string-based lookups by directly mapping module classes to configs.
        """
        # Import here to avoid circular imports
        from halinuxcompanion.modules import (
            BatteryModule,
            BluetoothModule,
            CameraModule,
            CPUModule,
            LidModule,
            MemoryModule,
            NetworkModule,
            TemperatureModule,
            UptimeModule,
        )

        module_mapping: list[tuple[type[Module], ModuleConfig]] = [
            (BatteryModule, self.battery),
            (BluetoothModule, self.bluetooth),
            (CameraModule, self.camera),
            (CPUModule, self.cpu),
            (LidModule, self.lid),
            (MemoryModule, self.memory),
            (NetworkModule, self.network),
            (TemperatureModule, self.temperature),
            (UptimeModule, self.uptime),
        ]

        return [(module_class, config) for module_class, config in module_mapping if config.enabled]

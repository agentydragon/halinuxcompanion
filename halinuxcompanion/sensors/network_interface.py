"""Network interface sensors implementation."""

import logging
from typing import Any, Dict, Optional

import psutil
from pydantic import BaseModel

from ..sensor_base import BaseSensor, SensorMetadata

logger = logging.getLogger(__name__)


class NetworkInterfaceConfig(BaseModel):
    """Configuration for network interface sensors."""

    interfaces: list[str]  # Required list of interface names to monitor
    show_ip_addresses: bool = False
    show_mac_address: bool = False


def format_bytes(bytes_value: int) -> str:
    """Format bytes into human readable format."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_value < 1024.0:
            return f"{bytes_value:.2f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.2f} PB"


class NetworkInterfaceSensor(BaseSensor):
    """Network interface sensor for monitoring network statistics."""

    config_name = "network_interface"

    def __init__(self, interface_name: str, config: NetworkInterfaceConfig):
        """Initialize network interface sensor.

        Args:
            interface_name: Name of the network interface (e.g., "eth0", "wlan0")
            config: Configuration for the sensor
        """
        super().__init__(interface_name)
        self.interface_name = interface_name
        self.config = config
        self._is_up = False

    def get_metadata(self) -> SensorMetadata:
        """Get network interface sensor metadata."""
        return SensorMetadata(
            unique_id=f"network_{self.interface_name}",
            name=f"Network {self.interface_name}",
            config_name=self.config_name,
            device_class="data_size",
            state_class="total_increasing",
            unit_of_measurement="B",
            icon="mdi:ethernet" if self.interface_name.startswith("eth") else "mdi:wifi",
        )

    @classmethod
    async def discover_sensors(cls, config: Optional[Dict[str, Any]] = None) -> list["BaseSensor"]:
        """Discover configured network interfaces."""
        sensors = []

        # Parse config with Pydantic
        parsed_config = NetworkInterfaceConfig(**(config or {}))

        # Get available network interfaces
        available_interfaces = psutil.net_if_stats()
        io_counters = psutil.net_io_counters(pernic=True)

        # Only create sensors for explicitly configured interfaces
        for interface_name in parsed_config.interfaces:
            if interface_name not in available_interfaces:
                logger.warning(f"Configured network interface '{interface_name}' not found on system")
                continue

            # Only include interfaces that have IO counters
            if interface_name not in io_counters:
                logger.warning(f"Network interface '{interface_name}' has no IO counters")
                continue

            sensors.append(cls(interface_name, parsed_config))
            logger.info(f"Created network interface sensor for: {interface_name}")

        return sensors

    async def update(self) -> None:
        """Update network interface state and statistics."""
        try:
            # Get interface statistics
            stats = psutil.net_if_stats().get(self.interface_name)
            io_counters = psutil.net_io_counters(pernic=True).get(self.interface_name)

            if not stats or not io_counters:
                self.state = "unavailable"
                self.attributes = {}
                return

            # Update state - total bytes transferred (sent + received)
            self.state = io_counters.bytes_sent + io_counters.bytes_recv
            self._is_up = stats.isup

            # Update icon based on interface state and type
            metadata = self.get_metadata()
            if not stats.isup:
                metadata.icon = "mdi:ethernet-off" if self.interface_name.startswith("eth") else "mdi:wifi-off"
            else:
                metadata.icon = "mdi:ethernet" if self.interface_name.startswith("eth") else "mdi:wifi"

            # Update attributes
            self.attributes = {
                "interface": self.interface_name,
                "is_up": stats.isup,
                "speed": stats.speed,  # Mbps
                "mtu": stats.mtu,
                # Total counters
                "bytes_sent": io_counters.bytes_sent,
                "bytes_recv": io_counters.bytes_recv,
                "bytes_total": io_counters.bytes_sent + io_counters.bytes_recv,
                "bytes_sent_formatted": format_bytes(io_counters.bytes_sent),
                "bytes_recv_formatted": format_bytes(io_counters.bytes_recv),
                "bytes_total_formatted": format_bytes(io_counters.bytes_sent + io_counters.bytes_recv),
                "packets_sent": io_counters.packets_sent,
                "packets_recv": io_counters.packets_recv,
                # Error counters
                "errors_in": io_counters.errin,
                "errors_out": io_counters.errout,
                "drop_in": io_counters.dropin,
                "drop_out": io_counters.dropout,
            }

            # Add IP addresses if configured to show them
            if self.config.show_ip_addresses or self.config.show_mac_address:
                addrs = psutil.net_if_addrs().get(self.interface_name, [])

                for addr in addrs:
                    if addr.family == psutil.AF_LINK and self.config.show_mac_address:  # MAC address
                        self.attributes["mac_address"] = addr.address
                    elif addr.family == 2 and self.config.show_ip_addresses:  # AF_INET (IPv4)
                        if "ipv4_addresses" not in self.attributes:
                            self.attributes["ipv4_addresses"] = []
                        self.attributes["ipv4_addresses"].append(addr.address)
                    elif addr.family == 10 and self.config.show_ip_addresses:  # AF_INET6 (IPv6)
                        if "ipv6_addresses" not in self.attributes:
                            self.attributes["ipv6_addresses"] = []
                        self.attributes["ipv6_addresses"].append(addr.address)

        except Exception as e:
            logger.error(f"Failed to update network interface {self.interface_name}: {e}")
            self.state = "unavailable"
            self.attributes = {"error": str(e)}


class NetworkInterfaceStatusSensor(BaseSensor):
    """Binary sensor for network interface up/down status."""

    sensor_type = "binary_sensor"
    config_name = "network_interface_status"

    def __init__(self, interface_name: str):
        """Initialize network interface status sensor.

        Args:
            interface_name: Name of the network interface
        """
        super().__init__(interface_name)
        self.interface_name = interface_name

    def get_metadata(self) -> SensorMetadata:
        """Get network interface status sensor metadata."""
        return SensorMetadata(
            unique_id=f"network_{self.interface_name}_status",
            name=f"Network {self.interface_name} Status",
            config_name=self.config_name,
            device_class="connectivity",
            icon="mdi:ethernet" if self.interface_name.startswith("eth") else "mdi:wifi",
        )

    @classmethod
    async def discover_sensors(cls, config: Optional[Dict[str, Any]] = None) -> list["BaseSensor"]:
        """Discover configured network interfaces."""
        sensors = []

        # Parse config with Pydantic to get the interface list
        parsed_config = NetworkInterfaceConfig(**(config or {}))

        # Get available network interfaces
        available_interfaces = psutil.net_if_stats()

        # Only create sensors for explicitly configured interfaces
        for interface_name in parsed_config.interfaces:
            if interface_name not in available_interfaces:
                logger.warning(f"Configured network interface '{interface_name}' not found on system")
                continue

            sensors.append(cls(interface_name))
            logger.info(f"Created network interface status sensor for: {interface_name}")

        return sensors

    async def update(self) -> None:
        """Update network interface status."""
        try:
            stats = psutil.net_if_stats().get(self.interface_name)

            if not stats:
                self.state = False
                self.attributes = {"error": "Interface not found"}
                return

            # State is True when interface is up, False when down
            self.state = stats.isup

            # Update icon based on state
            metadata = self.get_metadata()
            if self.interface_name.startswith("eth"):
                metadata.icon = "mdi:ethernet" if self.state else "mdi:ethernet-off"
            else:
                metadata.icon = "mdi:wifi" if self.state else "mdi:wifi-off"

            # Attributes
            self.attributes = {
                "interface": self.interface_name,
                "speed": stats.speed,  # Mbps
                "mtu": stats.mtu,
            }

            # Add IP addresses if interface is up
            if self.state:
                addrs = psutil.net_if_addrs().get(self.interface_name, [])
                ipv4_addrs = []
                ipv6_addrs = []

                for addr in addrs:
                    if addr.family == 2:  # AF_INET (IPv4)
                        ipv4_addrs.append(addr.address)
                    elif addr.family == 10:  # AF_INET6 (IPv6)
                        ipv6_addrs.append(addr.address)

                if ipv4_addrs:
                    self.attributes["ipv4_addresses"] = ipv4_addrs
                if ipv6_addrs:
                    self.attributes["ipv6_addresses"] = ipv6_addrs

        except Exception as e:
            logger.error(f"Failed to update network interface status {self.interface_name}: {e}")
            self.state = False
            self.attributes = {"error": str(e)}
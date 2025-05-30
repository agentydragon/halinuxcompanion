"""Network hardware class implementation."""

from __future__ import annotations

import logging
from typing import List, Optional

import psutil

from ..hardware_base import (
    HardwareClass,
    HardwarePiece,
    HardwareSensor,
    PerPieceUpdateMixin,
)
from ..hardware_config import NetworkConfig, SensorInfo

logger = logging.getLogger(__name__)


class NetworkInterfacePiece(HardwarePiece):
    """Represents a single network interface."""

    def __init__(self, hardware_id: str):
        super().__init__(hardware_id)
        self.status_sensor: Optional[HardwareSensor] = None
        self.tx_bytes_sensor: Optional[HardwareSensor] = None
        self.rx_bytes_sensor: Optional[HardwareSensor] = None
        self.ipv4_sensor: Optional[HardwareSensor] = None
        self.ipv6_sensor: Optional[HardwareSensor] = None

    async def update(self) -> None:
        """Update network interface data and push to sensors."""
        # Get interface statistics
        stats = psutil.net_if_stats().get(self.hardware_id)
        # Extract addresses and sort deterministically. 2 = AF_INET, 10 = AF_INET6
        addrs = psutil.net_if_addrs().get(self.hardware_id, [])
        ipv4_addrs = sorted(addr.address for addr in addrs if addr.family == 2)
        ipv6_addrs = sorted(addr.address for addr in addrs if addr.family == 10)
        io_counters = psutil.net_io_counters(pernic=True).get(self.hardware_id)
        for sensor, value in [
            (self.status_sensor, stats.isup if stats else None),
            (self.ipv4_sensor, ", ".join(ipv4_addrs) if ipv4_addrs else None),
            (self.ipv6_sensor, ", ".join(ipv6_addrs) if ipv6_addrs else None),
            (self.tx_bytes_sensor, io_counters.bytes_sent if io_counters else None),
            (self.rx_bytes_sensor, io_counters.bytes_recv if io_counters else None),
        ]:
            if sensor:
                sensor.attributes = {"interface": self.hardware_id}
                sensor.state = value

    def get_sensors(self) -> List[HardwareSensor]:
        """Get all sensors for this interface."""
        return list(
            filter(
                None,
                [
                    self.status_sensor,
                    self.tx_bytes_sensor,
                    self.rx_bytes_sensor,
                    self.ipv4_sensor,
                    self.ipv6_sensor,
                ],
            )
        )


class NetworkHardwareClass(PerPieceUpdateMixin, HardwareClass):
    hardware_class = "network"
    config_field = "network"

    def __init__(self, config: NetworkConfig):
        super().__init__(config)
        self.config: NetworkConfig = config  # Type hint for IDE

    async def discover_sensors(self) -> List[HardwareSensor]:
        """Discover configured network interfaces that exist on the system."""
        available_interfaces = set(psutil.net_if_stats().keys())
        configured = set(self.config.interfaces)
        if missing := configured - available_interfaces:
            logger.warning(
                f"Configured network interfaces not found on system: {'  '.join(sorted(missing))}"
            )
        for iface in configured & available_interfaces:
            piece = NetworkInterfacePiece(iface)

            def _sensor(
                sensor_type_name: str, sensor_info: SensorInfo
            ) -> HardwareSensor:
                return HardwareSensor(
                    hardware_class=self.hardware_class,
                    hardware_id=piece.hardware_id,
                    hardware_piece=piece,
                    sensor_type_name=sensor_type_name,
                    sensor_info=sensor_info,
                )

            if self.config.show_status:
                piece.status_sensor = _sensor(
                    "status",
                    SensorInfo(
                        type="binary_sensor", name="Status", device_class="connectivity"
                    ),
                )

            if self.config.show_counters:
                piece.tx_bytes_sensor = _sensor(
                    "tx_bytes",
                    SensorInfo(
                        name="TX Bytes",
                        unit="B",
                        device_class="data_size",
                        state_class="total_increasing",
                    ),
                )
                piece.rx_bytes_sensor = _sensor(
                    "rx_bytes",
                    SensorInfo(
                        name="RX Bytes",
                        unit="B",
                        device_class="data_size",
                        state_class="total_increasing",
                    ),
                )

            if self.config.show_ip_addresses:
                piece.ipv4_sensor = _sensor(
                    "ipv4_address",
                    SensorInfo(name="IPv4 Address", icon="mdi:ip-network"),
                )
                piece.ipv6_sensor = _sensor(
                    "ipv6_address",
                    SensorInfo(name="IPv6 Address", icon="mdi:ip-network"),
                )

        # Construct all_sensors at the end
        all_sensors = []
        for piece in self._hardware_pieces:
            all_sensors.extend(piece.get_sensors())

        return all_sensors

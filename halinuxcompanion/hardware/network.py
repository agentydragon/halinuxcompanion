"""Network hardware class implementation."""

from __future__ import annotations

import logging

import psutil

from ..hardware_base import (
    DeviceClass,
    HardwareClass,
    HardwarePiece,
    HardwareSensor,
    PerPieceUpdateMixin,
    StateClass,
)
from ..hardware_config import NetworkConfig

logger = logging.getLogger(__name__)


class NetworkInterfacePiece(HardwarePiece):
    """Represents a single network interface."""

    def __init__(
        self,
        hardware_id: str,
    ):
        super().__init__(hardware_id)
        self.status_sensor: HardwareSensor | None = None
        self.tx_bytes_sensor: HardwareSensor | None = None
        self.rx_bytes_sensor: HardwareSensor | None = None
        self.ipv4_sensor: HardwareSensor | None = None
        self.ipv6_sensor: HardwareSensor | None = None

    async def update(self) -> None:
        """Update network interface data and push to sensors."""
        # Get interface statistics
        stats = psutil.net_if_stats().get(self.hardware_id)
        # Extract addresses and sort deterministically. 2 = AF_INET, 10 = AF_INET6
        addrs = psutil.net_if_addrs().get(self.hardware_id, [])
        ipv4_addrs = sorted(a.address for a in addrs if a.family == 2)
        ipv6_addrs = sorted(a.address for a in addrs if a.family == 10)
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

    def get_sensors(self) -> list[HardwareSensor]:
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
    config_field = "network"

    def __init__(self, config: NetworkConfig):
        super().__init__(config)
        self.config: NetworkConfig = config  # Type hint for IDE

    async def discover_sensors(self) -> list[HardwareSensor]:
        """Discover configured network interfaces that exist on the system."""
        available_interfaces = set(psutil.net_if_stats().keys())
        configured = set(self.config.interfaces)
        if missing := configured - available_interfaces:
            logger.warning(f"Configured network interfaces not found on system: {'  '.join(sorted(missing))}")
        all_sensors = []
        for iface in configured & available_interfaces:
            piece = NetworkInterfacePiece(iface)
            self._hardware_pieces.append(piece)

            def _sensor(id, name, **kwargs):
                if len(available_interfaces) > 1:
                    name = f"{name} ({iface})"
                return HardwareSensor(
                    unique_id=f"net:{piece.hardware_id}:{id}",
                    name=name,
                    **kwargs,
                )

            if self.config.show_status:
                piece.status_sensor = _sensor(
                    id="status",
                    type="binary_sensor",
                    name="Status",
                    device_class=DeviceClass.CONNECTIVITY,
                )

            if self.config.show_counters:
                piece.tx_bytes_sensor = _sensor(
                    id="tx_bytes",
                    name="TX Bytes",
                    unit_of_measurement="B",
                    device_class=DeviceClass.DATA_SIZE,
                    state_class=StateClass.TOTAL_INCREASING,
                )
                piece.rx_bytes_sensor = _sensor(
                    id="rx_bytes",
                    name="RX Bytes",
                    unit_of_measurement="B",
                    device_class=DeviceClass.DATA_SIZE,
                    state_class=StateClass.TOTAL_INCREASING,
                )

            if self.config.show_ip_addresses:
                piece.ipv4_sensor = _sensor(
                    id="ipv4_address",
                    name="IPv4 Address",
                    icon="mdi:ip-network",
                )
                piece.ipv6_sensor = _sensor(
                    id="ipv6_address",
                    name="IPv6 Address",
                    icon="mdi:ip-network",
                )
            all_sensors.extend(piece.get_sensors())

        return all_sensors

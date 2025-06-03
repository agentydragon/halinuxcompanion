"""Network module implementation."""

from __future__ import annotations

import logging

import psutil

from ..module_base import BinarySensor, DeviceClass, Module, ModulePiece, PerPieceUpdateMixin, Sensor, StateClass
from ..module_config import NetworkConfig

logger = logging.getLogger(__name__)


class NetworkInterfacePiece(ModulePiece):
    """Represents a single network interface."""

    def __init__(
        self,
        module_id: str,
    ):
        super().__init__(module_id)
        self.status_sensor: Sensor | None = None
        self.tx_bytes_sensor: Sensor | None = None
        self.rx_bytes_sensor: Sensor | None = None
        self.ipv4_sensor: Sensor | None = None
        self.ipv6_sensor: Sensor | None = None

    async def update(self) -> None:
        """Update network interface data and push to sensors."""
        # Get interface statistics
        stats = psutil.net_if_stats().get(self.module_id)
        # Extract addresses and sort deterministically. 2 = AF_INET, 10 = AF_INET6
        addrs = psutil.net_if_addrs().get(self.module_id, [])
        ipv4_addrs = sorted(a.address for a in addrs if a.family == 2)
        ipv6_addrs = sorted(a.address for a in addrs if a.family == 10)
        io_counters = psutil.net_io_counters(pernic=True).get(self.module_id)
        for sensor, value in [
            (self.status_sensor, stats.isup if stats else None),
            (self.ipv4_sensor, ", ".join(ipv4_addrs) if ipv4_addrs else None),
            (self.ipv6_sensor, ", ".join(ipv6_addrs) if ipv6_addrs else None),
            (self.tx_bytes_sensor, io_counters.bytes_sent if io_counters else None),
            (self.rx_bytes_sensor, io_counters.bytes_recv if io_counters else None),
        ]:
            if sensor:
                sensor.attributes = {"interface": self.module_id}
                sensor.state = value

    def get_sensors(self) -> list[Sensor]:
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


class NetworkModule(PerPieceUpdateMixin, Module):
    def __init__(self, config: NetworkConfig):
        super().__init__(config)
        self.config: NetworkConfig = config  # Type hint for IDE

    async def discover_sensors(self) -> list[Sensor]:
        """Discover configured network interfaces that exist on the system."""
        available_interfaces = set(psutil.net_if_stats().keys())
        configured = set(self.config.interfaces)
        if missing := configured - available_interfaces:
            logger.warning(f"Configured network interfaces not found on system: {'  '.join(sorted(missing))}")
        all_sensors = []
        for iface in configured & available_interfaces:
            piece = NetworkInterfacePiece(iface)
            self._module_pieces.append(piece)

            def _name(name: str) -> str:
                if len(available_interfaces) > 1:
                    name = f"{name} ({iface})"
                return name

            def _sensor(id, name, **kwargs):
                return Sensor(
                    unique_id=f"net:{piece.module_id}:{id}",
                    name=_name(name),
                    **kwargs,
                )

            if self.config.show_status:
                piece.status_sensor = BinarySensor(
                    unique_id=f"net:{piece.module_id}:status",
                    name=_name("Status"),
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
                    state_class=None,  # IP addresses are text values, not numeric
                )
                piece.ipv6_sensor = _sensor(
                    id="ipv6_address",
                    name="IPv6 Address",
                    icon="mdi:ip-network",
                    state_class=None,  # IP addresses are text values, not numeric
                )
            all_sensors.extend(piece.get_sensors())

        return all_sensors

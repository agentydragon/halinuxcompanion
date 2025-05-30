"""Network hardware class implementation."""

from __future__ import annotations

import logging
from typing import List, Optional

import psutil

from ..hardware_base import (
    HardwareClass,
    HardwarePiece,
    HardwareProvider,
    PerPieceUpdateMixin,
    HardwareSensor,
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
        self.ipv4_address_sensor: Optional[HardwareSensor] = None
        self.ipv6_address_sensor: Optional[HardwareSensor] = None

    async def update(self) -> None:
        """Update network interface data and push to sensors."""
        # Get interface statistics
        stats = psutil.net_if_stats().get(self.hardware_id)
        io_counters = psutil.net_io_counters(pernic=True).get(self.hardware_id)
        addrs = psutil.net_if_addrs().get(self.hardware_id, [])

        if not stats or not io_counters:
            return

        # Extract addresses and sort deterministically
        ipv4_addresses = sorted(
            addr.address for addr in addrs if addr.family == 2
        )  # AF_INET
        ipv6_addresses = sorted(
            addr.address for addr in addrs if addr.family == 10
        )  # AF_INET6

        # Push data to sensors
        for sensor, value in [
            (self.status_sensor, stats.isup),
            (self.tx_bytes_sensor, io_counters.bytes_sent),
            (self.rx_bytes_sensor, io_counters.bytes_recv),
            (
                self.ipv4_address_sensor,
                ", ".join(ipv4_addresses) if ipv4_addresses else None,
            ),
            (
                self.ipv6_address_sensor,
                ", ".join(ipv6_addresses) if ipv6_addresses else None,
            ),
        ]:
            if sensor and value is not None:
                sensor.state = value
                sensor.attributes = {"interface": self.hardware_id}

    def get_sensors(self) -> List[HardwareSensor]:
        """Get all sensors for this interface."""
        return list(
            filter(
                None,
                [
                    self.status_sensor,
                    self.tx_bytes_sensor,
                    self.rx_bytes_sensor,
                    self.ipv4_address_sensor,
                    self.ipv6_address_sensor,
                ],
            )
        )


class NetworkProvider(HardwareProvider):
    """Network hardware provider."""

    def __init__(self, interfaces: List[str]):
        self._configured_interfaces = interfaces

    async def discover_hardware(self) -> List[HardwarePiece]:
        """Discover configured network interfaces that exist on the system."""
        available_interfaces = set(psutil.net_if_stats().keys())
        configured = set(self._configured_interfaces)

        # Log warnings for configured but non-existent interfaces
        if missing := configured - available_interfaces:
            logger.warning(
                f"Configured network interfaces not found on system: {', '.join(sorted(missing))}"
            )

        existing_interfaces = configured & available_interfaces
        pieces: List[HardwarePiece] = [
            NetworkInterfacePiece(iface) for iface in existing_interfaces
        ]
        return pieces


class NetworkHardwareClass(PerPieceUpdateMixin, HardwareClass):
    """Network hardware class."""

    hardware_class = "network"
    config_field = "network"

    def __init__(self, config: NetworkConfig):
        super().__init__(config)
        self.config: NetworkConfig = config  # Type hint for IDE
        self._hardware_pieces: list[NetworkInterfacePiece] = []  # type: ignore[assignment]

    async def get_provider(self) -> HardwareProvider:
        """Get the hardware provider."""
        if not self._provider:
            self._provider = NetworkProvider(self.config.interfaces)

        return self._provider

    async def discover_sensors(self) -> List[HardwareSensor]:
        """Discover and create sensors for network interfaces."""
        provider = await self.get_provider()
        pieces = await provider.discover_hardware()
        self._hardware_pieces = pieces

        for piece in pieces:
            # Get enabled sensors based on configuration
            enabled = set()
            if self.config.show_status:
                enabled |= {"status"}
            if self.config.show_counters:
                enabled |= {"tx_bytes", "rx_bytes"}
            if self.config.show_ip_addresses:
                enabled |= {"ipv4_address", "ipv6_address"}

            if "status" in enabled:
                piece.status_sensor = HardwareSensor(
                    hardware_class=self.hardware_class,
                    hardware_id=piece.hardware_id,
                    sensor_type_name="status",
                    sensor_info=SensorInfo(
                        type="binary_sensor", name="Status", device_class="connectivity"
                    ),
                    hardware_piece=piece,
                )

            if "tx_bytes" in enabled:
                piece.tx_bytes_sensor = HardwareSensor(
                    hardware_class=self.hardware_class,
                    hardware_id=piece.hardware_id,
                    sensor_type_name="tx_bytes",
                    sensor_info=SensorInfo(
                        name="TX Bytes",
                        unit="B",
                        device_class="data_size",
                        state_class="total_increasing",
                    ),
                    hardware_piece=piece,
                )

            if "rx_bytes" in enabled:
                piece.rx_bytes_sensor = HardwareSensor(
                    hardware_class=self.hardware_class,
                    hardware_id=piece.hardware_id,
                    sensor_type_name="rx_bytes",
                    sensor_info=SensorInfo(
                        name="RX Bytes",
                        unit="B",
                        device_class="data_size",
                        state_class="total_increasing",
                    ),
                    hardware_piece=piece,
                )

            if "ipv4_address" in enabled:
                piece.ipv4_address_sensor = HardwareSensor(
                    hardware_class=self.hardware_class,
                    hardware_id=piece.hardware_id,
                    sensor_type_name="ipv4_address",
                    sensor_info=SensorInfo(name="IPv4 Address", icon="mdi:ip-network"),
                    hardware_piece=piece,
                )

            if "ipv6_address" in enabled:
                piece.ipv6_address_sensor = HardwareSensor(
                    hardware_class=self.hardware_class,
                    hardware_id=piece.hardware_id,
                    sensor_type_name="ipv6_address",
                    sensor_info=SensorInfo(name="IPv6 Address", icon="mdi:ip-network"),
                    hardware_piece=piece,
                )

        # Construct all_sensors at the end
        all_sensors = []
        for piece in self._hardware_pieces:
            all_sensors.extend(piece.get_sensors())

        return all_sensors

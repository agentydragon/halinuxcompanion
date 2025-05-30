"""CPU hardware class implementation."""

from __future__ import annotations

import logging
from typing import List, Optional

import psutil

from ..hardware_base import (
    HardwareClass,
    HardwarePiece,
    HardwareProvider,
    HardwareSensor,
    PerPieceUpdateMixin,
)
from ..hardware_config import CPUConfig, SensorInfo

logger = logging.getLogger(__name__)


class CPUPiece(HardwarePiece):
    """Represents the CPU."""

    def __init__(self):
        super().__init__("cpu")
        self.usage_sensor: Optional[HardwareSensor] = None
        self.frequency_sensor: Optional[HardwareSensor] = None

    async def update(self) -> None:
        """Update CPU data and push to sensors."""
        # Use interval=0 for non-blocking call
        # This gives CPU usage since last call, which is good for periodic updates
        # For the first call, it may return 0.0
        usage = psutil.cpu_percent(interval=0)

        frequency = None
        if freq := psutil.cpu_freq():
            frequency = freq.current  # MHz

        # Push data to sensors
        for sensor, value in [
            (self.usage_sensor, usage),
            (self.frequency_sensor, frequency),
        ]:
            if sensor:
                sensor.state = value

    def get_sensors(self) -> List[HardwareSensor]:
        """Get all sensors for this piece."""
        return list(filter(None, [self.usage_sensor, self.frequency_sensor]))

    def get_available_sensors(self) -> set[str]:
        """Get set of available sensor types for CPU."""
        return {"usage_percent", "frequency"}


class CPUProvider(HardwareProvider):
    """CPU hardware provider."""

    async def discover_hardware(self) -> List[HardwarePiece]:
        """Discover CPU - always returns single CPU."""
        return [CPUPiece()]


class CPUHardwareClass(PerPieceUpdateMixin, HardwareClass):
    """CPU hardware class."""

    hardware_class = "cpu"
    config_field = "cpu"

    def __init__(self, config: CPUConfig):
        super().__init__(config)
        self.config: CPUConfig = config
        self._hardware_pieces: list[CPUPiece] = []  # type: ignore[assignment]

    async def get_provider(self) -> HardwareProvider:
        """Get the hardware provider."""
        if not self._provider:
            self._provider = CPUProvider()
        return self._provider

    async def discover_sensors(self) -> List[HardwareSensor]:
        """Discover and create sensors for CPU."""
        provider = await self.get_provider()
        pieces = await provider.discover_hardware()
        self._hardware_pieces = pieces

        # CPU is always a singleton
        piece = pieces[0]

        # Create usage sensor
        piece.usage_sensor = HardwareSensor(
            hardware_class=self.hardware_class,
            hardware_id=piece.hardware_id,
            sensor_type_name="usage_percent",
            sensor_info=SensorInfo(
                name="CPU Usage",
                unit="%",
                device_class=None,
                state_class="measurement",
                icon="mdi:cpu-64-bit",
            ),
            hardware_piece=piece,
        )

        # Create frequency sensor
        piece.frequency_sensor = HardwareSensor(
            hardware_class=self.hardware_class,
            hardware_id=piece.hardware_id,
            sensor_type_name="frequency",
            sensor_info=SensorInfo(
                name="CPU Frequency",
                unit="MHz",
                device_class="frequency",
                state_class="measurement",
                icon="mdi:speedometer",
            ),
            hardware_piece=piece,
        )

        return piece.get_sensors()

"""Memory hardware class implementation."""

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
from ..hardware_config import MemoryConfig, SensorInfo

logger = logging.getLogger(__name__)


class MemoryPiece(HardwarePiece):
    """Represents system memory."""

    def __init__(self):
        super().__init__("memory")
        self.usage_percent_sensor: Optional[HardwareSensor] = None
        self.used_sensor: Optional[HardwareSensor] = None
        self.available_sensor: Optional[HardwareSensor] = None

    async def update(self) -> None:
        """Update memory data and push to sensors."""
        mem = psutil.virtual_memory()

        # Push data to sensors
        for sensor, value in [
            (self.usage_percent_sensor, mem.percent),
            (self.used_sensor, mem.used),
            (self.available_sensor, mem.available),
        ]:
            if sensor:
                sensor.state = value

    def get_available_sensors(self) -> set[str]:
        """Get set of available sensor types for memory."""
        return {"usage_percent", "used", "available"}

    def get_sensors(self) -> List[HardwareSensor]:
        """Get all sensors for memory."""
        return list(
            filter(
                None,
                [
                    self.usage_percent_sensor,
                    self.used_sensor,
                    self.available_sensor,
                ],
            )
        )


class MemoryProvider(HardwareProvider):
    """Memory hardware provider."""

    async def discover_hardware(self) -> List[HardwarePiece]:
        """Discover memory - always returns single memory."""
        return [MemoryPiece()]


class MemoryHardwareClass(PerPieceUpdateMixin, HardwareClass):
    """Memory hardware class."""

    hardware_class = "memory"
    config_field = "memory"

    def __init__(self, config: MemoryConfig):
        super().__init__(config)
        self.config: MemoryConfig = config
        self._hardware_pieces: list[MemoryPiece] = []  # type: ignore[assignment]

    async def get_provider(self) -> HardwareProvider:
        return MemoryProvider()

    async def discover_sensors(self) -> List[HardwareSensor]:
        """Discover and create sensors for memory."""
        provider = await self.get_provider()
        pieces = await provider.discover_hardware()
        self._hardware_pieces = pieces

        # Memory is always a singleton
        piece = pieces[0]

        # Create usage sensor
        piece.usage_percent_sensor = HardwareSensor(
            hardware_class=self.hardware_class,
            hardware_id=piece.hardware_id,
            sensor_type_name="usage_percent",
            sensor_info=SensorInfo(
                name="Memory Usage",
                unit="%",
                state_class="measurement",
                icon="mdi:memory",
            ),
            hardware_piece=piece,
        )

        # Create used sensor
        piece.used_sensor = HardwareSensor(
            hardware_class=self.hardware_class,
            hardware_id=piece.hardware_id,
            sensor_type_name="used",
            sensor_info=SensorInfo(
                name="Memory Used",
                unit="B",
                device_class="data_size",
                state_class="measurement",
                icon="mdi:memory",
            ),
            hardware_piece=piece,
        )

        # Create available sensor
        piece.available_sensor = HardwareSensor(
            hardware_class=self.hardware_class,
            hardware_id=piece.hardware_id,
            sensor_type_name="available",
            sensor_info=SensorInfo(
                name="Memory Available",
                unit="B",
                device_class="data_size",
                state_class="measurement",
                icon="mdi:memory",
            ),
            hardware_piece=piece,
        )

        return piece.get_sensors()

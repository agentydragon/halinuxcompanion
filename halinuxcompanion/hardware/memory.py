"""Memory hardware class implementation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import partial
from typing import List

import psutil

from ..hardware_base import (
    HardwareClass,
    HardwarePiece,
    HardwareSensor,
    PerPieceUpdateMixin,
)
from ..hardware_config import MemoryConfig, SensorInfo

logger = logging.getLogger(__name__)


@dataclass
class MemoryPiece(HardwarePiece):
    """Represents system memory."""

    usage_percent_sensor: HardwareSensor
    used_sensor: HardwareSensor
    available_sensor: HardwareSensor

    def __init__(self):
        super().__init__("memory")

    async def update(self) -> None:
        """Update memory data and push to sensors."""
        mem = psutil.virtual_memory()
        self.usage_percent_sensor.state = mem.percent
        self.used_sensor.state = mem.used
        self.available_sensor.state = mem.available

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


class MemoryHardwareClass(PerPieceUpdateMixin, HardwareClass):
    """Memory hardware class."""

    hardware_class = "memory"
    config_field = "memory"

    def __init__(self, config: MemoryConfig):
        super().__init__(config)
        self.config: MemoryConfig = config

    async def discover_sensors(self) -> List[HardwareSensor]:
        """Discover and create sensors for memory."""
        # Memory is always a singleton
        piece = MemoryPiece()

        _sensor = partial(
            HardwareSensor,
            hardware_class=self.hardware_class,
            hardware_id=piece.hardware_id,
            hardware_piece=piece,
        )
        _bytes = partial(
            SensorInfo, device_class="data_size", state_class="measurement", unit="B"
        )

        # Create usage sensor
        piece.usage_percent_sensor = _sensor(
            sensor_type_name="usage_percent",
            sensor_info=SensorInfo(
                name="Memory Usage",
                unit="%",
                state_class="measurement",
                icon="mdi:memory",
            ),
        )
        piece.used_sensor = _sensor(
            sensor_type_name="used",
            sensor_info=_bytes(name="Memory Used", icon="mdi:memory"),
        )
        piece.available_sensor = _sensor(
            sensor_type_name="available",
            sensor_info=_bytes(name="Memory Available", icon="mdi:memory"),
        )
        return piece.get_sensors()

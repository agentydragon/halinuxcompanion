"""CPU hardware class implementation."""

from __future__ import annotations

import logging
from typing import List

import psutil

from ..hardware_base import (
    HardwareClass,
    HardwarePiece,
    HardwareSensor,
    PerPieceUpdateMixin,
)
from ..hardware_config import CPUConfig, SensorInfo

logger = logging.getLogger(__name__)


class CPUPiece(HardwarePiece):
    def __init__(self) -> None:
        super().__init__("cpu")
        self.usage_sensor: HardwareSensor | None = None
        self.frequency_sensor: HardwareSensor | None = None

    async def update(self) -> None:
        if self.usage_sensor:
            # Use interval=0 for non-blocking call. This gives CPU usage since last call,
            # which is good for periodic updates. For the first call, it may return 0.0.
            self.usage_sensor.state = psutil.cpu_percent(interval=0)

        if self.frequency_sensor and (freq := psutil.cpu_freq()):
            self.frequency_sensor.state = freq.current  # MHz

    def get_sensors(self) -> List[HardwareSensor]:
        """Get all sensors for this piece."""
        return list(filter(None, [self.usage_sensor, self.frequency_sensor]))


class CPUHardwareClass(PerPieceUpdateMixin, HardwareClass):
    hardware_class = "cpu"
    config_field = "cpu"

    def __init__(self, config: CPUConfig):
        super().__init__(config)
        self.config: CPUConfig = config

    async def discover_sensors(self) -> List[HardwareSensor]:
        """Discover and create sensors for CPU."""
        piece = CPUPiece()
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

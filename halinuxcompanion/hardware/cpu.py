"""CPU hardware class implementation."""

from __future__ import annotations

import logging

import psutil

from ..hardware_base import (
    DeviceClass,
    HardwareClass,
    HardwareSensor,
    PerPieceUpdateMixin,
    StateClass,
)
from ..hardware_config import CPUConfig

logger = logging.getLogger(__name__)


class CPUHardwareClass(PerPieceUpdateMixin, HardwareClass):
    config_field = "cpu"

    def __init__(self, config: CPUConfig):
        super().__init__(config)
        self.config: CPUConfig = config
        self.usage_sensor = HardwareSensor(
            unique_id="cpu:usage_percent",
            name="CPU Usage",
            unit_of_measurement="%",
            device_class=None,
            state_class=StateClass.MEASUREMENT,
            icon="mdi:cpu-64-bit",
        )
        self.frequency_sensor = HardwareSensor(
            unique_id="cpu:frequency",
            name="CPU Frequency",
            unit_of_measurement="MHz",
            device_class=DeviceClass.FREQUENCY,
            state_class=StateClass.MEASUREMENT,
            icon="mdi:speedometer",
        )

    async def discover_sensors(self) -> list[HardwareSensor]:
        """Discover and create sensors for CPU."""
        return [self.usage_sensor, self.frequency_sensor]

    async def update_all_sensors(self) -> None:
        # Use interval=0 for non-blocking call. This gives CPU usage since last call,
        # which is good for periodic updates. For the first call, it may return 0.0.
        self.usage_sensor.state = psutil.cpu_percent(interval=0)
        self.frequency_sensor.state = freq.current if (freq := psutil.cpu_freq()) else None  # MHz

    def get_sensors(self) -> list[HardwareSensor]:
        return [self.usage_sensor, self.frequency_sensor]

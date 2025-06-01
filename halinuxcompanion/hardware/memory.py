"""Memory hardware class implementation."""

from __future__ import annotations

import logging

import psutil

from ..hardware_base import DeviceClass, HardwareClass, HardwareSensor, StateClass
from ..hardware_config import MemoryConfig

logger = logging.getLogger(__name__)


class MemoryHardwareClass(HardwareClass):
    """Memory hardware class."""

    config_field = "memory"

    def __init__(self, config: MemoryConfig):
        super().__init__(config)
        self.config: MemoryConfig = config
        self.usage_percent_sensor = HardwareSensor(
            unique_id="memory:usage_percent",
            name="Memory Usage",
            unit_of_measurement="%",
            state_class=StateClass.MEASUREMENT,
            icon="mdi:memory",
        )
        self.used_sensor = HardwareSensor(
            unique_id="memory:used",
            name="Memory Used",
            icon="mdi:memory",
            state_class=StateClass.MEASUREMENT,
            unit_of_measurement="B",
            device_class=DeviceClass.DATA_SIZE,
        )
        self.available_sensor = HardwareSensor(
            unique_id="memory:available",
            name="Memory Available",
            icon="mdi:memory",
            state_class=StateClass.MEASUREMENT,
            unit_of_measurement="B",
            device_class=DeviceClass.DATA_SIZE,
        )

    async def update_all_sensors(self) -> None:
        mem = psutil.virtual_memory()
        self.usage_percent_sensor.state = mem.percent
        self.used_sensor.state = mem.used
        self.available_sensor.state = mem.available

    async def discover_sensors(self) -> list[HardwareSensor]:
        """Discover all sensors for memory."""
        return [
            self.usage_percent_sensor,
            self.used_sensor,
            self.available_sensor,
        ]

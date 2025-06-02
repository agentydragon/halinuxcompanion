"""Memory module implementation."""

from __future__ import annotations

import logging

import psutil

from ...module_base import DeviceClass, Module, Sensor, StateClass
from ...module_config import MemoryConfig

logger = logging.getLogger(__name__)


class MemoryModule(Module):
    """Memory module."""

    def __init__(self, config: MemoryConfig):
        super().__init__(config)
        self.config: MemoryConfig = config
        self.usage_percent_sensor = Sensor(
            unique_id="memory:usage_percent",
            name="Memory Usage",
            unit_of_measurement="%",
            state_class=StateClass.MEASUREMENT,
            icon="mdi:memory",
        )
        self.used_sensor = Sensor(
            unique_id="memory:used",
            name="Memory Used",
            icon="mdi:memory",
            state_class=StateClass.MEASUREMENT,
            unit_of_measurement="B",
            device_class=DeviceClass.DATA_SIZE,
        )
        self.available_sensor = Sensor(
            unique_id="memory:available",
            name="Memory Available",
            icon="mdi:memory",
            state_class=StateClass.MEASUREMENT,
            unit_of_measurement="B",
            device_class=DeviceClass.DATA_SIZE,
        )

    async def update_all_sensors(self) -> None:
        try:
            mem = psutil.virtual_memory()
            self.usage_percent_sensor.set_ok(mem.percent)
            self.used_sensor.set_ok(mem.used)
            self.available_sensor.set_ok(mem.available)
        except (OSError, RuntimeError) as e:
            self.usage_percent_sensor.set_error(e, "Failed to read memory info")
            self.used_sensor.set_error(e, "Failed to read memory info")
            self.available_sensor.set_error(e, "Failed to read memory info")

    async def discover_sensors(self) -> list[Sensor]:
        """Discover all sensors for memory."""
        return [
            self.usage_percent_sensor,
            self.used_sensor,
            self.available_sensor,
        ]

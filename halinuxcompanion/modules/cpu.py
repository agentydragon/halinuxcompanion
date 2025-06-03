"""CPU module implementation."""

from __future__ import annotations

import logging

import psutil

from ..module_base import DeviceClass, Module, PerPieceUpdateMixin, Sensor, StateClass
from ..module_config import CPUConfig

logger = logging.getLogger(__name__)


class CPUModule(PerPieceUpdateMixin, Module):
    def __init__(self, config: CPUConfig):
        super().__init__(config)
        self.config: CPUConfig = config
        self.usage_sensor = Sensor(
            unique_id="cpu:usage_percent",
            name="CPU Usage",
            unit_of_measurement="%",
            device_class=None,
            state_class=StateClass.MEASUREMENT,
            icon="mdi:cpu-64-bit",
        )
        self.frequency_sensor = Sensor(
            unique_id="cpu:frequency",
            name="CPU Frequency",
            unit_of_measurement="MHz",
            device_class=DeviceClass.FREQUENCY,
            state_class=StateClass.MEASUREMENT,
            icon="mdi:speedometer",
        )

    async def discover_sensors(self) -> list[Sensor]:
        """Discover and create sensors for CPU."""
        return [self.usage_sensor, self.frequency_sensor]

    async def update_all_sensors(self) -> None:
        try:
            # Use interval=0 for non-blocking call. This gives CPU usage since last call,
            # which is good for periodic updates. For the first call, it may return 0.0.
            self.usage_sensor.set_ok(psutil.cpu_percent(interval=0))
        except (OSError, RuntimeError) as e:
            self.usage_sensor.set_error(e, "Failed to read CPU usage")

        try:
            freq = psutil.cpu_freq()
            self.frequency_sensor.set_ok(freq.current if freq else None)  # MHz
        except (OSError, RuntimeError) as e:
            self.frequency_sensor.set_error(e, "Failed to read CPU frequency")

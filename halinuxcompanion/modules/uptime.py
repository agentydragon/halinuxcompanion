"""Uptime module implementation."""

from __future__ import annotations

import logging
import time

import psutil

from ...module_base import (
    DeviceClass,
    Module,
    PerPieceUpdateMixin,
    Sensor,
    StateClass,
)
from ...module_config import UptimeConfig

logger = logging.getLogger(__name__)


class UptimeModule(PerPieceUpdateMixin, Module):
    """Uptime module."""

    def __init__(self, config: UptimeConfig):
        super().__init__(config)
        self.config: UptimeConfig = config
        self.sensor = Sensor(
            unique_id="uptime",
            name="Uptime",
            unit_of_measurement="s",
            device_class=DeviceClass.DURATION,
            state_class=StateClass.TOTAL_INCREASING,
            icon="mdi:clock-outline",
        )

    async def discover_sensors(self) -> list[Sensor]:
        return [self.sensor]

    async def update_all_sensors(self) -> None:
        try:
            self.sensor.set_ok(time.time() - psutil.boot_time())
        except (OSError, RuntimeError) as e:
            self.sensor.set_error(e, "Failed to read boot time")

"""Uptime hardware class implementation."""

from __future__ import annotations

import logging
import time

import psutil

from ..hardware_base import (
    DeviceClass,
    HardwareClass,
    HardwareSensor,
    PerPieceUpdateMixin,
    StateClass,
)
from ..hardware_config import UptimeConfig

logger = logging.getLogger(__name__)


class UptimeHardwareClass(PerPieceUpdateMixin, HardwareClass):
    """Uptime hardware class."""

    config_field = "uptime"

    def __init__(self, config: UptimeConfig):
        super().__init__(config)
        self.config: UptimeConfig = config
        self.sensor = HardwareSensor(
            unique_id="uptime",
            name="Uptime",
            unit_of_measurement="s",
            device_class=DeviceClass.DURATION,
            state_class=StateClass.TOTAL_INCREASING,
            icon="mdi:clock-outline",
        )

    async def discover_sensors(self) -> list[HardwareSensor]:
        return [self.sensor]

    async def update_all_sensors(self) -> None:
        self.sensor.state = int(time.time() - psutil.boot_time())

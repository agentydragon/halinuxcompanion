"""Uptime hardware class implementation."""

from __future__ import annotations

import logging
import time
from typing import List

import psutil

from ..hardware_base import (
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
            unit="s",
            device_class="duration",
            state_class=StateClass.TOTAL_INCREASING,
            icon="mdi:clock-outline",
        )

    async def discover_sensors(self) -> List[HardwareSensor]:
        return [self.sensor]

    async def update_all_sensors(self) -> None:
        self.sensor.state = int(time.time() - psutil.boot_time())

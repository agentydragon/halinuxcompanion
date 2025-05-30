"""Uptime hardware class implementation."""

from __future__ import annotations

import logging
import time
from typing import List, Optional

import psutil

from ..hardware_base import (
    HardwareClass,
    HardwarePiece,
    HardwareSensor,
    PerPieceUpdateMixin,
)
from ..hardware_config import SensorInfo, UptimeConfig

logger = logging.getLogger(__name__)


class UptimePiece(HardwarePiece):
    """Represents system uptime."""

    def __init__(self) -> None:
        super().__init__("uptime")
        self.sensor: Optional[HardwareSensor] = None

    async def update(self) -> None:
        """Update uptime."""
        boot_time = psutil.boot_time()
        current_time = time.time()
        uptime_seconds = int(current_time - boot_time)

        if self.sensor:
            self.sensor.state = uptime_seconds

    def get_sensors(self) -> List[HardwareSensor]:
        """Get list of sensors."""
        return list(filter(None, [self.sensor]))


class UptimeHardwareClass(PerPieceUpdateMixin, HardwareClass):
    """Uptime hardware class."""

    hardware_class = "uptime"
    config_field = "uptime"

    def __init__(self, config: UptimeConfig):
        super().__init__(config)
        self.config: UptimeConfig = config
        self._hardware_pieces: list[UptimePiece] = []  # type: ignore[assignment]

    async def discover_sensors(self) -> List[HardwareSensor]:
        """Discover available sensors."""
        uptime = UptimePiece()
        self._hardware_pieces = [uptime]
        uptime.sensor = HardwareSensor(
            hardware_class=self.hardware_class,
            hardware_id=uptime.hardware_id,
            sensor_type_name="total_seconds",
            sensor_info=SensorInfo(
                name="Uptime",
                unit="s",
                device_class="duration",
                state_class="total_increasing",
                icon="mdi:clock-outline",
            ),
            hardware_piece=uptime,
        )
        return uptime.get_sensors()

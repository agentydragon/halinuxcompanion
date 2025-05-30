"""Uptime hardware class implementation."""

from __future__ import annotations

import logging
import time
from typing import List, Optional

import psutil

from ..hardware_base import (
    HardwareClass,
    HardwarePiece,
    HardwareProvider,
    HardwareSensor,
    PerPieceUpdateMixin,
)
from ..hardware_config import SensorInfo, UptimeConfig

logger = logging.getLogger(__name__)


class UptimePiece(HardwarePiece):
    """Represents system uptime."""

    def __init__(self):
        super().__init__("uptime")
        self.total_seconds_sensor: Optional[HardwareSensor] = None

    async def update(self) -> None:
        """Update uptime."""
        boot_time = psutil.boot_time()
        current_time = time.time()
        uptime_seconds = int(current_time - boot_time)

        if self.total_seconds_sensor:
            self.total_seconds_sensor.state = uptime_seconds

    def get_sensors(self) -> List[HardwareSensor]:
        """Get list of sensors."""
        return list(filter(None, [self.total_seconds_sensor]))


class UptimeProvider(HardwareProvider):
    """Uptime hardware provider."""

    async def discover_hardware(self) -> List[HardwarePiece]:
        """Discover uptime - always returns single instance."""
        return [UptimePiece()]


class UptimeHardwareClass(PerPieceUpdateMixin, HardwareClass):
    """Uptime hardware class."""

    hardware_class = "uptime"
    config_field = "uptime"

    def __init__(self, config: UptimeConfig):
        super().__init__(config)
        self.config: UptimeConfig = config
        self._hardware_pieces: list[UptimePiece] = []  # type: ignore[assignment]

    async def get_provider(self) -> HardwareProvider:
        return UptimeProvider()

    async def discover_sensors(self) -> List[HardwareSensor]:
        """Discover available sensors."""
        provider = await self.get_provider()
        pieces = await provider.discover_hardware()
        self._hardware_pieces = pieces

        if not pieces:
            return []

        # Uptime is a singleton
        piece = pieces[0]

        piece.total_seconds_sensor = HardwareSensor(
            hardware_class=self.hardware_class,
            hardware_id=piece.hardware_id,
            sensor_type_name="total_seconds",
            sensor_info=SensorInfo(
                name="Uptime",
                unit="s",
                device_class="duration",
                state_class="total_increasing",
                icon="mdi:clock-outline",
            ),
            hardware_piece=piece,
        )

        return piece.get_sensors()

"""Uptime hardware class implementation."""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, List, Optional

import psutil

from ..hardware_base import HardwareClass, HardwarePiece, HardwareProvider, PerPieceUpdateMixin
from ..hardware_config import UptimeConfig, SensorInfo

logger = logging.getLogger(__name__)


@dataclass
class UptimeData:
    """Uptime sensor data."""
    total_seconds: int
    boot_time: str  # ISO format


class UptimePiece(HardwarePiece[UptimeData]):
    """Represents system uptime."""
    
    def __init__(self):
        super().__init__("uptime")
    
    async def _fetch_sensor_data(self) -> Optional[UptimeData]:
        """Fetch fresh uptime data."""
        boot_time = psutil.boot_time()
        current_time = time.time()
        uptime_seconds = int(current_time - boot_time)
        
        return UptimeData(
            total_seconds=uptime_seconds,
            boot_time=datetime.fromtimestamp(boot_time, timezone.utc).isoformat()
        )
    
    def get_available_sensors(self) -> set[str]:
        """Get set of available sensor types."""
        return {"uptime"}
    
    def extract_sensor_value(self, data: UptimeData, sensor_type: str) -> Any:
        """Extract sensor value from uptime data."""
        if sensor_type == "uptime":
            return data.total_seconds
        return None


class UptimeProvider(HardwareProvider):
    """Uptime hardware provider."""
    
    async def discover_hardware(self) -> List[HardwarePiece]:
        """Discover uptime - always returns single instance."""
        return [UptimePiece()]


class UptimeHardwareClass(PerPieceUpdateMixin, HardwareClass):
    """Uptime hardware class."""
    
    hardware_name = "uptime"
    sensor_definitions = {
        "uptime": SensorInfo(
            name="Uptime",
            icon="mdi:clock-outline"
        )
    }
    
    def __init__(self, config: UptimeConfig):
        super().__init__(config)
        self.config: UptimeConfig = config
    
    async def get_provider(self) -> HardwareProvider:
        """Get the hardware provider."""
        if not self._provider:
            self._provider = UptimeProvider()
        return self._provider
    
    def get_enabled_sensors(self, available_sensors: set[str]) -> set[str]:
        # Always enable uptime sensor
        return available_sensors
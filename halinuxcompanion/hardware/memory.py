"""Memory hardware class implementation."""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

import psutil

from ..hardware_base import HardwareClass, HardwarePiece, HardwareProvider, PerPieceUpdateMixin
from ..hardware_config import MemoryConfig, MEMORY_SENSORS

logger = logging.getLogger(__name__)


@dataclass
class MemoryData:
    """Memory sensor data."""
    usage_percent: float
    used: int  # bytes
    available: int  # bytes


class MemoryPiece(HardwarePiece[MemoryData]):
    """Represents system memory."""
    
    def __init__(self):
        super().__init__("memory")
    
    async def _fetch_sensor_data(self) -> Optional[MemoryData]:
        """Fetch fresh sensor data for memory."""
        mem = psutil.virtual_memory()
        
        return MemoryData(
            usage_percent=mem.percent,
            used=mem.used,
            available=mem.available
        )
    
    def get_available_sensors(self) -> set[str]:
        """Get set of available sensor types for memory."""
        return set(MEMORY_SENSORS.keys())
    
    def extract_sensor_value(self, data: MemoryData, sensor_type: str) -> Any:
        """Extract a specific sensor value from memory data."""
        mapping = {
            "usage_percent": data.usage_percent,
            "used": data.used,
            "available": data.available,
        }
        return mapping.get(sensor_type)


class MemoryProvider(HardwareProvider):
    """Memory hardware provider."""
    
    async def discover_hardware(self) -> List[HardwarePiece]:
        """Discover memory - always returns single memory."""
        return [MemoryPiece()]


class MemoryHardwareClass(PerPieceUpdateMixin, HardwareClass):
    """Memory hardware class."""
    
    hardware_name = "memory"
    sensor_definitions = MEMORY_SENSORS
    
    def __init__(self, config: MemoryConfig):
        super().__init__(config)
        self.config: MemoryConfig = config
    
    async def get_provider(self) -> HardwareProvider:
        """Get the hardware provider."""
        if not self._provider:
            self._provider = MemoryProvider()
        return self._provider
    
    def get_enabled_sensors(self, available_sensors: set[str]) -> set[str]:
        # All memory sensors are always enabled
        return available_sensors
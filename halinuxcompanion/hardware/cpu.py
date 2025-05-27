"""CPU hardware class implementation."""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

import psutil

from ..hardware_base import HardwareClass, HardwarePiece, HardwareProvider, PerPieceUpdateMixin
from ..hardware_config import CPUConfig, CPU_SENSORS

logger = logging.getLogger(__name__)


@dataclass
class CPUData:
    """CPU sensor data."""
    usage_percent: float
    frequency: Optional[float]


class CPUPiece(HardwarePiece[CPUData]):
    """Represents the CPU."""
    
    def __init__(self):
        super().__init__("cpu")
        self.sensors: List[HardwareSensor] = []
    
    async def update(self) -> None:
        """Update CPU data and push to sensors."""
        # Use interval=0 for non-blocking call
        # This gives CPU usage since last call, which is good for periodic updates
        # For the first call, it may return 0.0
        usage = psutil.cpu_percent(interval=0)
        
        frequency = None
        if freq := psutil.cpu_freq():
            frequency = freq.current  # MHz
        
        data = CPUData(usage_percent=usage, frequency=frequency)
        
        # Push data to sensors
        for sensor in self.sensors:
            if sensor.sensor_type_name == "usage_percent":
                sensor.state = data.usage_percent
            elif sensor.sensor_type_name == "frequency":
                sensor.state = data.frequency
    
    def get_available_sensors(self) -> set[str]:
        """Get set of available sensor types for CPU."""
        return {"usage_percent", "frequency"}


class CPUProvider(HardwareProvider):
    """CPU hardware provider."""
    
    async def discover_hardware(self) -> List[HardwarePiece]:
        """Discover CPU - always returns single CPU."""
        return [CPUPiece()]


class CPUHardwareClass(PerPieceUpdateMixin, HardwareClass):
    """CPU hardware class."""
    
    hardware_name = "cpu"
    sensor_definitions = CPU_SENSORS
    
    def __init__(self, config: CPUConfig):
        super().__init__(config)
        self.config: CPUConfig = config
    
    async def get_provider(self) -> HardwareProvider:
        """Get the hardware provider."""
        if not self._provider:
            self._provider = CPUProvider()
        return self._provider
    
    def get_enabled_sensors(self, available_sensors: set[str]) -> set[str]:
        # Always enable both usage and frequency
        return available_sensors
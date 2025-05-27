"""Temperature hardware class implementation."""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import psutil

from ..hardware_base import HardwareClass, HardwarePiece, HardwareProvider, HardwareSensor
from ..hardware_config import TemperatureConfig, SensorInfo

logger = logging.getLogger(__name__)


@dataclass
class TemperatureData:
    """Temperature sensor data."""
    temperature: float
    max_threshold: Optional[float] = None
    critical_threshold: Optional[float] = None
    
    @property
    def max_threshold_reached(self) -> bool:
        """Check if max threshold is reached."""
        return self.max_threshold is not None and self.temperature >= self.max_threshold
    
    @property
    def critical_threshold_reached(self) -> bool:
        """Check if critical threshold is reached."""
        return self.critical_threshold is not None and self.temperature >= self.critical_threshold


class TemperaturePiece(HardwarePiece[TemperatureData]):
    """Represents a temperature sensor."""
    
    def __init__(self, hardware_id: str, chip_name: str, label: str):
        super().__init__(hardware_id)
        self.chip_name = chip_name
        self.label = label
    
    async def _fetch_sensor_data(self) -> Optional[TemperatureData]:
        """Fetch fresh temperature data.
        
        Note: For temperature sensors, this is not used.
        Temperature data is populated via bulk update in the hardware class.
        """
        # Temperature uses bulk update pattern
        return self._cached_data
    
    def get_available_sensors(self) -> set[str]:
        """Get set of available sensor types."""
        return {"temperature"}
    
    def extract_sensor_value(self, data: TemperatureData, sensor_type: str) -> Any:
        """Extract a specific sensor value from temperature data."""
        if sensor_type == "temperature":
            return data.temperature
        return None


class TemperatureProvider(HardwareProvider):
    """Temperature hardware provider."""
    
    async def discover_hardware(self) -> List[HardwarePiece]:
        """Discover available temperature sensors."""
        pieces_by_key: Dict[Tuple[str, str], TemperaturePiece] = {}
        
        temps = psutil.sensors_temperatures()
        if not temps:
            logger.debug("No temperature sensors found")
            return []
        
        for chip_name, chip_temps in temps.items():
            for temp in chip_temps:
                key = (chip_name, temp.label)
                if key not in pieces_by_key:
                    hardware_id = f"{chip_name}_{temp.label}" if temp.label else chip_name
                    pieces_by_key[key] = TemperaturePiece(hardware_id, chip_name, temp.label)
        
        pieces = list(pieces_by_key.values())
        labels = [f"{p.chip_name}:{p.label or 'unlabeled'}" for p in pieces]
        logger.debug(f"Discovered {len(pieces)} temperature sensors: {', '.join(labels)}")
        
        return pieces


class TemperatureHardwareClass(HardwareClass):
    """Temperature hardware class with bulk update support."""
    
    hardware_name = "temperature"
    sensor_definitions = {
        "temperature": SensorInfo(
            name="Temperature",
            unit="°C",
            device_class="temperature",
            state_class="measurement",
            icon="mdi:thermometer"
        )
    }
    
    def __init__(self, config: TemperatureConfig):
        super().__init__(config)
        self.config: TemperatureConfig = config
        # Index pieces by (chip_name, label) for efficient lookup
        self._piece_index: Dict[Tuple[str, str], TemperaturePiece] = {}
    
    async def get_provider(self) -> HardwareProvider:
        """Get the hardware provider."""
        if not self._provider:
            self._provider = TemperatureProvider()
        return self._provider
    
    def get_enabled_sensors(self, available_sensors: set[str]) -> set[str]:
        # Always enable temperature sensor
        return available_sensors
    
    async def discover_sensors(self) -> List[HardwareSensor]:
        """Discover all sensors and build piece index."""
        sensors = await super().discover_sensors()
        
        # Build index for efficient lookup during bulk updates
        self._piece_index.clear()
        for sensor in sensors:
            piece = sensor._hardware_piece
            key = (piece.chip_name, piece.label)
            self._piece_index[key] = piece
        
        return sensors
    
    async def update_all_sensors(self) -> None:
        """Bulk update all temperature sensors in one read."""
        # Update data for each temperature reading
        for chip_name, chip_temps in psutil.sensors_temperatures().items():
            for temp in chip_temps:
                if not (piece := self._piece_index.get((chip_name, temp.label))):
                    # TODO: This means a new temperature sensor appeared and should probably be added to HA
                    continue
                
                piece._cached_data = TemperatureData(
                    temperature=temp.current,
                    max_threshold=temp.high,
                    critical_threshold=temp.critical
                )
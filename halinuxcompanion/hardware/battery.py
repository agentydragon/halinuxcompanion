"""Battery hardware class implementation."""

import logging
from typing import Dict, List, Optional, Any

from ..hardware_base import HardwareClass, HardwarePiece, HardwareProvider
from ..hardware_config import BatteryConfig, BATTERY_SENSORS
from ..sensors.battery.battery_provider import BatteryDataProvider, BatteryData
from ..sensors.battery.battery_provider_psutil import PsutilBatteryProvider
from ..sensors.battery.battery_provider_upower import UPowerBatteryProvider

logger = logging.getLogger(__name__)


class BatteryPiece(HardwarePiece[BatteryData]):
    """Represents a single battery."""
    
    def __init__(self, hardware_id: str, provider: BatteryDataProvider):
        super().__init__(hardware_id)
        self._provider = provider
        self._battery_data: Optional[BatteryData] = None
    
    async def _fetch_sensor_data(self) -> Optional[BatteryData]:
        """Fetch fresh sensor data for this battery."""
        return await self._provider.get_battery_data(self.hardware_id)
    
    def get_available_sensors(self) -> set[str]:
        """Get set of available sensor types for this battery."""
        # For psutil, only basic sensors are available
        if isinstance(self._provider, PsutilBatteryProvider):
            return {"charge_level", "charging_state", "time_to_empty"}
        
        # For upower, all sensors are potentially available
        # (actual availability depends on what the battery reports)
        return set(BATTERY_SENSORS.keys())
    
    def extract_sensor_value(self, data: BatteryData, sensor_type: str) -> Any:
        """Extract a specific sensor value from battery data."""
        # Map sensor types to BatteryData attributes
        mapping = {
            "charge_level": data.percent,
            "charging_state": data.state,
            "time_to_empty": data.time_to_empty,
            "time_to_full": data.time_to_full,
            "temperature": data.temperature,
            "voltage": data.voltage,
            "charge_rate": data.charge_rate,
            "discharge_rate": data.discharge_rate,
            "charge_cycles": data.charge_cycles,
            "energy": data.energy,
            "energy_full": data.energy_full,
            "health": data.capacity,
        }
        
        return mapping.get(sensor_type)


class BatteryProvider(HardwareProvider):
    """Battery hardware provider."""
    
    def __init__(self, data_provider: BatteryDataProvider):
        self._data_provider = data_provider
    
    async def discover_hardware(self) -> List[HardwarePiece]:
        """Discover available batteries."""
        battery_ids = await self._data_provider.discover_batteries()
        return [BatteryPiece(battery_id, self._data_provider) for battery_id in battery_ids]


class BatteryHardwareClass(PerPieceUpdateMixin, HardwareClass):
    """Battery hardware class."""
    
    hardware_name = "battery"
    sensor_definitions = BATTERY_SENSORS
    
    def __init__(self, config: BatteryConfig):
        super().__init__(config)
        self.config: BatteryConfig = config  # Type hint for IDE
    
    async def get_provider(self) -> HardwareProvider:
        """Get the hardware provider based on configuration."""
        if not self._provider:
            # Create data provider based on implementation choice
            if self.config.implementation == "upower":
                data_provider = UPowerBatteryProvider()
            else:
                data_provider = PsutilBatteryProvider()
            
            self._provider = BatteryProvider(data_provider)
        
        return self._provider
    
    def get_enabled_sensors(self, available_sensors: set[str]) -> set[str]:
        # All available sensors are enabled for batteries
        return available_sensors
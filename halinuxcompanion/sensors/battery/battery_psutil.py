"""Battery sensors using psutil."""

import logging
from typing import Any, Dict, List, Optional

from halinuxcompanion.sensor_base import BaseSensor
from .battery_provider import BatteryData, BatteryDataProvider
from .battery_provider_psutil import PsutilBatteryProvider
from . import subsensors

logger = logging.getLogger(__name__)


class PSUtilSensor(BaseSensor):
    """Battery percentage sensor using psutil."""

    config_name = "battery_psutil"

    def __init__(self, provider: BatteryDataProvider, battery_data: BatteryData):
        super().__init__(
            instance_id=battery_data.battery_id,
            unique_id=f"battery_psutil_{battery_data.battery_id}",
            name=battery_data.name,
            device_class="battery",
            unit_of_measurement="%",
            state_class="measurement",
        )
        self._provider = provider
        self._battery_id = battery_data.battery_id
        self._battery_data = battery_data

    @classmethod
    async def discover_sensors(cls, config: Optional[Dict[str, Any]] = None) -> List["PSUtilSensor"]:
        """Discover battery sensors."""
        provider = PsutilBatteryProvider()
        battery_ids = await provider.discover_batteries()

        sensors = []
        for battery_id in battery_ids:
            battery_data = await provider.get_battery_data(battery_id)
            if battery_data:
                sensors.append(cls(provider, battery_data))

        return sensors

    def get_metadata(self):
        """Get sensor metadata with dynamic icon."""
        metadata = super().get_metadata()

        # Update icon based on battery data
        if self._battery_data:
            metadata.icon = self._battery_data.get_icon()

        return metadata

    async def update(self) -> None:
        """Update battery state."""
        self._battery_data = await self._provider.get_battery_data(self._battery_id)

        if self._battery_data:
            self.state = self._battery_data.percent
            self.attributes = {
                "power_plugged": self._battery_data.plugged,
                "battery_state": self._battery_data.state,
            }
            # Add time to empty if available
            if self._battery_data.time_to_empty:
                self.attributes["seconds_to_empty"] = self._battery_data.time_to_empty
        else:
            self.state = "unavailable"
            self.attributes = {}


# Create wrapper class for psutil time to empty subsensor
class PSUtilTimeToEmptySensor(subsensors.TimeToEmptySensor):
    config_name = "battery_psutil_time_to_empty"

    @classmethod
    async def discover_sensors(cls, config=None):
        provider = PsutilBatteryProvider()
        battery_ids = await provider.discover_batteries()

        sensors = []
        for battery_id in battery_ids:
            battery_data = await provider.get_battery_data(battery_id)
            if battery_data:
                sensors.append(cls(provider, battery_data))

        return sensors
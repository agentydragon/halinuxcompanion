"""Battery state sensor implementation."""

import logging
from typing import List

import psutil

from ..sensor_base import BaseSensor, SensorMetadata
from .battery_level import format_seconds_to_time

logger = logging.getLogger(__name__)


class BatteryStateSensor(BaseSensor):
    """Battery charging state sensor."""

    config_name = "battery_state"

    def __init__(self, battery_id: str = ""):
        """Initialize battery state sensor.

        Args:
            battery_id: Battery identifier (e.g., "BAT0")
        """
        super().__init__(battery_id)

    def get_metadata(self) -> SensorMetadata:
        """Get battery state sensor metadata."""
        return SensorMetadata(
            unique_id=f"battery_state_{self.instance_id}" if self.instance_id else "battery_state",
            name=f"Battery State ({self.instance_id})" if self.instance_id else "Battery State",
            config_name=self.config_name,
            device_class="battery_charging",
            icon="mdi:battery-charging",
        )

    @classmethod
    async def discover_sensors(cls) -> List["BatteryStateSensor"]:
        """Discover available batteries on the system."""
        sensors = []

        # Check if the system has a battery
        battery = psutil.sensors_battery()
        if battery is not None:
            sensors.append(cls())

        return sensors

    async def update(self) -> None:
        """Update battery charging state."""
        battery = psutil.sensors_battery()

        if battery is None:
            self.state = "unavailable"
            self.attributes = {}
            return

        # Determine state
        if battery.power_plugged:
            if battery.percent >= 99:
                self.state = "Full"
            else:
                self.state = "Charging"
        else:
            self.state = "Discharging"

        # Update icon
        metadata = self.get_metadata()
        if battery.power_plugged:
            metadata.icon = "mdi:battery-charging"
        else:
            metadata.icon = "mdi:battery"

        # Attributes
        self.attributes = {
            "power_plugged": battery.power_plugged,
            "percent": battery.percent,
        }

        # Add time info if available
        if battery.secsleft == psutil.POWER_TIME_UNLIMITED:
            self.attributes["time_info"] = "Unlimited (plugged in)"
        elif battery.secsleft == psutil.POWER_TIME_UNKNOWN or battery.secsleft < 0:
            self.attributes["time_info"] = "Unknown"
        else:
            self.attributes["time_info"] = format_seconds_to_time(battery.secsleft)
            self.attributes["seconds_left"] = battery.secsleft
"""Battery level sensor implementation."""

import logging

import psutil

from ..sensor_base import BaseSensor, SensorMetadata

logger = logging.getLogger(__name__)


def format_seconds_to_time(seconds: int) -> str:
    """Format seconds into HH:MM:SS format."""
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{int(hours)}:{int(minutes):02d}:{int(secs):02d}"


class BatteryLevelSensor(BaseSensor):
    """Battery level sensor."""

    config_name = "battery_level"

    def __init__(self):
        """Initialize battery sensor."""
        super().__init__()

    def get_metadata(self) -> SensorMetadata:
        """Get battery sensor metadata."""

        # Update icon based on battery level
        percent = self.state
        level = round(percent / 10) * 10
        icon = f"mdi:battery"
        if self.attributes["power_plugged"]:
            icon += "-charging"
        if level == 0:
            icon += "-outline"
        elif level < 100:
            icon += f"-{level}"

        return SensorMetadata(
            unique_id=f"battery_level_{self.instance_id}" if self.instance_id else "battery_level",
            name=f"Battery Level ({self.instance_id})" if self.instance_id else "Battery Level",
            config_name=self.config_name,
            device_class="battery",
            state_class="measurement",
            unit_of_measurement="%",
            icon=icon,
        )

    @classmethod
    async def discover_sensors(cls) -> list["BatteryLevelSensor"]:
        """Discover available batteries on the system."""
        # Check if the system has a battery
        if psutil.sensors_battery() is not None:
            # For now, create a single battery sensor
            # TODO: Check /sys/class/power_supply/ for multiple batteries,
            # create 1 sensor per battery
            return [cls()]
        return []

    async def update(self) -> None:
        """Update battery state and attributes."""
        battery = psutil.sensors_battery()

        if battery is None:
            self.state = "unavailable"
            self.attributes = {}
            return

        self.state = battery.percent

        self.attributes = {"power_plugged": battery.power_plugged}

        # Add time remaining if available
        # psutil.POWER_TIME_UNLIMITED is -2, psutil.POWER_TIME_UNKNOWN is -1
        if battery.secsleft == psutil.POWER_TIME_UNLIMITED:
            self.attributes["time_left"] = "Unlimited (plugged in)"
        elif battery.secsleft == psutil.POWER_TIME_UNKNOWN or battery.secsleft < 0:
            self.attributes["time_left"] = "Unknown"
        else:
            # Convert seconds to readable format
            self.attributes["time_left"] = format_seconds_to_time(battery.secsleft)
            self.attributes["seconds_left"] = battery.secsleft


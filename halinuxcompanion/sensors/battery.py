"""Battery sensor implementation using proper inheritance."""

import logging
from typing import List, Optional

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
    
    def __init__(self, battery_id: str = ""):
        """Initialize battery sensor.
        
        Args:
            battery_id: Battery identifier (e.g., "BAT0")
        """
        super().__init__(battery_id)
        
    def get_metadata(self) -> SensorMetadata:
        """Get battery sensor metadata."""
        return SensorMetadata(
            unique_id=f"battery_level_{self.instance_id}" if self.instance_id else "battery_level",
            name=f"Battery Level ({self.instance_id})" if self.instance_id else "Battery Level",
            config_name=self.config_name,
            device_class="battery",
            state_class="measurement",
            unit_of_measurement="%",
            icon="mdi:battery",
        )
    
    @classmethod
    async def discover_sensors(cls) -> List["BatteryLevelSensor"]:
        """Discover available batteries on the system."""
        sensors = []
        
        # Check if the system has a battery
        battery = psutil.sensors_battery()
        if battery is not None:
            # For now, create a single battery sensor
            # In the future, we could check /sys/class/power_supply/ for multiple batteries
            sensors.append(cls())
            
        return sensors
    
    async def update(self) -> None:
        """Update battery state and attributes."""
        battery = psutil.sensors_battery()
        
        if battery is None:
            self.state = "unavailable"
            self.attributes = {}
            return
            
        # Update state
        self.state = round(battery.percent)
        
        # Update icon based on battery level
        level = round(battery.percent / 10) * 10
        if level == 100:
            icon_suffix = ""
        elif level == 0:
            icon_suffix = "-outline"
        else:
            icon_suffix = f"-{level}"
        
        # Add charging status to icon
        if battery.power_plugged:
            icon_suffix = f"-charging{icon_suffix}"
            
        metadata = self.get_metadata()
        metadata.icon = f"mdi:battery{icon_suffix}"
        
        # Update attributes
        self.attributes = {
            "power_plugged": battery.power_plugged,
        }
        
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
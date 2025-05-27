"""Temperature sensors implementation."""

import logging
from typing import Any, Dict, Optional

import psutil

from ..sensor_base import BaseSensor, SensorMetadata

logger = logging.getLogger(__name__)


class TemperatureSensor(BaseSensor):
    """Temperature sensor for monitoring system temperatures."""

    config_name = "temperature"

    def __init__(self, sensor_name: str, sensor_label: str):
        """Initialize temperature sensor.

        Args:
            sensor_name: Unique name for the sensor (e.g., "coretemp_core0")
            sensor_label: Human-readable label (e.g., "CPU Core 0")
        """
        super().__init__(sensor_name)
        self.sensor_name = sensor_name
        self.sensor_label = sensor_label
        self._max_threshold: Optional[float] = None
        self._critical_threshold: Optional[float] = None

    def get_metadata(self) -> SensorMetadata:
        """Get temperature sensor metadata."""
        # Create a safe unique ID by replacing spaces and special chars
        safe_name = self.sensor_name.replace(" ", "_").replace("-", "_").lower()
        return SensorMetadata(
            unique_id=f"temperature_{safe_name}",
            name=f"Temperature {self.sensor_label}",
            config_name=self.config_name,
            device_class="temperature",
            state_class="measurement",
            unit_of_measurement="°C",
            icon="mdi:thermometer",
        )

    @classmethod
    async def discover_sensors(cls, config: Optional[Dict[str, Any]] = None) -> list["BaseSensor"]:
        """Discover available temperature sensors."""
        del config  # Unused parameter
        sensors = []
        discovered_names = set()

        # Use psutil only
        try:
            temps = psutil.sensors_temperatures()
            for chip_name, chip_temps in temps.items():
                for temp in chip_temps:
                    # Create unique sensor name
                    sensor_name = f"{chip_name}_{temp.label}" if temp.label else chip_name

                    # Avoid duplicates
                    if sensor_name in discovered_names:
                        continue
                    discovered_names.add(sensor_name)

                    # Create sensor instance
                    sensor = cls(
                        sensor_name=sensor_name,
                        sensor_label=temp.label or chip_name,
                    )

                    # Store threshold values if available
                    if temp.high is not None:
                        sensor._max_threshold = temp.high
                    if temp.critical is not None:
                        sensor._critical_threshold = temp.critical

                    sensors.append(sensor)
                    label_info = f" ({temp.label})" if temp.label else ""
                    logger.info(f"Discovered temperature sensor: {sensor_name}{label_info}")
        except Exception:
            logger.debug("Failed to discover temperature sensors via psutil", exc_info=True)

        if not sensors:
            logger.info("No temperature sensors found")

        return sensors

    async def update(self) -> None:
        """Update temperature sensor state."""
        try:
            temperature = None

            # Get temperature from psutil
            temps = psutil.sensors_temperatures()
            for chip_name, chip_temps in temps.items():
                for temp in chip_temps:
                    sensor_name = f"{chip_name}_{temp.label}" if temp.label else chip_name
                    if sensor_name == self.sensor_name:
                        temperature = temp.current
                        # Update thresholds if available
                        if temp.high is not None:
                            self._max_threshold = temp.high
                        if temp.critical is not None:
                            self._critical_threshold = temp.critical
                        break
                if temperature is not None:
                    break

            if temperature is None:
                self.state = "unavailable"
                self.attributes = {}
                return

            # Update state
            self.state = temperature

            # Update icon based on temperature
            metadata = self.get_metadata()
            if temperature >= 80:
                metadata.icon = "mdi:thermometer-high"
            elif temperature >= 60:
                metadata.icon = "mdi:thermometer-medium"
            elif temperature <= 20:
                metadata.icon = "mdi:thermometer-low"
            else:
                metadata.icon = "mdi:thermometer"

        except Exception:
            logger.error(f"Failed to update temperature sensor {self.sensor_name}", exc_info=True)
            self.state = "unavailable"
            self.attributes = {"error": "Failed to read temperature"}
            return

        # Build attributes
        self.attributes = {}

        # Only include sensor_label if it's different from the chip name part of sensor_name
        sensor_name_parts = self.sensor_name.split("_", 1)
        chip_name = sensor_name_parts[0] if sensor_name_parts else self.sensor_name

        if self.sensor_label and self.sensor_label != chip_name and self.sensor_label != self.sensor_name:
            self.attributes["sensor_label"] = self.sensor_label

        # Add thresholds if available
        if self._max_threshold is not None:
            self.attributes["max_threshold"] = self._max_threshold
            self.attributes["max_threshold_reached"] = temperature >= self._max_threshold

        if self._critical_threshold is not None:
            self.attributes["critical_threshold"] = self._critical_threshold
            self.attributes["critical_threshold_reached"] = temperature >= self._critical_threshold

        # Add temperature status
        if self._critical_threshold and temperature >= self._critical_threshold:
            self.attributes["status"] = "critical"
        elif self._max_threshold and temperature >= self._max_threshold:
            self.attributes["status"] = "high"
        elif temperature <= 20:
            self.attributes["status"] = "low"
        else:
            self.attributes["status"] = "normal"



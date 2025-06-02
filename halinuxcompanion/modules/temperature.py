"""Temperature module implementation."""

from __future__ import annotations

import logging

import psutil

from ...module_base import DeviceClass, Module, Sensor, StateClass
from ...module_config import TemperatureConfig

logger = logging.getLogger(__name__)


class TemperatureModule(Module):
    """Temperature module with bulk update support."""

    def __init__(self, config: TemperatureConfig):
        super().__init__(config)
        self.config: TemperatureConfig = config
        # hw id => sensor label => sensor
        self._sensors: dict[str, dict[str, Sensor]] = {}

    async def discover_sensors(self) -> list[Sensor]:
        """Discover available temperature chips."""
        try:
            temps = psutil.sensors_temperatures()
        except (OSError, RuntimeError):
            logger.exception("Failed to retrieve temperature sensors")
            return []

        if not temps:
            logger.debug("No temperature sensors found")
            return []

        sensors: dict[str, dict[str, Sensor]] = {}
        for chip_name, chip_temps in temps.items():
            sensors[chip_name] = {}

            # Create a sensor for each temperature reading on this chip
            for temp in chip_temps:
                # Store sensor by label for easy lookup during updates
                name = f"Temperature - {chip_name}"
                unique_id = f"temperature:{chip_name}"
                if temp.label:
                    name += f" - {temp.label}"
                    unique_id += f":{temp.label}"
                sensors[chip_name][temp.label] = Sensor(
                    unique_id=unique_id,
                    name=name,
                    unit_of_measurement="°C",
                    device_class=DeviceClass.TEMPERATURE,
                    state_class=StateClass.MEASUREMENT,
                    icon="mdi:thermometer",
                )

        self._sensors = sensors
        logger.debug(f"Discovered {len(self._sensors)} temperature chips: {' '.join(sorted(self._sensors.keys()))}")

        # Construct all_sensors at the end
        return [sensor for sensors_by_label in self._sensors.values() for sensor in sensors_by_label.values()]

    async def update_all_sensors(self) -> None:
        """Bulk update all temperature sensors in one read."""
        try:
            temps = psutil.sensors_temperatures()
        except (OSError, RuntimeError) as e:
            # Set all sensors to error state
            for chip_sensors in self._sensors.values():
                for sensor in chip_sensors.values():
                    sensor.set_error(e, "Failed to read temperature sensors")
            return

        # Update data for each temperature reading
        for chip_name, chip_temps in temps.items():
            if chip_name not in self._sensors:
                # This chip wasn't discovered during initialization
                # TODO: ... rediscovery ...
                logger.info(f"Skipping unknown temperature chip: {chip_name}")
                continue

            chip_sensors = self._sensors[chip_name]
            for temp in chip_temps:
                sensor_label = temp.label or "default"
                if sensor_label not in chip_sensors:
                    continue
                sensor = chip_sensors[sensor_label]
                sensor.set_ok(temp.current)
                sensor.attributes.update({"chip": chip_name, "label": sensor_label})
                if temp.high is not None:
                    sensor.attributes["high"] = temp.high
                if temp.critical is not None:
                    sensor.attributes["critical"] = temp.critical

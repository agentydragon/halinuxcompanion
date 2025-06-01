"""Temperature hardware class implementation."""

from __future__ import annotations

import logging
from typing import List

import psutil

from ..hardware_base import DeviceClass, HardwareClass, HardwareSensor, StateClass
from ..hardware_config import TemperatureConfig

logger = logging.getLogger(__name__)


class TemperatureHardwareClass(HardwareClass):
    """Temperature hardware class with bulk update support."""

    config_field = "temperature"

    def __init__(self, config: TemperatureConfig):
        super().__init__(config)
        self.config: TemperatureConfig = config
        # hw id => sensor label => sensor
        self._sensors: dict[str, dict[str, HardwareSensor]] = {}

    async def discover_sensors(self) -> List[HardwareSensor]:
        """Discover available temperature chips."""
        if not (temps := psutil.sensors_temperatures()):
            logger.debug("No temperature sensors found")
            return []

        sensors: dict[str, dict[str, HardwareSensor]] = {}
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
                sensors[chip_name][temp.label] = HardwareSensor(
                    unique_id=unique_id,
                    name=name,
                    unit_of_measurement="°C",
                    device_class=DeviceClass.TEMPERATURE,
                    state_class=StateClass.MEASUREMENT,
                    icon="mdi:thermometer",
                )

        self._sensors = sensors
        logger.debug(
            f"Discovered {len(self._sensors)} temperature chips: {' '.join(sorted(self._sensors.keys()))}"
        )

        # Construct all_sensors at the end
        return [
            sensor
            for sensors_by_label in self._sensors.values()
            for sensor in sensors_by_label.values()
        ]

    async def update_all_sensors(self) -> None:
        """Bulk update all temperature sensors in one read."""
        # Update data for each temperature reading
        for chip_name, chip_temps in psutil.sensors_temperatures().items():
            if not (chip_sensors := self._sensors.get(chip_name)):
                # This chip wasn't discovered during initialization
                # TODO: ... rediscovery ...
                logger.info(f"Skipping unknown temperature chip: {chip_name}")
                continue

            for temp in chip_temps:
                sensor_label = temp.label or "default"
                if not (sensor := chip_sensors.get(sensor_label)):
                    continue
                sensor.state = temp.current
                sensor.attributes = {"chip": chip_name, "label": sensor_label}
                if temp.high is not None:
                    sensor.attributes["high"] = temp.high
                if temp.critical is not None:
                    sensor.attributes["critical"] = temp.critical

"""Temperature hardware class implementation."""

from __future__ import annotations

import logging
from typing import Dict, List

import psutil

from ..hardware_base import HardwareClass, HardwarePiece, HardwareSensor
from ..hardware_config import SensorInfo, TemperatureConfig

logger = logging.getLogger(__name__)


class TemperaturePiece(HardwarePiece):
    """Represents a temperature chip with multiple sensors."""

    def __init__(self, hardware_id: str, chip_name: str):
        super().__init__(hardware_id)
        self.chip_name = chip_name
        # Dictionary to store sensors by label
        self.sensors_by_label: Dict[str, HardwareSensor] = {}

    def get_sensors(self) -> List[HardwareSensor]:
        """Get all sensors for this chip."""
        return list(self.sensors_by_label.values())


class TemperatureHardwareClass(HardwareClass):
    """Temperature hardware class with bulk update support."""

    hardware_class = "temperature"
    config_field = "temperature"

    def __init__(self, config: TemperatureConfig):
        super().__init__(config)
        self.config: TemperatureConfig = config
        # Index pieces by chip_name for efficient lookup
        self._piece_index: Dict[str, TemperaturePiece] = {}

    async def discover_sensors(self) -> List[HardwareSensor]:
        """Discover available temperature chips."""
        if not (temps := psutil.sensors_temperatures()):
            logger.debug("No temperature sensors found")
            return []

        for chip_name, chip_temps in temps.items():
            piece = TemperaturePiece(chip_name, chip_name)

            # Create a sensor for each temperature reading on this chip
            for temp in chip_temps:
                # Create unique sensor ID
                sensor_label = temp.label or "default"

                # Store sensor by label for easy lookup during updates
                piece.sensors_by_label[sensor_label] = HardwareSensor(
                    hardware_class=self.hardware_class,
                    hardware_id=f"{piece.chip_name}_{sensor_label}",
                    sensor_type_name="temperature",
                    sensor_info=SensorInfo(
                        name="Temperature",
                        unit="°C",
                        device_class="temperature",
                        state_class="measurement",
                        icon="mdi:thermometer",
                    ),
                    hardware_piece=piece,
                )

            # Add piece to index for efficient lookup
            self._piece_index[piece.chip_name] = piece

        logger.debug(
            f"Discovered {len(self._piece_index)} temperature chips: {' '.join(p.hardware_id for p in self._piece_index.values())}"
        )

        # Construct all_sensors at the end
        all_sensors = []
        for piece in self._piece_index.values():
            all_sensors.extend(piece.get_sensors())
        return all_sensors

    async def update_all_sensors(self) -> None:
        """Bulk update all temperature sensors in one read."""
        # Update data for each temperature reading
        for chip_name, chip_temps in psutil.sensors_temperatures().items():
            if not (piece := self._piece_index.get(chip_name)):
                # This chip wasn't discovered during initialization
                continue

            for temp in chip_temps:
                sensor_label = temp.label or "default"
                if not (sensor := piece.sensors_by_label.get(sensor_label)):
                    continue
                # Update sensor state directly
                sensor.state = temp.current
                sensor.attributes = {"chip": chip_name, "label": sensor_label}
                if temp.high is not None:
                    sensor.attributes["high"] = temp.high
                if temp.critical is not None:
                    sensor.attributes["critical"] = temp.critical

"""Temperature hardware class implementation."""

from __future__ import annotations

import logging
from typing import Dict, List

import psutil

from ..hardware_base import (
    HardwareClass,
    HardwarePiece,
    HardwareProvider,
    HardwareSensor,
)
from ..hardware_config import TemperatureConfig, SensorInfo

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


class TemperatureProvider(HardwareProvider):
    """Temperature hardware provider."""

    async def discover_hardware(self) -> List[HardwarePiece]:
        """Discover available temperature chips."""
        temps = psutil.sensors_temperatures()
        if not temps:
            logger.debug("No temperature sensors found")
            return []

        pieces: List[HardwarePiece] = []
        for chip_name in temps.keys():
            piece = TemperaturePiece(chip_name, chip_name)
            pieces.append(piece)

        logger.debug(
            f"Discovered {len(pieces)} temperature chips: {', '.join([p.hardware_id for p in pieces])}"
        )
        return pieces


class TemperatureHardwareClass(HardwareClass):
    """Temperature hardware class with bulk update support."""

    hardware_class = "temperature"
    config_field = "temperature"

    def __init__(self, config: TemperatureConfig):
        super().__init__(config)
        self.config: TemperatureConfig = config
        # Index pieces by chip_name for efficient lookup
        self._piece_index: Dict[str, TemperaturePiece] = {}

    async def get_provider(self) -> HardwareProvider:
        """Get the hardware provider."""
        if not self._provider:
            self._provider = TemperatureProvider()
        return self._provider

    async def discover_sensors(self) -> List[HardwareSensor]:
        """Discover all sensors and build piece index."""
        provider = await self.get_provider()
        pieces = await provider.discover_hardware()

        # Get current temperature data to know what sensors exist on each chip
        temps = psutil.sensors_temperatures()

        for piece in pieces:
            chip_temps = temps.get(piece.chip_name, [])

            # Create a sensor for each temperature reading on this chip
            for temp in chip_temps:
                # Create unique sensor ID
                sensor_label = temp.label or "default"
                sensor_id = f"{piece.chip_name}_{sensor_label}"

                sensor = HardwareSensor(
                    hardware_class=self.hardware_class,
                    hardware_id=sensor_id,
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

                # Store sensor by label for easy lookup during updates
                piece.sensors_by_label[sensor_label] = sensor

            # Add piece to index for efficient lookup
            self._piece_index[piece.chip_name] = piece

        # Construct all_sensors at the end
        all_sensors = []
        for piece in pieces:
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
                if sensor := piece.sensors_by_label.get(sensor_label):
                    # Update sensor state directly
                    sensor.state = temp.current
                    sensor.attributes = {
                        "chip": chip_name,
                        "label": sensor_label,
                        "high": temp.high,
                        "critical": temp.critical,
                    }

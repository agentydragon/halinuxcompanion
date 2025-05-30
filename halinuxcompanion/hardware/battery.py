"""Battery hardware class implementation."""

from __future__ import annotations

import logging
from functools import partial
from typing import List, Optional

from ..hardware_base import (
    HardwareClass,
    HardwarePiece,
    HardwareSensor,
    PerPieceUpdateMixin,
)
from ..hardware_config import BatteryConfig, SensorInfo
from .battery.provider import BatteryData, BatteryDataProvider
from .battery.psutil_provider import PsutilBatteryProvider
from .battery.upower_provider import UPowerBatteryProvider

logger = logging.getLogger(__name__)


class BatteryPiece(HardwarePiece):
    """Represents a single battery."""

    def __init__(self, hardware_id: str, provider: BatteryDataProvider):
        super().__init__(hardware_id)
        self._provider = provider
        self._battery_data: Optional[BatteryData] = None

        # Sensor attributes
        self.charge_level_sensor: Optional[HardwareSensor] = None
        self.charging_state_sensor: Optional[HardwareSensor] = None
        self.time_to_empty_sensor: Optional[HardwareSensor] = None
        self.time_to_full_sensor: Optional[HardwareSensor] = None
        self.temperature_sensor: Optional[HardwareSensor] = None
        self.voltage_sensor: Optional[HardwareSensor] = None
        self.charge_rate_sensor: Optional[HardwareSensor] = None
        self.discharge_rate_sensor: Optional[HardwareSensor] = None
        self.health_sensor: Optional[HardwareSensor] = None
        self.charge_cycles_sensor: Optional[HardwareSensor] = None
        self.energy_sensor: Optional[HardwareSensor] = None
        self.energy_full_sensor: Optional[HardwareSensor] = None

    async def update(self) -> None:
        """Update battery data and push to sensors."""
        data = await self._provider.get_battery_data(self.hardware_id)
        if not data:
            return

        # Push data to other sensors
        for sensor, value in [
            (self.charge_level_sensor, data.percent),
            (self.charging_state_sensor, data.state),
            (self.time_to_empty_sensor, data.time_to_empty),
            (self.time_to_full_sensor, data.time_to_full),
            (self.temperature_sensor, data.temperature),
            (self.voltage_sensor, data.voltage),
            (self.charge_rate_sensor, data.charge_rate),
            (self.discharge_rate_sensor, data.discharge_rate),
            (self.health_sensor, data.capacity),
            (self.charge_cycles_sensor, data.charge_cycles),
            (self.energy_sensor, data.energy),
            (self.energy_full_sensor, data.energy_full),
        ]:
            if sensor and value is not None:
                sensor.state = value
                sensor.attributes = {
                    "battery_id": self.hardware_id,
                    "battery_name": data.name,
                }

        # Update battery level sensor with dynamic icon
        if self.charge_level_sensor and data.percent is not None:
            self.charge_level_sensor.sensor_info.icon = data.get_icon()

    def get_sensors(self) -> List[HardwareSensor]:
        """Get all sensors for this battery."""
        return list(
            filter(
                None,
                [
                    self.charge_level_sensor,
                    self.charging_state_sensor,
                    self.time_to_empty_sensor,
                    self.time_to_full_sensor,
                    self.temperature_sensor,
                    self.voltage_sensor,
                    self.charge_rate_sensor,
                    self.discharge_rate_sensor,
                    self.health_sensor,
                    self.charge_cycles_sensor,
                    self.energy_sensor,
                    self.energy_full_sensor,
                ],
            )
        )


class BatteryHardwareClass(PerPieceUpdateMixin, HardwareClass):
    """Battery hardware class."""

    hardware_class = "battery"
    config_field = "battery"

    def __init__(self, config: BatteryConfig):
        super().__init__(config)
        self.config: BatteryConfig = config
        self._hardware_pieces: list[BatteryPiece] = []  # type: ignore[assignment]

        self.provider: BatteryDataProvider
        if self.config.implementation == "upower":
            self.provider = UPowerBatteryProvider()
        else:
            self.provider = PsutilBatteryProvider()

    async def discover_sensors(self) -> List[HardwareSensor]:
        """Discover and create sensors for batteries."""
        battery_ids = await self.provider.discover_batteries()
        pieces = [BatteryPiece(battery_id, self.provider) for battery_id in battery_ids]
        self._hardware_pieces = pieces
        # Determine which sensors to enable based on provider type

        for piece in pieces:
            _sensor = partial(
                HardwareSensor,
                hardware_class=self.hardware_class,
                hardware_id=piece.hardware_id,
                hardware_piece=piece,
            )
            piece.charge_level_sensor = _sensor(
                sensor_type_name="charge_level",
                sensor_info=SensorInfo(
                    name="Battery Level",
                    unit="%",
                    device_class="battery",
                    state_class="measurement",
                ),
            )
            piece.charging_state_sensor = _sensor(
                sensor_type_name="charging_state",
                sensor_info=SensorInfo(name="Battery State", icon="mdi:battery"),
            )
            piece.time_to_empty_sensor = _sensor(
                sensor_type_name="time_to_empty",
                sensor_info=SensorInfo(
                    name="Time to Empty",
                    unit="s",
                    device_class="duration",
                    state_class="measurement",
                ),
            )

            # For upower, all sensors are potentially available
            if isinstance(self.provider, UPowerBatteryProvider):
                piece.time_to_full_sensor = _sensor(
                    sensor_type_name="time_to_full",
                    sensor_info=SensorInfo(
                        name="Time to Full",
                        unit="s",
                        device_class="duration",
                        state_class="measurement",
                    ),
                )
                piece.temperature_sensor = _sensor(
                    sensor_type_name="temperature",
                    sensor_info=SensorInfo(
                        name="Battery Temperature",
                        unit="°C",
                        device_class="temperature",
                        state_class="measurement",
                    ),
                )
                piece.voltage_sensor = _sensor(
                    sensor_type_name="voltage",
                    sensor_info=SensorInfo(
                        name="Battery Voltage",
                        unit="V",
                        device_class="voltage",
                        state_class="measurement",
                    ),
                )
                piece.charge_rate_sensor = _sensor(
                    sensor_type_name="charge_rate",
                    sensor_info=SensorInfo(
                        name="Charge Rate",
                        unit="W",
                        device_class="power",
                        state_class="measurement",
                    ),
                )
                piece.discharge_rate_sensor = _sensor(
                    sensor_type_name="discharge_rate",
                    sensor_info=SensorInfo(
                        name="Discharge Rate",
                        unit="W",
                        device_class="power",
                        state_class="measurement",
                    ),
                )
                piece.health_sensor = _sensor(
                    sensor_type_name="health",
                    sensor_info=SensorInfo(
                        name="Battery Health", unit="%", state_class="measurement"
                    ),
                )
                piece.charge_cycles_sensor = _sensor(
                    sensor_type_name="charge_cycles",
                    sensor_info=SensorInfo(
                        name="Charge Cycles", state_class="total_increasing"
                    ),
                )
                piece.energy_sensor = _sensor(
                    sensor_type_name="energy",
                    sensor_info=SensorInfo(
                        name="Battery Energy",
                        unit="Wh",
                        device_class="energy_storage",
                        state_class="measurement",
                    ),
                )
                piece.energy_full_sensor = _sensor(
                    sensor_type_name="energy_full",
                    sensor_info=SensorInfo(
                        name="Battery Energy Full",
                        unit="Wh",
                        device_class="energy_storage",
                        state_class="measurement",
                    ),
                )

        # Construct all_sensors at the end
        all_sensors = []
        for piece in self._hardware_pieces:
            all_sensors.extend(piece.get_sensors())
        return all_sensors

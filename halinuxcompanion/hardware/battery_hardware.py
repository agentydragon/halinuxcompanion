"""Battery hardware class implementation."""

from __future__ import annotations

import logging
from typing import List

from ..hardware_base import (
    DeviceClass,
    HardwareClass,
    HardwarePiece,
    HardwareSensor,
    PerPieceUpdateMixin,
    StateClass,
)
from ..hardware_config import BatteryConfig
from .battery.provider import BatteryDataProvider
from .battery.psutil import PsutilBatteryProvider
from .battery.upower import UPowerBatteryProvider

logger = logging.getLogger(__name__)


class BatteryPiece(HardwarePiece):
    """Represents a single battery."""

    def __init__(
        self,
        hardware_id: str,
        provider: BatteryDataProvider,
        charge_level_sensor: HardwareSensor,
        charging_state_sensor: HardwareSensor,
        time_to_empty_sensor: HardwareSensor,
        time_to_full_sensor: HardwareSensor,
        temperature_sensor: HardwareSensor,
        voltage_sensor: HardwareSensor,
        charge_rate_sensor: HardwareSensor,
        discharge_rate_sensor: HardwareSensor,
        health_sensor: HardwareSensor,
        charge_cycles_sensor: HardwareSensor,
        energy_sensor: HardwareSensor,
        energy_full_sensor: HardwareSensor,
    ):
        super().__init__(hardware_id)
        self._provider = provider

        self.charge_level_sensor = charge_level_sensor
        self.charging_state_sensor = charging_state_sensor
        self.time_to_empty_sensor = time_to_empty_sensor
        self.time_to_full_sensor = time_to_full_sensor
        self.temperature_sensor = temperature_sensor
        self.voltage_sensor = voltage_sensor
        self.charge_rate_sensor = charge_rate_sensor
        self.discharge_rate_sensor = discharge_rate_sensor
        self.health_sensor = health_sensor
        self.charge_cycles_sensor = charge_cycles_sensor
        self.energy_sensor = energy_sensor
        self.energy_full_sensor = energy_full_sensor

    async def update(self) -> None:
        """Update battery data and push to sensors."""
        if not (data := await self._provider.get_battery_data(self.hardware_id)):
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
            sensor.state = value
            sensor.attributes = {"id": self.hardware_id}

        # Update battery level sensor with dynamic icon
        if data.percent is not None:
            # TODO: i hear HA does this maybe automatically?
            self.charge_level_sensor.icon = data.get_icon()

    def get_sensors(self) -> List[HardwareSensor]:
        """Get all sensors for this battery."""
        if isinstance(self._provider, UPowerBatteryProvider):
            return [
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
            ]
        elif isinstance(self._provider, PsutilBatteryProvider):
            return [
                self.charge_level_sensor,
                self.charging_state_sensor,
                self.time_to_empty_sensor,
                self.temperature_sensor,
                self.voltage_sensor,
            ]
        else:
            raise Exception("Unknown battery provider")


class BatteryHardwareClass(PerPieceUpdateMixin, HardwareClass):
    """Battery hardware class."""

    config_field = "battery"

    def __init__(self, config: BatteryConfig):
        super().__init__(config)
        self.config: BatteryConfig = config
        self._hardware_pieces: list[BatteryPiece] = []  # type: ignore[assignment]

        self.provider: BatteryDataProvider
        if self.config.implementation == "upower":
            self.provider = UPowerBatteryProvider()
        elif self.config.implementation == "psutil":
            self.provider = PsutilBatteryProvider()
        else:
            raise ValueError(
                f"Unknown battery implementation: {self.config.implementation}"
            )

    async def discover_sensors(self) -> List[HardwareSensor]:
        """Discover and create sensors for batteries."""
        self._hardware_pieces.clear()
        battery_ids: List[str] = await self.provider.discover_batteries()
        for battery_id in battery_ids:

            def _sensor(id, name, **kwargs):
                if len(battery_ids) > 1:
                    # Scope if multiple batteries
                    name = f"{battery_id} - {name}"
                return HardwareSensor(
                    unique_id=f"battery:{battery_id}:{id}",
                    name=name,
                    **kwargs,
                )

            self._hardware_pieces.append(
                BatteryPiece(
                    battery_id,
                    self.provider,
                    charge_level_sensor=_sensor(
                        id="charge_level",
                        name="Battery Level",
                        unit_of_measurement="%",
                        device_class=DeviceClass.BATTERY,
                        state_class=StateClass.MEASUREMENT,
                    ),
                    charging_state_sensor=_sensor(
                        id="charging_state",
                        name="Battery State",
                        unit_of_measurement=None,  # enum?
                        icon="mdi:battery",
                    ),
                    time_to_empty_sensor=_sensor(
                        id="time_to_empty",
                        name="Time to Empty",
                        unit_of_measurement="s",
                        device_class=DeviceClass.DURATION,
                        state_class=StateClass.MEASUREMENT,
                    ),
                    time_to_full_sensor=_sensor(
                        id="time_to_full",
                        name="Time to Full",
                        unit_of_measurement="s",
                        device_class=DeviceClass.DURATION,
                        state_class=StateClass.MEASUREMENT,
                    ),
                    temperature_sensor=_sensor(
                        id="temperature",
                        name="Battery Temperature",
                        unit_of_measurement="°C",
                        device_class=DeviceClass.TEMPERATURE,
                        state_class=StateClass.MEASUREMENT,
                    ),
                    voltage_sensor=_sensor(
                        id="voltage",
                        name="Battery Voltage",
                        unit_of_measurement="V",
                        device_class=DeviceClass.VOLTAGE,
                        state_class=StateClass.MEASUREMENT,
                    ),
                    charge_rate_sensor=_sensor(
                        id="charge_rate",
                        name="Charge Rate",
                        unit_of_measurement="W",
                        device_class=DeviceClass.POWER,
                        state_class=StateClass.MEASUREMENT,
                    ),
                    discharge_rate_sensor=_sensor(
                        id="discharge_rate",
                        name="Discharge Rate",
                        unit_of_measurement="W",
                        device_class=DeviceClass.POWER,
                        state_class=StateClass.MEASUREMENT,
                    ),
                    health_sensor=_sensor(
                        id="health",
                        name="Battery Health",
                        unit_of_measurement="%",
                        state_class=StateClass.MEASUREMENT,
                    ),
                    charge_cycles_sensor=_sensor(
                        id="charge_cycles",
                        name="Charge Cycles",
                        unit_of_measurement=None,
                        state_class=StateClass.MEASUREMENT,
                    ),
                    energy_sensor=_sensor(
                        id="energy",
                        name="Battery Energy",
                        unit_of_measurement="Wh",
                        device_class=DeviceClass.ENERGY_STORAGE,
                        state_class=StateClass.MEASUREMENT,
                    ),
                    energy_full_sensor=_sensor(
                        id="energy_full",
                        name="Battery Energy Full",
                        unit_of_measurement="Wh",
                        device_class=DeviceClass.ENERGY_STORAGE,
                        state_class=StateClass.MEASUREMENT,
                    ),
                )
            )

        # Construct all_sensors at the end
        all_sensors = []
        for piece in self._hardware_pieces:
            all_sensors.extend(piece.get_sensors())
        return all_sensors

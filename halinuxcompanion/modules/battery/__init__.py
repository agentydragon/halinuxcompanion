"""Battery module implementation."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from halinuxcompanion.module_base import DeviceClass, Module, Sensor, StateClass
from halinuxcompanion.module_config import BatteryConfig

from .provider import BatteryData
from .psutil import PsutilBatteryProvider
from .upower import UPowerBatteryProvider

logger = logging.getLogger(__name__)


@dataclass
class BatterySensors:
    """Container for battery sensors."""

    charge_level: Sensor
    charging_state: Sensor
    time_to_empty: Sensor
    temperature: Sensor
    voltage: Sensor
    # UPower-only sensors
    time_to_full: Sensor | None = None
    charge_rate: Sensor | None = None
    discharge_rate: Sensor | None = None
    health: Sensor | None = None
    charge_cycles: Sensor | None = None
    energy: Sensor | None = None
    energy_full: Sensor | None = None

    def update_from_data(self, data: BatteryData, battery_id: str) -> None:
        """Update all sensors from battery data."""
        # Common sensors
        self.charge_level.set_ok(data.percent)
        if data.percent is not None:
            self.charge_level.icon = data.get_icon()
        self.charging_state.set_ok(data.state)
        self.time_to_empty.set_ok(data.time_to_empty)
        self.temperature.set_ok(data.temperature)
        self.voltage.set_ok(data.voltage)

        # UPower-specific sensors
        if self.time_to_full:
            self.time_to_full.set_ok(data.time_to_full)
        if self.charge_rate:
            self.charge_rate.set_ok(data.charge_rate)
        if self.discharge_rate:
            self.discharge_rate.set_ok(data.discharge_rate)
        if self.health:
            self.health.set_ok(data.capacity)
        if self.charge_cycles:
            self.charge_cycles.set_ok(data.charge_cycles)
        if self.energy:
            self.energy.set_ok(data.energy)
        if self.energy_full:
            self.energy_full.set_ok(data.energy_full)

        # Set battery ID on all sensors
        for sensor in self.all_sensors():
            sensor.attributes = {"id": battery_id}

    def all_sensors(self) -> list[Sensor]:
        """Get all sensors that exist."""
        return [
            self.charge_level,
            self.charging_state,
            self.time_to_empty,
            self.temperature,
            self.voltage,
            *filter(
                None,
                [
                    self.time_to_full,
                    self.charge_rate,
                    self.discharge_rate,
                    self.health,
                    self.charge_cycles,
                    self.energy,
                    self.energy_full,
                ],
            ),
        ]


class BatteryModule(Module):
    """Battery module with support for multiple batteries."""

    PROVIDERS = {
        "upower": UPowerBatteryProvider,
        "psutil": PsutilBatteryProvider,
    }

    def __init__(self, config: BatteryConfig):
        super().__init__(config)
        self.config: BatteryConfig = config
        self._batteries: dict[str, BatterySensors] = {}

        if config.implementation not in self.PROVIDERS:
            raise ValueError(f"Unknown battery implementation: {config.implementation}")
        self.provider = self.PROVIDERS[config.implementation]()

    async def discover_sensors(self) -> list[Sensor]:
        """Discover and create sensors for batteries."""
        battery_ids = await self.provider.discover_batteries()

        if not battery_ids:
            logger.debug("No batteries found")
            return []

        self._batteries = {}
        all_sensors = []

        for battery_id in battery_ids:
            # Helper to create sensor with proper naming
            def _sensor(sensor_id: str, name: str, **kwargs) -> Sensor:
                # Add battery ID to name if multiple batteries
                if len(battery_ids) > 1:
                    name = f"{battery_id} - {name}"
                return Sensor(
                    unique_id=f"battery:{battery_id}:{sensor_id}",
                    name=name,
                    **kwargs,
                )

            # Create common sensors
            battery_sensors = BatterySensors(
                charge_level=_sensor(
                    "charge_level",
                    "Battery Level",
                    unit_of_measurement="%",
                    device_class=DeviceClass.BATTERY,
                    state_class=StateClass.MEASUREMENT,
                ),
                charging_state=_sensor(
                    "charging_state",
                    "Battery State",
                    icon="mdi:battery",
                    state_class=None,
                    options=["Charging", "Discharging", "Full", "Unknown"],
                ),
                time_to_empty=_sensor(
                    "time_to_empty",
                    "Time to Empty",
                    unit_of_measurement="s",
                    device_class=DeviceClass.DURATION,
                    state_class=StateClass.MEASUREMENT,
                ),
                temperature=_sensor(
                    "temperature",
                    "Battery Temperature",
                    unit_of_measurement="°C",
                    device_class=DeviceClass.TEMPERATURE,
                    state_class=StateClass.MEASUREMENT,
                ),
                voltage=_sensor(
                    "voltage",
                    "Battery Voltage",
                    unit_of_measurement="V",
                    device_class=DeviceClass.VOLTAGE,
                    state_class=StateClass.MEASUREMENT,
                ),
            )

            # Add UPower-specific sensors
            if isinstance(self.provider, UPowerBatteryProvider):
                battery_sensors.time_to_full = _sensor(
                    "time_to_full",
                    "Time to Full",
                    unit_of_measurement="s",
                    device_class=DeviceClass.DURATION,
                    state_class=StateClass.MEASUREMENT,
                )

                battery_sensors.charge_rate = _sensor(
                    "charge_rate",
                    "Charge Rate",
                    unit_of_measurement="W",
                    device_class=DeviceClass.POWER,
                    state_class=StateClass.MEASUREMENT,
                )

                battery_sensors.discharge_rate = _sensor(
                    "discharge_rate",
                    "Discharge Rate",
                    unit_of_measurement="W",
                    device_class=DeviceClass.POWER,
                    state_class=StateClass.MEASUREMENT,
                )

                battery_sensors.health = _sensor(
                    "health", "Battery Health", unit_of_measurement="%", state_class=StateClass.MEASUREMENT
                )

                battery_sensors.charge_cycles = _sensor(
                    "charge_cycles", "Charge Cycles", state_class=StateClass.MEASUREMENT
                )

                battery_sensors.energy = _sensor(
                    "energy",
                    "Battery Energy",
                    unit_of_measurement="Wh",
                    device_class=DeviceClass.ENERGY_STORAGE,
                    state_class=StateClass.MEASUREMENT,
                )

                battery_sensors.energy_full = _sensor(
                    "energy_full",
                    "Battery Energy Full",
                    unit_of_measurement="Wh",
                    device_class=DeviceClass.ENERGY_STORAGE,
                    state_class=StateClass.MEASUREMENT,
                )

            self._batteries[battery_id] = battery_sensors
            all_sensors.extend(battery_sensors.all_sensors())

        logger.debug(f"Discovered {len(battery_ids)} batteries with {len(all_sensors)} sensors total")
        return all_sensors

    async def update_all_sensors(self) -> None:
        """Update all battery sensors."""
        for battery_id, battery_sensors in self._batteries.items():
            try:
                data = await self.provider.get_battery_data(battery_id)
                if data:
                    battery_sensors.update_from_data(data, battery_id)
                else:
                    # No data - set all sensors to None
                    for sensor in battery_sensors.all_sensors():
                        sensor.state = None
                        sensor.attributes = {"id": battery_id}
            except Exception:
                # Set all sensors for this battery to error state
                logger.exception(f"Failed to get battery data for {battery_id}")
                for sensor in battery_sensors.all_sensors():
                    sensor.set_error(Exception("Failed to get battery data"), None)

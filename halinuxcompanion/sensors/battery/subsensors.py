"""Battery subsensors that work with any battery data provider."""

import logging
from typing import Any, Dict, List, Optional

from halinuxcompanion.sensor_base import BaseSensor
from .battery_provider import BatteryData, BatteryDataProvider

logger = logging.getLogger(__name__)


class BatterySubSensor(BaseSensor):
    """Base class for battery sub-sensors."""

    # To be set by subclasses
    sensor_field: str
    name_suffix: str

    def __init__(self, provider: BatteryDataProvider, battery_data: BatteryData, **sensor_kwargs):
        battery_id = battery_data.battery_id

        super().__init__(
            instance_id=battery_id,
            name=f"{battery_data.name} {self.name_suffix}",
            **sensor_kwargs
        )
        self._provider = provider
        self._battery_id = battery_id

    async def update(self) -> None:
        """Update sensor state from battery data."""
        battery_data = await self._provider.get_battery_data(self._battery_id)
        if not battery_data:
            self.state = "unavailable"
            return

        value = getattr(battery_data, self.sensor_field, None)
        self.state = value if value is not None else "unavailable"


# Generic subsensor classes that can be used by any provider

class TimeToEmptySensor(BatterySubSensor):
    """Battery time to empty sensor."""

    sensor_field = "time_to_empty"
    name_suffix = "Time to Empty"

    def __init__(self, provider: BatteryDataProvider, battery_data: BatteryData):
        super().__init__(
            provider, battery_data,
            device_class="duration",
            native_unit_of_measurement="s",
            state_class="measurement",
            entity_category="diagnostic",
        )


class TimeToFullSensor(BatterySubSensor):
    """Battery time to full sensor."""

    sensor_field = "time_to_full"
    name_suffix = "Time to Full"

    def __init__(self, provider: BatteryDataProvider, battery_data: BatteryData):
        super().__init__(
            provider, battery_data,
            device_class="duration",
            native_unit_of_measurement="s",
            state_class="measurement",
            entity_category="diagnostic",
        )


class TemperatureSensor(BatterySubSensor):
    """Battery temperature sensor."""

    sensor_field = "temperature"
    name_suffix = "Temperature"

    def __init__(self, provider: BatteryDataProvider, battery_data: BatteryData):
        super().__init__(
            provider, battery_data,
            device_class="temperature",
            native_unit_of_measurement="°C",
            state_class="measurement",
            entity_category="diagnostic",
        )


class VoltageSensor(BatterySubSensor):
    """Battery voltage sensor."""

    sensor_field = "voltage"
    name_suffix = "Voltage"

    def __init__(self, provider: BatteryDataProvider, battery_data: BatteryData):
        super().__init__(
            provider, battery_data,
            device_class="voltage",
            native_unit_of_measurement="V",
            state_class="measurement",
            entity_category="diagnostic",
        )


class PowerSensor(BatterySubSensor):
    """Battery charge/discharge rate sensor."""

    sensor_field = "energy_rate"
    name_suffix = "Power"

    def __init__(self, provider: BatteryDataProvider, battery_data: BatteryData):
        super().__init__(
            provider, battery_data,
            device_class="power",
            native_unit_of_measurement="W",
            state_class="measurement",
        )

    async def update(self) -> None:
        """Update sensor with charge or discharge rate."""
        battery_data = await self._provider.get_battery_data(self._battery_id)
        if not battery_data:
            self.state = "unavailable"
            return

        # Use charge_rate when charging, discharge_rate when discharging
        if battery_data.state == "Charging" and battery_data.charge_rate:
            self.state = battery_data.charge_rate
        elif battery_data.state == "Discharging" and battery_data.discharge_rate:
            self.state = battery_data.discharge_rate
        else:
            self.state = 0


class HealthSensor(BatterySubSensor):
    """Battery health/capacity sensor."""

    sensor_field = "capacity"
    name_suffix = "Health"

    def __init__(self, provider: BatteryDataProvider, battery_data: BatteryData):
        super().__init__(
            provider, battery_data,
            unit_of_measurement="%",
            state_class="measurement",
            entity_category="diagnostic",
        )


class ChargeCyclesSensor(BatterySubSensor):
    """Battery charge cycles sensor."""

    sensor_field = "charge_cycles"
    name_suffix = "Charge Cycles"

    def __init__(self, provider: BatteryDataProvider, battery_data: BatteryData):
        super().__init__(
            provider, battery_data,
            state_class="total_increasing",
            entity_category="diagnostic",
        )


class EnergySensor(BatterySubSensor):
    """Battery current energy sensor."""

    sensor_field = "energy"
    name_suffix = "Energy"

    def __init__(self, provider: BatteryDataProvider, battery_data: BatteryData):
        super().__init__(
            provider, battery_data,
            device_class="energy",
            native_unit_of_measurement="Wh",
            state_class="measurement",
            entity_category="diagnostic",
        )


class EnergyFullSensor(BatterySubSensor):
    """Battery full energy sensor."""

    sensor_field = "energy_full"
    name_suffix = "Energy Full"

    def __init__(self, provider: BatteryDataProvider, battery_data: BatteryData):
        super().__init__(
            provider, battery_data,
            device_class="energy",
            native_unit_of_measurement="Wh",
            state_class="measurement",
            entity_category="diagnostic",
        )
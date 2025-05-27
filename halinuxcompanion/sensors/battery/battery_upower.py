"""Battery sensors using UPower."""

import logging
from typing import Any, Dict, List, Optional

from halinuxcompanion.sensor_base import BaseSensor
from .battery_provider import BatteryData, BatteryDataProvider
from .battery_provider_upower import UPowerBatteryProvider
from . import subsensors

logger = logging.getLogger(__name__)


class UPowerSensor(BaseSensor):
    """Battery percentage sensor using UPower."""

    config_name = "battery_upower"

    def __init__(self, provider: BatteryDataProvider, battery_data: BatteryData):
        super().__init__(
            instance_id=battery_data.battery_id,
            unique_id=f"battery_upower_{battery_data.battery_id}",
            name=battery_data.name,
            device_class="battery",
            unit_of_measurement="%",
            state_class="measurement",
        )
        self._provider = provider
        self._battery_id = battery_data.battery_id
        self._battery_data = battery_data

    @classmethod
    async def discover_sensors(cls, config: Optional[Dict[str, Any]] = None) -> List["UPowerSensor"]:
        """Discover battery sensors."""
        provider = UPowerBatteryProvider()
        battery_ids = await provider.discover_batteries()

        sensors = []
        for battery_id in battery_ids:
            battery_data = await provider.get_battery_data(battery_id)
            if battery_data:
                sensors.append(cls(provider, battery_data))

        return sensors

    def get_metadata(self):
        """Get sensor metadata with dynamic icon."""
        metadata = super().get_metadata()

        # Update icon based on battery data
        if self._battery_data:
            metadata.icon = self._battery_data.get_icon()

        return metadata

    async def update(self) -> None:
        """Update battery state."""
        self._battery_data = await self._provider.get_battery_data(self._battery_id)

        if self._battery_data:
            self.state = self._battery_data.percent
            # Basic attributes - other data will be in separate sensors
            self.attributes = {
                "power_plugged": self._battery_data.plugged,
                "battery_state": self._battery_data.state,
            }
        else:
            self.state = "unavailable"
            self.attributes = {}


# Helper function for subsensor discovery
async def _discover_subsensors(sensor_class):
    """Common discovery logic for UPower subsensors."""
    provider = UPowerBatteryProvider()
    battery_ids = await provider.discover_batteries()

    sensors = []
    for battery_id in battery_ids:
        battery_data = await provider.get_battery_data(battery_id)
        if battery_data:
            sensors.append(sensor_class(provider, battery_data))

    return sensors


# Create wrapper classes for all UPower subsensors
class UPowerTimeToEmptySensor(subsensors.TimeToEmptySensor):
    config_name = "battery_upower_time_to_empty"

    @classmethod
    async def discover_sensors(cls, config=None):
        return await _discover_subsensors(cls)


class UPowerTimeToFullSensor(subsensors.TimeToFullSensor):
    config_name = "battery_upower_time_to_full"

    @classmethod
    async def discover_sensors(cls, config=None):
        return await _discover_subsensors(cls)


class UPowerTemperatureSensor(subsensors.TemperatureSensor):
    config_name = "battery_upower_temperature"

    @classmethod
    async def discover_sensors(cls, config=None):
        return await _discover_subsensors(cls)


class UPowerVoltageSensor(subsensors.VoltageSensor):
    config_name = "battery_upower_voltage"

    @classmethod
    async def discover_sensors(cls, config=None):
        return await _discover_subsensors(cls)


class UPowerPowerSensor(subsensors.PowerSensor):
    config_name = "battery_upower_power"

    @classmethod
    async def discover_sensors(cls, config=None):
        return await _discover_subsensors(cls)


class UPowerHealthSensor(subsensors.HealthSensor):
    config_name = "battery_upower_health"

    @classmethod
    async def discover_sensors(cls, config=None):
        return await _discover_subsensors(cls)


class UPowerChargeCyclesSensor(subsensors.ChargeCyclesSensor):
    config_name = "battery_upower_charge_cycles"

    @classmethod
    async def discover_sensors(cls, config=None):
        return await _discover_subsensors(cls)


class UPowerEnergySensor(subsensors.EnergySensor):
    config_name = "battery_upower_energy"

    @classmethod
    async def discover_sensors(cls, config=None):
        return await _discover_subsensors(cls)


class UPowerEnergyFullSensor(subsensors.EnergyFullSensor):
    config_name = "battery_upower_energy_full"

    @classmethod
    async def discover_sensors(cls, config=None):
        return await _discover_subsensors(cls)
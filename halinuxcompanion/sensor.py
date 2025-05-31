import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from aiohttp import ClientError

from halinuxcompanion.api import API
from halinuxcompanion.dbus import Dbus, register_sensor_dbus_handlers
from halinuxcompanion.hardware import (
    BluetoothHardwareClass,
    CameraHardwareClass,
    CPUHardwareClass,
    LidHardwareClass,
    MemoryHardwareClass,
    NetworkHardwareClass,
    TemperatureHardwareClass,
    UptimeHardwareClass,
)
from halinuxcompanion.hardware.battery_hardware import BatteryHardwareClass
from halinuxcompanion.hardware_base import HardwareClass, HardwareSensor

if TYPE_CHECKING:
    from halinuxcompanion.api import API
    from halinuxcompanion.dbus import Dbus

logger = logging.getLogger(__name__)

SC_REGISTER_SENSOR = 301

# Map of hardware config fields to hardware classes
HARDWARE_CLASSES = {
    hw_class.config_field: hw_class  # type: ignore[attr-defined]
    for hw_class in [
        BatteryHardwareClass,
        BluetoothHardwareClass,
        CameraHardwareClass,
        CPUHardwareClass,
        LidHardwareClass,
        MemoryHardwareClass,
        NetworkHardwareClass,
        TemperatureHardwareClass,
        UptimeHardwareClass,
    ]
}


@dataclass
class SensorManager:
    """Manages sensors registration, and updates to Home Assistant"""

    api: API
    dbus: Dbus
    update_counter: int = 0
    sensors: list[HardwareSensor] = field(default_factory=list)
    hardware_instances: list[HardwareClass] = field(default_factory=list)

    async def update_sensors(self) -> bool:
        """Update all sensors with Home Assistant

        :return: True if the update was successful, False otherwise
        """
        # Skip update if no sensors
        if not self.sensors:
            return True

        self.update_counter += 1

        # Update all hardware classes (which update their sensors directly)
        await asyncio.gather(
            *[hw.update_all_sensors() for hw in self.hardware_instances],
            return_exceptions=True,
        )

        prefix = f"Sensors update {self.update_counter}"
        logger.info(
            f"{prefix} with sensors: {' '.join(s.unique_id for s in self.sensors)}"
        )

        try:
            res = await self.api.webhook_post(
                {
                    "type": "update_sensor_states",
                    "data": [
                        {
                            "attributes": sensor.attributes,
                            "icon": sensor.icon,
                            "state": sensor.state,
                            "type": sensor.type,
                            "unique_id": sensor.unique_id,
                        }
                        for sensor in self.sensors
                    ],
                }
            )
        except ClientError as e:
            logger.error(f"{prefix} failed with {e=}")
            return False
        if res.ok or res.status == SC_REGISTER_SENSOR:
            logger.info(f"{prefix} successful")
            return True
        logger.error(f"{prefix} failed with {res.status=}")
        return False

    async def discover_and_register_sensors(self) -> None:
        """Discover and register sensors."""
        # Get sensor configs from companion
        if not (companion := getattr(self.api, "companion", None)):
            logger.error("No companion object found in API")
            return

        # Discover sensors for each enabled hardware class
        for hw_name, hw_class in HARDWARE_CLASSES.items():
            hw_config = getattr(companion.hardware, hw_name)
            if not hw_config.enabled:
                continue
            logger.info(f"Discovering {hw_name} sensors...")
            self.hardware_instances.append(hw_class(hw_config))  # type: ignore[abstract]

        for hw_instance in self.hardware_instances:
            self.sensors.extend(await hw_instance.discover_sensors())

        if not self.sensors:
            logger.warning(
                "No sensors discovered! Check sensor configuration and system capabilities."
            )
            return

        logger.info(
            f"Discovered {len(self.sensors)} sensors: {' '.join(sensor.unique_id for sensor in self.sensors)}"
        )

        # Register all discovered sensors
        await self._register_sensors()

        # Register D-Bus handlers for each sensor
        await asyncio.gather(
            *[
                register_sensor_dbus_handlers(sensor, self.dbus)
                for sensor in self.sensors
            ]
        )

    async def _register_sensors(self) -> None:
        """Register all sensors with Home Assistant."""
        await asyncio.gather(
            *[self._register_sensor(sensor) for sensor in self.sensors]
        )

    async def _register_sensor(self, sensor: HardwareSensor) -> None:
        """Register a single sensor with Home Assistant."""
        data = {
            "attributes": sensor.attributes,
            "device_class": sensor.device_class,
            "icon": sensor.icon,
            "name": sensor.name,
            "state": sensor.state,
            "type": sensor.type,
            "unique_id": sensor.unique_id,
            "unit_of_measurement": sensor.unit,
            "state_class": sensor.state_class,
            "entity_category": None,  # sensor.entity_category,
        }
        payload = {"data": data, "type": "register_sensor"}
        logger.info(f"Registering sensor: {sensor.unique_id}")
        logger.debug(f"Registration {payload=}")

        res = await self.api.webhook_post(payload)

        if not (res.ok or res.status == SC_REGISTER_SENSOR):
            raise RuntimeError(
                f"Sensor registration failed for {sensor.unique_id} with {res.status=}"
            )

        logger.info(f"Sensor registration successful: {sensor.unique_id}")

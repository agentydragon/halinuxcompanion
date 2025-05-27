import asyncio
import logging
from typing import TYPE_CHECKING

from aiohttp import ClientError

from halinuxcompanion.api import API
from halinuxcompanion.dbus import Dbus, register_sensor_dbus_handlers
from halinuxcompanion.hardware import (
    BatteryHardwareClass,
    BluetoothHardwareClass,
    CameraHardwareClass,
    CPUHardwareClass,
    LidHardwareClass,
    MemoryHardwareClass,
    NetworkHardwareClass,
    TemperatureHardwareClass,
    UptimeHardwareClass,
)
from halinuxcompanion.sensor_base import BaseSensor, DiscoverySensorManager

if TYPE_CHECKING:
    from halinuxcompanion.api import API
    from halinuxcompanion.dbus import Dbus

logger = logging.getLogger(__name__)

SC_REGISTER_SENSOR = 301


class SensorManager:
    """Manages sensors registration, and updates to Home Assistant"""

    api: API
    update_counter: int = 0
    sensors: list[BaseSensor] = []
    dbus: Dbus
    discovery_managers: list[DiscoverySensorManager] = []
    hardware_instances: dict[str, "HardwareClass"] = {}

    def __init__(self, api: API, dbus: Dbus) -> None:
        self.api = api
        self.dbus = dbus

    async def register_sensors(self):
        """Register all sensors with Home Assistant"""
        # Discover and register sensors
        await self.discover_and_register_sensors()

    async def update_sensors(self) -> bool:
        """Update all sensors with Home Assistant

        :return: True if the update was successful, False otherwise
        """
        # Skip update if no sensors
        if not self.sensors:
            return True

        self.update_counter += 1

        # First, update all hardware classes (bulk updates)
        hw_update_tasks = []
        for hw_instance in self.hardware_instances.values():
            hw_update_tasks.append(hw_instance.update_all_sensors())
        await asyncio.gather(*hw_update_tasks, return_exceptions=True)

        # Then update individual sensors to extract values from cached data
        update_tasks = []
        for sensor in self.sensors:
            update_tasks.append(sensor.update())
        await asyncio.gather(*update_tasks, return_exceptions=True)

        # Build update payload
        updates = []
        for sensor in self.sensors:
            metadata = sensor.get_metadata()
            updates.append(
                {
                    "attributes": sensor.attributes,
                    "icon": metadata.icon,
                    "state": sensor.state,
                    "type": sensor.sensor_type,
                    "unique_id": metadata.unique_id,
                }
            )

        data = {
            "type": "update_sensor_states",
            "data": updates,
        }

        all_names = [s.get_metadata().unique_id for s in self.sensors]
        prefix = f"Sensors update {self.update_counter}"
        logger.info(f"{prefix} with sensors: {all_names}")
        logger.debug(f"{prefix} with {data=}")

        try:
            res = await self.api.webhook_post("update_sensors", data=data)
            if res.ok or res.status == SC_REGISTER_SENSOR:
                logger.info(f"{prefix} successful")
                return True
            else:
                logger.error(f"{prefix} failed with {res.status=}")
        except ClientError as e:
            logger.error(f"{prefix} failed with {e=}")

        return False

    async def discover_and_register_sensors(self) -> None:
        """Discover and register sensors."""
        # Get sensor configs from companion
        companion = getattr(self.api, "companion", None)
        if not companion:
            logger.error("No companion object found in API")
            return

        # Map of hardware config fields to hardware classes
        hardware_classes = {
            "battery": BatteryHardwareClass,
            "network": NetworkHardwareClass,
            "cpu": CPUHardwareClass,
            "memory": MemoryHardwareClass,
            "lid": LidHardwareClass,
            "temperature": TemperatureHardwareClass,
            "camera": CameraHardwareClass,
            "bluetooth": BluetoothHardwareClass,
            "uptime": UptimeHardwareClass,
            # Status sensor doesn't fit the model - it uses D-Bus signals
        }

        # Discover sensors for each enabled hardware class
        for hw_name, hw_class in hardware_classes.items():
            hw_config = getattr(companion.hardware, hw_name, None)
            if hw_config and hw_config.enabled:
                logger.info(f"Discovering {hw_name} sensors...")
                hw_instance = hw_class(hw_config)
                self.hardware_instances[hw_name] = hw_instance
                discovered = await hw_instance.discover_sensors()
                for sensor in discovered:
                    self.sensors.append(sensor)
                    logger.info(f"Discovered sensor: {sensor.get_metadata().unique_id}")

        if not self.sensors:
            logger.warning("No sensors discovered! Check sensor configuration and system capabilities.")
            return

        logger.info(f"Total sensors discovered: {len(self.sensors)}")

        # Create discovery managers for sensors that support it
        discovery_classes = set()
        for sensor in self.sensors:
            if hasattr(sensor, "start_discovery") and sensor.__class__ not in discovery_classes:
                discovery_classes.add(sensor.__class__)
                manager = DiscoverySensorManager(sensor.__class__, self)
                self.discovery_managers.append(manager)

        # Register all discovered sensors
        await self._register_sensors()

        # Register D-Bus handlers for each sensor
        for sensor in self.sensors:
            await register_sensor_dbus_handlers(sensor, self.dbus)

        # Start discovery managers
        for manager in self.discovery_managers:
            await manager.start()

    async def _register_sensors(self) -> None:
        """Register all sensors with Home Assistant."""
        await asyncio.gather(*[self._register_sensor(sensor) for sensor in self.sensors])

    async def _register_sensor(self, sensor: BaseSensor) -> None:
        """Register a single sensor with Home Assistant."""
        metadata = sensor.get_metadata()

        # Build registration payload
        data = {
            "attributes": sensor.attributes,
            "device_class": metadata.device_class,
            "icon": metadata.icon,
            "name": metadata.name,
            "state": sensor.state,
            "type": sensor.sensor_type,
            "unique_id": metadata.unique_id,
            "unit_of_measurement": metadata.unit_of_measurement,
            "state_class": metadata.state_class,
            "entity_category": metadata.entity_category,
        }
        # Remove empty values
        data = {k: v for k, v in data.items() if v}

        payload = {"data": data, "type": "register_sensor"}
        logger.info(f"Registering sensor: {metadata.unique_id}")
        logger.debug(f"Registration {payload=}")

        res = await self.api.webhook_post("register_sensor", data=payload)

        if not (res.ok or res.status == SC_REGISTER_SENSOR):
            raise RuntimeError(f"Sensor registration failed for {metadata.unique_id} with {res.status=}")

        logger.info(f"Sensor registration successful: {metadata.unique_id}")

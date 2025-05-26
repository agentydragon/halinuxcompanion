import asyncio
import logging
from functools import partial, update_wrapper
from types import MethodType
from typing import Callable, Dict, Union, TYPE_CHECKING

from aiohttp import ClientError

from halinuxcompanion.api import API
from halinuxcompanion.companion import Companion
from halinuxcompanion.dbus import Dbus, register_sensor_dbus_handlers
from halinuxcompanion.sensor_base import BaseSensor, SensorMetadata, DiscoverySensorManager
from . import sensors

if TYPE_CHECKING:
    from halinuxcompanion.api import API
    from halinuxcompanion.dbus import Dbus

logger = logging.getLogger(__name__)

SC_REGISTER_SENSOR = 301


class Sensor:
    """Standard sensor class"""

    instances = []

    def __init__(self):
        self.config_name: str
        self.attributes: dict = {}
        self.device_class: str = ""
        self.state_class: str = ""
        self.icon: str
        self.name: str
        self.state: Union[str, int, float] = ""
        self.type: str
        self.unique_id: str
        self.unit_of_measurement: str = ""
        self.state_class: str = ""
        self.entity_category: str = ""
        self.type: str
        # Signal name (halinuxcompanion.dbus) and it's callback
        self.signals: Dict[str, Callable] = {}
        Sensor.instances.append(self)

    # TODO: Should be async
    def updater(self) -> None:
        """To be called every time update is called"""
        pass

    def register(self) -> dict:
        self.updater()
        """Payload to register the sensor"""
        data = {
            "attributes": self.attributes,
            "device_class": self.device_class,
            "icon": self.icon,
            "name": self.name,
            "state": self.state,
            "type": self.type,
            "unique_id": self.unique_id,
            "unit_of_measurement": self.unit_of_measurement,
            "state_class": self.state_class,
            "entity_category": self.entity_category,
        }
        return {k: v for k, v in data.items() if v != ""}

    def update(self) -> dict:
        """Payload to update the sensor"""
        self.updater()
        return {
            "attributes": self.attributes,
            "icon": self.icon,
            "state": self.state,
            "type": self.type,
            "unique_id": self.unique_id,
        }


class SensorManager:
    """Manages sensors registration, and updates to Home Assistant"""

    api: API
    update_counter: int = 0
    sensors: list[Sensor] = []
    new_sensors: list[BaseSensor] = []
    dbus: Dbus
    discovery_managers: list[DiscoverySensorManager] = []

    def __init__(self, api: API, sensors: list[Sensor], dbus: Dbus) -> None:
        self.api = api
        self.sensors = sensors
        self.dbus = dbus

    async def register_sensors(self):
        """Register all sensors with Home Assistant
        If all have been registered successfully, register each sensor signals
        """
        # Register legacy sensors
        await asyncio.gather(*[self._register_sensor(s) for s in self.sensors])
        await self.register_signals()
        
        # Discover and register new architecture sensors
        await self.discover_and_register_new_sensors()

    async def _register_sensor(self, sensor: Sensor):
        """Register a sensor with Home Assisntat
        If the registration fails it's a critical error and the program should exit.

        :param sensor: The sensor to register
        :return: True if the registration was successful, False otherwise
        """
        data = {"data": sensor.register(), "type": "register_sensor"}
        sname = sensor.config_name
        logger.info(f"Registering sensor:{sname} {data=}")
        res = await self.api.webhook_post("register_sensor", data=data)

        if not (res.ok or res.status == SC_REGISTER_SENSOR):
            raise RuntimeError(f"Sensor registration failed for {sname} with status code: {res.status}")

        logger.info(f"Sensor registration successful: {sname}")

    async def update_sensors(self, sensors: list[Sensor] | None = None) -> bool:
        """Update the given sensors with Home Assistant
        If the update fails it's an error and it should be retried by the caller.

        :param sensors: The sensors to update, if empty all sensors will be updated
        :return: True if the update was successful, False otherwise
        """
        # Handle both legacy and new sensors
        if sensors is None:
            # Update all sensors
            return await self._update_all_sensors()
        else:
            # Update specific legacy sensors
            return await self._update_legacy_sensors(sensors)
            
    async def _update_all_sensors(self) -> bool:
        """Update both legacy and new sensors."""
        self.update_counter += 1
        
        # Update new sensors first
        update_tasks = []
        for sensor in self.new_sensors:
            update_tasks.append(sensor.update())
        await asyncio.gather(*update_tasks, return_exceptions=True)
        
        # Build combined update payload
        updates = []
        
        # Add legacy sensor updates
        for sensor in self.sensors:
            updates.append(sensor.update())
            
        # Add new sensor updates
        for sensor in self.new_sensors:
            metadata = sensor.get_metadata()
            updates.append({
                "attributes": sensor.attributes,
                "icon": metadata.icon,
                "state": sensor.state,
                "type": sensor.sensor_type,
                "unique_id": metadata.unique_id,
            })
            
        data = {
            "type": "update_sensor_states",
            "data": updates,
        }
        
        all_names = [s.config_name for s in self.sensors] + [s.get_metadata().unique_id for s in self.new_sensors]
        prefix = f"Sensors update {self.update_counter}"
        logger.info(f"{prefix} with sensors: {all_names}")
        logger.debug(f"{prefix} with data: {data}")
        
        try:
            res = await self.api.webhook_post("update_sensors", data=data)
            if res.ok or res.status == SC_REGISTER_SENSOR:
                logger.info(f"{prefix} successful")
                return True
            else:
                logger.error(f"{prefix} failed with status code: {res.status}")
        except ClientError as e:
            logger.error(f"{prefix} failed with error: {e}")
            
        return False
        
    async def _update_legacy_sensors(self, sensors: list[Sensor]) -> bool:
        """Update specific legacy sensors."""
        self.update_counter += 1
        data = {
            "type": "update_sensor_states",
            "data": [sensor.update() for sensor in sensors],
        }
        snames = [sensor.config_name for sensor in sensors]
        prefix = f"Sensors update {self.update_counter}"
        logger.info(f"{prefix} with sensors: {snames}")
        logger.debug(f"{prefix} with sensors: {snames} {data=}")
        try:
            res = await self.api.webhook_post("update_sensors", data=data)
            if res.ok or res.status == SC_REGISTER_SENSOR:
                logger.info(f"{prefix} successful")
                return True
            else:
                logger.error(
                    f"{prefix} failed with status code:{res.status}",
                )
        except ClientError:
            logger.error(f"{prefix} failed with error:%s")

        return False

    async def _signal_handler(self, signal_alias: str, signal_handler: Callable, sensor: Sensor, *args) -> None:
        """Signal handler for the sensor manager
        Each sensor can have multiple signals, at the moment defined in halinuxcompanion.dbus, the callback provided for
        the signal is this function wrapped in a functools.partial this allows for the SensorManager to be in charge of
        actually calling the sensor callback and therefore be able to know when to update it.

        :param sensor: The sensor that the signal belongs to
        :param signal_alias: The signal alias (defined in halinuxcompanion.dbus)
        :param signal_handler: The signal handler (defined by the sensor in sensor.signals)
        :param args: The arguments to pass to the signal handler (coming from the dbus signal)
        """
        logger.info("Signal %s received for sensor:%s", signal_alias, sensor.unique_id)
        await signal_handler(sensor, *args)
        await self.update_sensors([sensor])

    async def register_signals(self) -> None:
        """Register all signals from all sensors.
        Each sensor defines signals with a name and callback, which is called by self._signal_handler
        """
        for sensor in self.sensors:
            for signal_alias, signal_handler in sensor.signals.items():
                callback = partial(self._signal_handler, signal_alias, signal_handler)
                callback = MethodType(update_wrapper(callback, signal_handler), sensor)
                await self.dbus.register_signal(signal_alias, callback)
                
    async def discover_and_register_new_sensors(self) -> None:
        """Discover and register sensors using the new architecture."""
        # Get sensor configs from companion
        companion = getattr(self.api, 'companion', None)
        if not companion:
            return
        
        # Discover sensors for each enabled type
        for sensor_class in BaseSensor.__subclasses__():
            config_name = getattr(sensor_class, 'config_name', None)
            if config_name and config_name in companion.sensors and companion.sensors[config_name]:
                logger.info(f"Discovering {config_name} sensors...")
                try:
                    discovered = await sensor_class.discover_sensors()
                    for sensor in discovered:
                        # Apply custom name if configured
                        if config_name in companion.sensor_names:
                            metadata = sensor.get_metadata()
                            metadata.name = companion.sensor_names[config_name]
                        self.new_sensors.append(sensor)
                        logger.info(f"Discovered sensor: {sensor.get_metadata().unique_id}")
                except Exception as e:
                    logger.error(f"Failed to discover {config_name} sensors: {e}")
                    
        # Create discovery managers for sensors that support it
        discovery_classes = set()
        for sensor in self.new_sensors:
            if hasattr(sensor, "start_discovery") and sensor.__class__ not in discovery_classes:
                discovery_classes.add(sensor.__class__)
                manager = DiscoverySensorManager(sensor.__class__, self)
                self.discovery_managers.append(manager)
                
        # Register all discovered sensors
        await self._register_new_sensors()
        
        # Register D-Bus handlers for each sensor
        for sensor in self.new_sensors:
            await register_sensor_dbus_handlers(sensor, self.dbus)
            
        # Start discovery managers
        for manager in self.discovery_managers:
            await manager.start()
            
    async def _register_new_sensors(self) -> None:
        """Register all new architecture sensors with Home Assistant."""
        await asyncio.gather(*[self._register_new_sensor(sensor) for sensor in self.new_sensors])
        
    async def _register_new_sensor(self, sensor: BaseSensor) -> None:
        """Register a single new architecture sensor with Home Assistant."""
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
        logger.info(f"Registering new sensor: {metadata.unique_id}")
        logger.debug(f"Registration payload: {payload}")
        
        res = await self.api.webhook_post("register_sensor", data=payload)
        
        if not (res.ok or res.status == SC_REGISTER_SENSOR):
            raise RuntimeError(f"Sensor registration failed for {metadata.unique_id} with status code: {res.status}")
            
        logger.info(f"Sensor registration successful: {metadata.unique_id}")
        
    async def add_sensor(self, sensor: BaseSensor) -> None:
        """Add a new sensor at runtime and register it."""
        self.new_sensors.append(sensor)
        await self._register_new_sensor(sensor)
        await register_sensor_dbus_handlers(sensor, self.dbus)
        logger.info(f"Added new sensor: {sensor.get_metadata().unique_id}")
        
    async def remove_sensor(self, sensor: BaseSensor) -> None:
        """Remove a sensor at runtime."""
        if sensor in self.new_sensors:
            self.new_sensors.remove(sensor)
            # TODO: Unregister from Home Assistant
            logger.info(f"Removed sensor: {sensor.get_metadata().unique_id}")
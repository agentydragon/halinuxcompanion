import asyncio
import logging
from dataclasses import dataclass, field

from aiohttp import ClientError

from halinuxcompanion.api import API
from halinuxcompanion.dbus import Dbus, register_sensor_dbus_handlers
from halinuxcompanion.module_base import Module, Sensor
from halinuxcompanion.module_config import ModulesConfig

from .constants import SC_REGISTER_SENSOR

logger = logging.getLogger(__name__)


@dataclass
class SensorManager:
    """Manages sensors registration, and updates to Home Assistant"""

    api: API
    dbus: Dbus
    module_config: ModulesConfig
    update_counter: int = 0
    sensors: list[Sensor] = field(default_factory=list)
    module_instances: list[Module] = field(default_factory=list)
    _last_sensor_ids: set[str] = field(default_factory=set)
    _last_full_log_time: float = field(default_factory=lambda: asyncio.get_event_loop().time())

    async def update_sensors(self) -> bool:
        """Update all sensors with Home Assistant

        :return: True if the update was successful, False otherwise
        """
        # Skip update if no sensors
        if not self.sensors:
            return True

        self.update_counter += 1

        # Update all modules (which update their sensors directly)
        await asyncio.gather(
            *[module.update_all_sensors() for module in self.module_instances],
            return_exceptions=True,
        )

        # Check for sensor changes
        current_sensor_ids = {s.unique_id for s in self.sensors}
        added = current_sensor_ids - self._last_sensor_ids
        removed = self._last_sensor_ids - current_sensor_ids

        # Log based on what changed
        prefix = f"Sensors update {self.update_counter}"
        current_time = asyncio.get_event_loop().time()
        hours_since_last_full_log = (current_time - self._last_full_log_time) / 3600

        if added or removed or hours_since_last_full_log >= 1:
            # Log full list if changes or every hour
            if added:
                logger.info(f"{prefix}: Added sensors: {' '.join(added)}")
            if removed:
                logger.info(f"{prefix}: Removed sensors: {' '.join(removed)}")

            if hours_since_last_full_log >= 1:
                logger.info(
                    f"{prefix}: Full sensor list ({len(self.sensors)} total): {' '.join(s.unique_id for s in self.sensors)}"
                )
                self._last_full_log_time = current_time
            else:
                logger.info(f"{prefix}: Total {len(self.sensors)} sensors")

            self._last_sensor_ids = current_sensor_ids
        else:
            # Just log the count for regular updates
            logger.debug(f"{prefix}: Updating {len(self.sensors)} sensors")

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
            logger.exception(f"{prefix} failed with {e=}")
            return False
        if res.ok or res.status == SC_REGISTER_SENSOR:
            logger.info(f"{prefix} successful")
            return True
        logger.error(f"{prefix} failed with {res.status=}")
        return False

    async def discover_and_register_sensors(self) -> None:
        """Discover and register sensors."""
        self.module_instances = [
            module_class(config) for module_class, config in self.module_config.get_enabled_module_classes()
        ]

        for module_instance in self.module_instances:
            logger.info(f"Discovering {module_instance.__class__.__name__} sensors...")
            self.sensors.extend(await module_instance.discover_sensors())

        if not self.sensors:
            logger.warning("No sensors discovered! Check sensor configuration and system capabilities.")
            return

        logger.info(f"Discovered {len(self.sensors)} sensors: {' '.join(sensor.unique_id for sensor in self.sensors)}")

        # Register all discovered sensors
        await self._register_sensors()

        # Register D-Bus handlers for each sensor
        await asyncio.gather(*[register_sensor_dbus_handlers(sensor, self.dbus) for sensor in self.sensors])

    async def _register_sensors(self) -> None:
        """Register all sensors with Home Assistant."""
        await asyncio.gather(*[self._register_sensor(sensor) for sensor in self.sensors])

    async def _register_sensor(self, sensor: Sensor) -> None:
        """Register a single sensor with Home Assistant."""
        payload = {"data": sensor.to_registration_dict(), "type": "register_sensor"}
        logger.info(f"Registering sensor: {sensor.unique_id}")
        logger.debug(f"Registration {payload=}")

        res = await self.api.webhook_post(payload)

        if not (res.ok or res.status == SC_REGISTER_SENSOR):
            raise RuntimeError(f"Sensor registration failed for {sensor.unique_id} with {res.status=}")

        logger.info(f"Sensor registration successful: {sensor.unique_id}")

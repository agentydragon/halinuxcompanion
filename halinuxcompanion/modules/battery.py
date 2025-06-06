"""Battery module using UPower DBus service."""

import asyncio
import logging
from contextlib import asynccontextmanager
from enum import IntEnum
from typing import Any

from dbus_fast.aio import MessageBus

from .base import (
    BaseModule,
    DeviceClass,
    EntityCategory,
    SensorRegistration,
    SensorType,
    SensorUpdate,
    StateClass,
    UpdateListener,
)

logger = logging.getLogger(__name__)

UPOWER_NAME = "org.freedesktop.UPower"
UPOWER_ROOT = "/org/freedesktop/UPower"


class UPowerDeviceState(IntEnum):
    """UPower device states from org.freedesktop.UPower.Device."""

    UNKNOWN = 0
    CHARGING = 1
    DISCHARGING = 2
    EMPTY = 3
    FULLY_CHARGED = 4
    PENDING_CHARGE = 5
    PENDING_DISCHARGE = 6

    @classmethod
    def to_home_assistant_state(cls, state: int) -> str:
        """Convert UPower state to Home Assistant state."""
        return {
            cls.UNKNOWN.value: "unknown",
            cls.CHARGING.value: "charging",
            cls.DISCHARGING.value: "discharging",
            cls.EMPTY.value: "empty",
            cls.FULLY_CHARGED.value: "full",
            cls.PENDING_CHARGE.value: "pending_charge",
            cls.PENDING_DISCHARGE.value: "pending_discharge",
        }.get(state, "unknown")

    @classmethod
    def to_icon(cls, state: int) -> str:
        """Get icon for battery state."""
        return {
            cls.CHARGING.value: "mdi:battery-charging",
            cls.DISCHARGING.value: "mdi:battery-minus",
            cls.EMPTY.value: "mdi:battery-alert",
            cls.FULLY_CHARGED.value: "mdi:battery",
        }.get(state, "mdi:battery-unknown")


class UPowerDeviceType(IntEnum):
    """UPower device types from org.freedesktop.UPower.Device."""

    UNKNOWN = 0
    LINE_POWER = 1
    BATTERY = 2
    UPS = 3
    MONITOR = 4
    MOUSE = 5
    KEYBOARD = 6
    PDA = 7
    PHONE = 8


class BatteryModule(BaseModule):
    """Module for battery monitoring via UPower."""

    def __init__(self, system_bus: MessageBus):
        """Initialize battery module.

        Args:
            system_bus: System bus instance.
        """
        self._system_bus = system_bus
        self._update_listener: UpdateListener | None = None
        self._display_device_iface: Any = None  # ProxyInterface from dbus-fast
        self._display_properties_iface: Any = None  # ProxyInterface from dbus-fast

    def sensors(self) -> list[SensorRegistration]:
        """Return list of sensors this module provides."""
        return [
            SensorRegistration(
                unique_id="battery_level",
                type=SensorType.SENSOR.value,
                name="Battery Level",
                state=None,
                icon="mdi:battery",
                unit_of_measurement="%",
                device_class=DeviceClass.BATTERY,
                state_class=StateClass.MEASUREMENT,
            ),
            SensorRegistration(
                unique_id="battery_state",
                type=SensorType.SENSOR.value,
                name="Battery State",
                state="unknown",
                icon="mdi:battery-unknown",
            ),
            SensorRegistration(
                unique_id="battery_power",
                type=SensorType.SENSOR.value,
                name="Battery Power",
                state=None,
                icon="mdi:lightning-bolt",
                unit_of_measurement="W",
                device_class=DeviceClass.POWER,
                state_class=StateClass.MEASUREMENT,
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            SensorRegistration(
                unique_id="battery_time_to_empty",
                type=SensorType.SENSOR.value,
                name="Battery Time to Empty",
                state=None,
                icon="mdi:timer-sand",
                unit_of_measurement="s",
                device_class=DeviceClass.DURATION,
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            SensorRegistration(
                unique_id="battery_time_to_full",
                type=SensorType.SENSOR.value,
                name="Battery Time to Full",
                state=None,
                icon="mdi:timer-sand",
                unit_of_measurement="s",
                device_class=DeviceClass.DURATION,
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
        ]

    async def start(self, update_listener: UpdateListener) -> None:
        """Start monitoring battery status."""
        assert self._update_listener is None, "Module already started"
        self._update_listener = update_listener
        logger.debug("Starting...")

        try:
            introspect = await self._system_bus.introspect(UPOWER_NAME, UPOWER_ROOT)
            upower_proxy = self._system_bus.get_proxy_object(UPOWER_NAME, UPOWER_ROOT, introspect)
            display_device_path = await upower_proxy.get_interface(UPOWER_NAME).call_get_display_device()
            display_obj = self._system_bus.get_proxy_object(
                UPOWER_NAME, display_device_path, await self._system_bus.introspect(UPOWER_NAME, display_device_path)
            )
        except Exception:
            logger.exception("Failed to get or introspect display device")
            raise

        self._display_device_iface = display_obj.get_interface("org.freedesktop.UPower.Device")
        self._display_properties_iface = display_obj.get_interface("org.freedesktop.DBus.Properties")
        self._display_properties_iface.on_properties_changed(self._handle_properties_changed)
        logger.debug("Initialized, calling update...")
        await self._update()

    async def _handle_properties_changed(self, _interface: str, _changed, _invalidated: list[str]) -> None:
        """Handle properties changed signal from UPower."""
        await self._update()

    async def stop(self) -> None:
        """Stop monitoring and clean up resources."""
        assert self._update_listener is not None, "Module not started"
        self._update_listener = None
        if self._display_properties_iface:
            self._display_properties_iface.off_properties_changed(self._handle_properties_changed)
        self._display_properties_iface = None

    @asynccontextmanager
    async def context(self, update_listener) -> Any:
        """Provide an async context manager for the battery module."""
        try:
            await self.start(update_listener)
            yield self
        finally:
            await self.stop()

    async def _update(self) -> None:
        """Update battery sensor states."""
        logger.debug("Updating battery state")
        try:
            percentage = await self._display_device_iface.get_percentage()
            state = await self._display_device_iface.get_state()
            energy_rate = await self._display_device_iface.get_energy_rate()
            time_to_empty = await self._display_device_iface.get_time_to_empty()
            time_to_full = await self._display_device_iface.get_time_to_full()

        except Exception:
            logger.exception("Failed to get battery state")
            await self._send_unavailable_state()
            return

        # Power (positive = discharging, negative = charging)
        power = energy_rate if energy_rate > 0 else None
        if power and state == UPowerDeviceState.CHARGING:
            power = -power

        # Prepare all updates
        updates = [
            SensorUpdate(
                unique_id="battery_level",
                state=percentage if percentage > 0 else None,
                icon=self._get_battery_icon(percentage, state),
            ),
            SensorUpdate(
                unique_id="battery_state",
                state=UPowerDeviceState.to_home_assistant_state(state),
                icon=UPowerDeviceState.to_icon(state),
            ),
            SensorUpdate(unique_id="battery_power", state=power),
            SensorUpdate(unique_id="battery_time_to_empty", state=time_to_empty if time_to_empty > 0 else None),
            SensorUpdate(unique_id="battery_time_to_full", state=time_to_full if time_to_full > 0 else None),
        ]

        # Send all updates
        if self._update_listener is not None:
            await asyncio.gather(*[self._update_listener(update) for update in updates])

    async def _send_unavailable_state(self) -> None:
        """Send unavailable state for all sensors."""
        updates = [
            SensorUpdate(unique_id="battery_level", state=None),
            SensorUpdate(unique_id="battery_state", state=None),
            SensorUpdate(unique_id="battery_power", state=None),
            SensorUpdate(unique_id="battery_time_to_empty", state=None),
            SensorUpdate(unique_id="battery_time_to_full", state=None),
        ]
        if self._update_listener is not None:
            await asyncio.gather(*[self._update_listener(update) for update in updates])

    @classmethod
    def _get_battery_icon(cls, percentage: float, state: int) -> str:
        """Get appropriate battery icon based on level and state."""
        # Floor to nearest 10 for icon selection
        level = max(0, min(100, int(percentage / 10) * 10))
        if state == UPowerDeviceState.CHARGING:
            return f"mdi:battery-charging-{level}"
        if level == 100:
            return "mdi:battery"
        if level == 0:
            return "mdi:battery-alert"
        return f"mdi:battery-{level}"

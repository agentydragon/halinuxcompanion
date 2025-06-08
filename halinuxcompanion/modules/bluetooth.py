"""Bluetooth module using BlueZ DBus service."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from dbus_fast.aio import MessageBus
from dataclasses import dataclass, field
from typing import Any, TypeVar

import dbus_fast.errors

from ..dbus_utils import unwrap_variant
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

T = TypeVar("T")

BLUEZ_NAME = "org.bluez"
BLUEZ_ROOT = "/org/bluez"


@dataclass
class BluetoothAdapter:
    """Bluetooth adapter information."""

    path: str
    address: str
    system_bus: Any
    on_state_change: Callable[[], Awaitable[None]]
    object_manager: Any
    powered: bool = False
    interface: Any = None  # ProxyInterface
    properties_interface: Any = None  # ProxyInterface
    _signal_handlers: list[Any] = field(default_factory=list, init=False)

    @property
    def is_available(self) -> bool:
        """Check if adapter is available and powered."""
        return bool(self.interface and self.powered)

    async def start_monitoring(self) -> None:
        """Start monitoring this adapter."""
        # Subscribe to interface changes for this specific adapter
        handler_added = (  # noqa: E731
            lambda path, interfaces: asyncio.create_task(self._handle_interfaces_added(path, interfaces))
            if path == self.path
            else None
        )
        handler_removed = (  # noqa: E731
            lambda path, interfaces: asyncio.create_task(self._handle_interfaces_removed(path, interfaces))
            if path == self.path
            else None
        )

        self.object_manager.on_interfaces_added(handler_added)
        self.object_manager.on_interfaces_removed(handler_removed)
        self._signal_handlers = [handler_added, handler_removed]

        # Setup initial interfaces
        await self._setup_interfaces()

    async def _handle_interfaces_added(self, _path: str, interfaces: dict[str, dict[str, Any]]) -> None:
        """Handle interfaces being added to this adapter."""
        if "org.bluez.Adapter1" in interfaces:
            powered = interfaces["org.bluez.Adapter1"].get("Powered", False)
            self.powered = unwrap_variant(powered, bool) if powered else False
            await self._setup_interfaces()
            await self.on_state_change()

    async def _handle_interfaces_removed(self, _path: str, interfaces: list[str]) -> None:
        """Handle interfaces being removed from this adapter."""
        if "org.bluez.Adapter1" in interfaces:
            self._cleanup_interfaces()
            await self.on_state_change()

    async def _setup_interfaces(self) -> None:
        """Set up adapter interfaces."""
        try:
            introspect = await self.system_bus.introspect(BLUEZ_NAME, self.path)
            proxy = self.system_bus.get_proxy_object(BLUEZ_NAME, self.path, introspect)
            self.interface = proxy.get_interface("org.bluez.Adapter1")
            self.properties_interface = proxy.get_interface("org.freedesktop.DBus.Properties")

            # Subscribe to property changes
            self.properties_interface.on_properties_changed(
                lambda iface, changed, invalidated: asyncio.create_task(
                    self._handle_properties_changed(iface, changed, invalidated)
                )
            )
        except dbus_fast.errors.DBusError:
            logger.exception("Failed to setup adapter interfaces")
            self.interface = None
            self.properties_interface = None

    def _cleanup_interfaces(self) -> None:
        """Clean up adapter interfaces."""
        if self.properties_interface:
            # Note: off_properties_changed doesn't exist in dbus_fast, we'll handle this differently
            pass
        self.interface = None
        self.properties_interface = None
        self.powered = False

    def stop_monitoring(self) -> None:
        """Stop monitoring this adapter."""
        # Note: dbus_fast doesn't have proper signal unsubscription
        self._signal_handlers.clear()
        self._cleanup_interfaces()

    async def _handle_properties_changed(
        self, _interface: str, changed: dict[str, Any], _invalidated: list[str]
    ) -> None:
        """Handle adapter property changes."""
        if "Powered" in changed:
            self.powered = unwrap_variant(changed["Powered"], bool)
            await self.on_state_change()


@dataclass
class BluetoothDevice:
    """Bluetooth device information."""

    address: str
    system_bus: Any
    object_manager: Any
    path: str = ""
    name: str | None = None
    interface: Any = None  # ProxyInterface
    properties_interface: Any = None  # ProxyInterface
    battery_interface: Any | None = None  # ProxyInterface
    _update_listener: UpdateListener | None = field(default=None, init=False, repr=False)
    _adapter: BluetoothAdapter | None = field(default=None, init=False, repr=False)
    _signal_handlers: list[Any] = field(default_factory=list, init=False)

    @property
    def sensor_prefix(self) -> str:
        """Get the sensor ID prefix for this device."""
        return f"bluetooth_device_{self.address.replace(':', '_').lower()}"

    def sensor_id(self, sensor_type: str) -> str:
        """Get a specific sensor ID for this device."""
        return f"{self.sensor_prefix}_{sensor_type}"

    @property
    def is_discovered(self) -> bool:
        """Check if device has been discovered via DBus."""
        return bool(self.path and self.interface)

    async def start_monitoring(self) -> None:
        """Start monitoring for this device appearing/disappearing."""
        # Find any existing device with our address
        managed_objects = await self.object_manager.call_get_managed_objects()
        for path, interfaces in managed_objects.items():
            if "org.bluez.Device1" not in interfaces:
                continue
            device_props = interfaces["org.bluez.Device1"]
            address = unwrap_variant(device_props["Address"], str)
            if address.upper() == self.address:
                self.path = path
                await self._handle_device_appeared(path, interfaces)
                # Check if battery interface exists
                if "org.bluez.Battery1" in interfaces:
                    await self._setup_battery_interface()
                break

        # Subscribe to interface changes
        handler_added = lambda path, interfaces: asyncio.create_task(self._handle_interfaces_added(path, interfaces))  # noqa: E731
        handler_removed = lambda path, interfaces: asyncio.create_task(  # noqa: E731
            self._handle_interfaces_removed(path, interfaces)
        )

        self.object_manager.on_interfaces_added(handler_added)
        self.object_manager.on_interfaces_removed(handler_removed)
        self._signal_handlers = [handler_added, handler_removed]

    async def _handle_interfaces_added(self, path: str, interfaces: dict[str, dict[str, Any]]) -> None:
        """Handle interfaces being added."""
        # Check if this is our device appearing
        if "org.bluez.Device1" in interfaces:
            device_props = interfaces["org.bluez.Device1"]
            address = unwrap_variant(device_props["Address"], str)
            if address.upper() == self.address:
                self.path = path
                await self._handle_device_appeared(path, interfaces)
        # Check if this is our device getting new interfaces
        elif path == self.path:
            if "org.bluez.Battery1" in interfaces:
                await self._setup_battery_interface()
                await self._update_partial(["battery"])

    async def _handle_interfaces_removed(self, path: str, interfaces: list[str]) -> None:
        """Handle interfaces being removed."""
        if path != self.path:
            return

        if "org.bluez.Device1" in interfaces:
            # Device disappeared
            self._cleanup_all_interfaces()
            await self.update_full(self._adapter)
        elif "org.bluez.Battery1" in interfaces:
            # Battery interface removed
            self.battery_interface = None
            await self._update_partial(["battery"])

    async def _handle_device_appeared(self, _path: str, interfaces: dict[str, dict[str, Any]]) -> None:
        """Handle device appearing with all its interfaces."""
        device_props = interfaces["org.bluez.Device1"]

        # Try to get name from Alias or Name property
        alias = device_props.get("Alias")
        if alias:
            self.name = unwrap_variant(alias, str)
        else:
            name = device_props.get("Name")
            self.name = unwrap_variant(name, str) if name else self.address

        await self._setup_device_interfaces()
        await self.update_full(self._adapter)

    async def _setup_device_interfaces(self) -> None:
        """Set up device interfaces."""
        if not self.path:
            return

        try:
            introspect = await self.system_bus.introspect(BLUEZ_NAME, self.path)
            proxy = self.system_bus.get_proxy_object(BLUEZ_NAME, self.path, introspect)
            self.interface = proxy.get_interface("org.bluez.Device1")
            self.properties_interface = proxy.get_interface("org.freedesktop.DBus.Properties")

            # Subscribe to property changes
            self.properties_interface.on_properties_changed(
                lambda iface, changed, invalidated: asyncio.create_task(
                    self.handle_properties_changed(iface, changed, invalidated)
                )
            )

            # Check if battery interface exists in managed objects
            # We'll set this up based on ObjectManager data instead</
            self.battery_interface = None

        except dbus_fast.errors.DBusError:
            logger.exception("Failed to setup device interfaces for %s", self.address)

    async def _setup_battery_interface(self) -> None:
        """Set up battery interface."""
        if not self.path:
            return

        # For now, we'll just mark that battery is available
        # In a real implementation, we'd get the interface from introspection
        self.battery_interface = True
        logger.debug(f"Battery interface appeared for device {self.address}")

    def _cleanup_all_interfaces(self) -> None:
        """Clean up all device interfaces."""
        self.path = ""
        self.interface = None
        self.properties_interface = None
        self.battery_interface = None

    def stop_monitoring(self) -> None:
        """Stop monitoring this device."""
        self._signal_handlers.clear()
        self._cleanup_all_interfaces()

    def sensors(self) -> list[SensorRegistration]:
        """Return sensor registrations for this device."""
        # Use device name if known (without "Bluetooth" prefix), otherwise "Bluetooth MAC"
        base_name = self.name if self.name and self.name != self.address else f"Bluetooth {self.address}"

        return [
            SensorRegistration(
                unique_id=self.sensor_id("connected"),
                type=SensorType.BINARY_SENSOR,
                name=base_name,
                state=False,
                icon="mdi:bluetooth-connect",
                device_class=DeviceClass.CONNECTIVITY,
            ),
            SensorRegistration(
                unique_id=self.sensor_id("rssi"),
                type=SensorType.SENSOR,
                name=f"{base_name} RSSI",
                state=None,
                icon="mdi:signal",
                unit_of_measurement="dBm",
                state_class=StateClass.MEASUREMENT,
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            SensorRegistration(
                unique_id=self.sensor_id("battery"),
                type=SensorType.SENSOR,
                name=f"{base_name} Battery",
                state=None,
                icon="mdi:battery-bluetooth",
                unit_of_measurement="%",
                device_class=DeviceClass.BATTERY,
                state_class=StateClass.MEASUREMENT,
            ),
            SensorRegistration(
                unique_id=self.sensor_id("name"),
                type=SensorType.SENSOR,
                name=f"{base_name} Name",
                state=None,
                icon="mdi:bluetooth",
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
        ]

    def set_update_listener(self, update_listener: UpdateListener | None) -> None:
        """Set the update listener for this device."""
        self._update_listener = update_listener

    def set_adapter(self, adapter: BluetoothAdapter | None) -> None:
        """Set the adapter reference for this device."""
        self._adapter = adapter

    async def handle_properties_changed(
        self, _interface: str, changed: dict[str, Any], _invalidated: list[str]
    ) -> None:
        """Handle properties changed signal for this device."""
        # Only update sensors for properties that actually changed
        # Get current device state and send updates only for changed properties
        await self._update_partial(
            [
                sensor_type
                for prop, sensor_type in {
                    "Connected": "connected",
                    "RSSI": "rssi",
                    "Name": "name",
                    "Alias": "name",
                    "Percentage": "battery",
                }.items()
                if prop in changed
            ]
        )

    async def _update_partial(self, sensor_types: list[str]) -> None:
        """Update only specific sensors for this device.

        Args:
            sensor_types: List of sensor types to update (e.g. ["connected", "rssi"])
        """
        if not self._update_listener:
            return

        # Map sensor types to their update methods
        sensor_updaters = {
            "connected": self._get_connected_update,
            "rssi": self._get_rssi_update,
            "name": self._get_name_update,
            "battery": self._get_battery_update,
        }

        # Build coroutines for requested sensors
        update_coroutines = [
            sensor_updaters[sensor_type]() for sensor_type in sensor_types if sensor_type in sensor_updaters
        ]

        updates = await asyncio.gather(*update_coroutines, return_exceptions=True)

        # Send updates and log exceptions
        for update in updates:
            if isinstance(update, Exception):
                logger.error("Failed to get sensor update: %s", update)
            elif isinstance(update, SensorUpdate):
                await self._update_listener(update)

    async def _get_property_safe(
        self,
        getter: Callable[[], Awaitable[Any]],
        expected_type: type[T],
        timeout: float = 1.0,
        default: T | None = None,
    ) -> T | None:
        """Safely get a property with timeout and exception handling, including unwrapping variants."""
        try:
            result = await asyncio.wait_for(getter(), timeout=timeout)
            return unwrap_variant(result, expected_type) if result is not None else default
        except (Exception, asyncio.TimeoutError):
            return default

    @staticmethod
    def _get_battery_icon(percentage: int | None) -> str:
        """Get appropriate battery icon based on level."""
        if percentage is None:
            return "mdi:battery-bluetooth-variant"

        # Floor to nearest 10 for icon selection
        level = max(0, min(100, int(percentage / 10) * 10))
        if level == 100:
            return "mdi:battery-bluetooth"
        if level == 0:
            return "mdi:battery-alert-bluetooth"
        return f"mdi:battery-bluetooth-{level}"

    async def _make_sensor_update(
        self,
        sensor_type: str,
        state_getter: Callable[[], Awaitable[Any]],
        offline_icon: str | None = None,
        icon_getter: Callable[[Any], str | None] | None = None,
    ) -> SensorUpdate:
        """Create a sensor update with availability checking.

        Args:
            sensor_type: The sensor type (e.g. "connected", "rssi")
            state_getter: Async function to get the state value
            offline_icon: Icon to use when device is offline
            icon_getter: Optional function to get icon based on state
        """
        # Check if device is available
        if not self._adapter or not self._adapter.is_available or not self.is_discovered:
            return SensorUpdate(unique_id=self.sensor_id(sensor_type), state=None, icon=offline_icon)

        try:
            state = await state_getter()
            icon = icon_getter(state) if icon_getter else offline_icon
            return SensorUpdate(unique_id=self.sensor_id(sensor_type), state=state, icon=icon)
        except Exception as e:
            logger.debug(f"Error getting {sensor_type}: {e}")
            raise

    async def _get_connected_state(self) -> bool:
        """Get connected state value."""
        result = await self._get_property_safe(self.interface.get_connected, bool, default=False)
        return result if result is not None else False

    async def _get_rssi_state(self) -> int | None:
        """Get RSSI state value."""
        return await self._get_property_safe(self.interface.get_rssi, int)

    async def _get_name_state(self) -> str:
        """Get name state value."""
        if not (alias := await self._get_property_safe(self.interface.get_alias, str)):
            result = await self._get_property_safe(self.interface.get_name, str, default=self.address)
            return result if result is not None else self.address
        return alias

    async def _get_battery_state(self) -> int | None:
        """Get battery state value."""
        if not self.battery_interface:
            return None
        # For mock testing, check if we have battery data in ObjectManager
        if not self.object_manager or not self.path:
            return None
        try:
            managed_objects = await self.object_manager.call_get_managed_objects()
            interfaces = managed_objects.get(self.path, {})
            battery_props = interfaces.get("org.bluez.Battery1", {})
            if "Percentage" in battery_props:
                return unwrap_variant(battery_props["Percentage"], int)
        except Exception:
            pass
        return None

    async def _get_connected_update(self) -> SensorUpdate:
        """Get connected sensor update."""
        return await self._make_sensor_update(
            "connected",
            self._get_connected_state,
            offline_icon="mdi:bluetooth-off",
            icon_getter=lambda state: "mdi:bluetooth-connect" if state else "mdi:bluetooth-off",
        )

    async def _get_rssi_update(self) -> SensorUpdate:
        """Get RSSI sensor update."""
        return await self._make_sensor_update("rssi", self._get_rssi_state)

    async def _get_name_update(self) -> SensorUpdate:
        """Get name sensor update."""
        return await self._make_sensor_update("name", self._get_name_state)

    async def _get_battery_update(self) -> SensorUpdate:
        """Get battery sensor update."""
        return await self._make_sensor_update(
            "battery",
            self._get_battery_state,
            offline_icon="mdi:battery-bluetooth-variant",
            icon_getter=lambda state: self._get_battery_icon(state)
            if state is not None
            else "mdi:battery-bluetooth-variant",
        )

    async def update_full(self, adapter: BluetoothAdapter | None = None) -> None:
        """Update all sensor states for this device."""
        self._adapter = adapter
        # Update all sensors
        await self._update_partial(["connected", "rssi", "battery", "name"])


class BluetoothModule(BaseModule):
    """Module for Bluetooth monitoring via BlueZ."""

    def __init__(self, system_bus: MessageBus, whitelisted_devices: list[str]):
        """Initialize Bluetooth module.

        Args:
            system_bus: System bus instance.
            whitelisted_devices: List of device MAC addresses to monitor (in format AA:BB:CC:DD:EE:FF).
        """
        self._system_bus = system_bus
        self._update_listener: UpdateListener | None = None
        self._adapter: BluetoothAdapter | None = None
        self._object_manager: Any = None  # ObjectManager interface

        # Create all devices upfront - they'll be "off" until discovered
        self._devices_by_address: dict[str, BluetoothDevice] = {
            mac.upper(): BluetoothDevice(
                address=mac.upper(),
                system_bus=system_bus,
                object_manager=None,  # Will be set in start()
            )
            for mac in (whitelisted_devices or [])
        }

    def _set_update_listener_on_all_devices(self, update_listener: UpdateListener | None) -> None:
        """Set update listener on all devices."""
        for device in self._devices_by_address.values():
            device.set_update_listener(update_listener)

    def _disconnect_all_device_handlers(self) -> None:
        """Disconnect property change handlers and clear DBus references for all devices."""
        for device in self._devices_by_address.values():
            device.stop_monitoring()

    def sensors(self) -> list[SensorRegistration]:
        """Return list of sensors this module provides."""
        sensors = [
            SensorRegistration(
                unique_id="bluetooth_enabled",
                type=SensorType.BINARY_SENSOR,
                name="Bluetooth",
                state=False,
                icon="mdi:bluetooth",
                device_class=DeviceClass.CONNECTIVITY,
            ),
        ]

        # Add sensors for each whitelisted device
        for device in self._devices_by_address.values():
            sensors.extend(device.sensors())

        return sensors

    async def start(self, update_listener: UpdateListener) -> None:
        """Start monitoring Bluetooth status."""
        assert self._update_listener is None, "Module already started"
        self._update_listener = update_listener
        logger.debug("Starting...")

        # Get ObjectManager interface
        introspect = await self._system_bus.introspect(BLUEZ_NAME, "/")
        proxy = self._system_bus.get_proxy_object(BLUEZ_NAME, "/", introspect)
        self._object_manager = proxy.get_interface("org.freedesktop.DBus.ObjectManager")

        # Set object_manager and start monitoring for all devices
        for device in self._devices_by_address.values():
            device.object_manager = self._object_manager
            device.set_update_listener(update_listener)
            await device.start_monitoring()

        # Subscribe to interface changes for adapter monitoring only
        self._object_manager.on_interfaces_added(self._handle_interfaces_added)
        self._object_manager.on_interfaces_removed(self._handle_interfaces_removed)

        # Get current objects and find adapter
        managed_objects = await self._object_manager.call_get_managed_objects()

        # Find first adapter
        for path, interfaces in managed_objects.items():
            if "org.bluez.Adapter1" not in interfaces:
                continue

            adapter_props = interfaces["org.bluez.Adapter1"]
            await self._create_adapter(path, adapter_props)
            break

        # Send initial state update
        await self._update()

    async def _create_adapter(self, path: str, adapter_props: dict[str, Any]) -> None:
        """Create and start monitoring a Bluetooth adapter."""
        address = unwrap_variant(adapter_props["Address"], str)
        powered_prop = adapter_props.get("Powered", False)
        powered = unwrap_variant(powered_prop, bool) if powered_prop else False

        self._adapter = BluetoothAdapter(
            path=path,
            address=address,
            system_bus=self._system_bus,
            on_state_change=self._update_adapter_state,
            object_manager=self._object_manager,
            powered=powered,
        )
        logger.info(f"{'Found' if powered else 'Bluetooth adapter appeared'}: {self._adapter.address} at {path}")
        await self._adapter.start_monitoring()

    async def _handle_interfaces_added(self, path: str, interfaces: dict[str, dict[str, Any]]) -> None:
        """Handle new interfaces being added - only care about adapter appearing."""
        # New adapter appeared
        if "org.bluez.Adapter1" in interfaces and not self._adapter:
            adapter_props = interfaces["org.bluez.Adapter1"]
            await self._create_adapter(path, adapter_props)
            # Update state when adapter appears
            await self._update()

    async def _handle_interfaces_removed(self, path: str, interfaces: list[str]) -> None:
        """Handle interfaces being removed - only care about adapter disappearing."""
        # Check if adapter fully disappeared
        if self._adapter and path == self._adapter.path and "org.bluez.Adapter1" in interfaces:
            logger.warning(f"Bluetooth adapter removed: {path}")
            self._adapter.stop_monitoring()
            self._adapter = None
            # Update state when adapter disappears
            await self._update()

    async def stop(self) -> None:
        """Stop monitoring and clean up resources."""
        assert self._update_listener is not None, "Module not started"
        self._update_listener = None
        # Clear update listener on all devices
        self._set_update_listener_on_all_devices(None)

        # Clean up devices
        self._disconnect_all_device_handlers()

        # Clear adapter
        if self._adapter:
            self._adapter.stop_monitoring()
            self._adapter = None

    async def _update(self) -> None:
        """Update all Bluetooth sensor states."""
        logger.debug("Updating Bluetooth state")

        # Update adapter state
        await self._update_adapter_state()

    async def _update_adapter_state(self) -> None:
        """Update adapter enabled/disabled state."""
        if self._update_listener is None:
            return

        # If no adapter interface, send unavailable state
        if not self._adapter or not self._adapter.interface:
            await self._update_listener(SensorUpdate(unique_id="bluetooth_enabled", state=None))
            return
        try:
            # Add timeout to prevent hanging on disconnected bus
            powered = await asyncio.wait_for(self._adapter.interface.get_powered(), timeout=2.0)
            update = SensorUpdate(
                unique_id="bluetooth_enabled",
                state=powered,
                icon="mdi:bluetooth" if powered else "mdi:bluetooth-off",
            )
            # Store adapter powered state for device updates
            self._adapter.powered = powered
        except (dbus_fast.errors.DBusError, asyncio.TimeoutError) as e:
            # Send unavailable state when adapter is unreachable
            logger.warning(f"Bluetooth adapter unavailable: {e}")
            update = SensorUpdate(unique_id="bluetooth_enabled", state=None)
            self._adapter.powered = False
        except Exception:
            # Log unexpected errors but still send unavailable state
            logger.exception("Unexpected error getting adapter state")
            update = SensorUpdate(unique_id="bluetooth_enabled", state=None)
            self._adapter.powered = False
        await self._update_listener(update)

        # Always update device states - they'll be marked unavailable if no adapter or not discovered
        for device in self._devices_by_address.values():
            device.set_adapter(self._adapter)
        await asyncio.gather(*[device.update_full(self._adapter) for device in self._devices_by_address.values()])

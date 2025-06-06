"""Bluetooth module using BlueZ DBus service."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

import dbus_fast.errors
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

BLUEZ_NAME = "org.bluez"
BLUEZ_ROOT = "/org/bluez"


class BluetoothModule(BaseModule):
    """Module for Bluetooth monitoring via BlueZ."""

    def __init__(self, system_bus: MessageBus, whitelisted_devices: list[str] | None = None):
        """Initialize Bluetooth module.

        Args:
            system_bus: System bus instance.
            whitelisted_devices: List of device MAC addresses to monitor (in format AA:BB:CC:DD:EE:FF).
        """
        self._system_bus = system_bus
        self._whitelisted_devices = [mac.upper() for mac in (whitelisted_devices or [])]
        self._update_listener: UpdateListener | None = None
        self._adapter_path: str | None = None
        self._adapter_iface: Any = None  # ProxyInterface from dbus-fast
        self._adapter_properties_iface: Any = None  # ProxyInterface from dbus-fast
        self._device_interfaces: dict[str, Any] = {}  # MAC -> Device interface
        self._device_properties_interfaces: dict[str, Any] = {}  # MAC -> Properties interface
        self._battery_interfaces: dict[str, Any] = {}  # MAC -> Battery interface
        self._adapter_powered: bool = False

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
        for mac in self._whitelisted_devices:
            device_name = f"bluetooth_device_{mac.replace(':', '_').lower()}"
            sensors.extend(
                [
                    SensorRegistration(
                        unique_id=f"{device_name}_connected",
                        type=SensorType.BINARY_SENSOR,
                        name=f"Bluetooth {mac}",
                        state=False,
                        icon="mdi:bluetooth-connect",
                        device_class=DeviceClass.CONNECTIVITY,
                    ),
                    SensorRegistration(
                        unique_id=f"{device_name}_rssi",
                        type=SensorType.SENSOR,
                        name=f"Bluetooth {mac} RSSI",
                        state=None,
                        icon="mdi:signal",
                        unit_of_measurement="dBm",
                        state_class=StateClass.MEASUREMENT,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    ),
                    SensorRegistration(
                        unique_id=f"{device_name}_battery",
                        type=SensorType.SENSOR,
                        name=f"Bluetooth {mac} Battery",
                        state=None,
                        icon="mdi:battery-bluetooth",
                        unit_of_measurement="%",
                        device_class=DeviceClass.BATTERY,
                        state_class=StateClass.MEASUREMENT,
                    ),
                    SensorRegistration(
                        unique_id=f"{device_name}_name",
                        type=SensorType.SENSOR,
                        name=f"Bluetooth {mac} Name",
                        state="Unknown",
                        icon="mdi:bluetooth",
                        entity_category=EntityCategory.DIAGNOSTIC,
                    ),
                ]
            )

        return sensors

    async def start(self, update_listener: UpdateListener) -> None:
        """Start monitoring Bluetooth status."""
        assert self._update_listener is None, "Module already started"
        self._update_listener = update_listener
        logger.debug("Starting...")

        try:
            # Get ObjectManager interface to monitor for adapters
            introspect = await self._system_bus.introspect(BLUEZ_NAME, "/")
            proxy = self._system_bus.get_proxy_object(BLUEZ_NAME, "/", introspect)
            object_manager = proxy.get_interface("org.freedesktop.DBus.ObjectManager")

            # Subscribe to interface changes for adapter monitoring
            object_manager.on_interfaces_added(self._handle_interfaces_added)  # type: ignore[attr-defined]
            object_manager.on_interfaces_removed(self._handle_interfaces_removed)  # type: ignore[attr-defined]

            # Get current objects to find adapter
            managed_objects = await object_manager.call_get_managed_objects()  # type: ignore[attr-defined]

            # Find first adapter
            for path, interfaces in managed_objects.items():
                if "org.bluez.Adapter1" in interfaces:
                    self._adapter_path = path
                    logger.info(f"Found Bluetooth adapter: {path}")
                    break

            if self._adapter_path:
                await self._setup_adapter()
            else:
                logger.warning("No Bluetooth adapter found - will be notified when one appears")
                # Send initial unavailable states
                await self._update()

        except dbus_fast.errors.DBusError as e:
            logger.error(f"Failed to initialize Bluetooth module: {e}")
            # Still set up ObjectManager monitoring even if BlueZ isn't ready
            try:
                introspect = await self._system_bus.introspect("org.freedesktop.DBus", "/")
                proxy = self._system_bus.get_proxy_object("org.freedesktop.DBus", "/", introspect)
                # Monitor for BlueZ service appearing
                logger.info("BlueZ not available, monitoring for service availability")
            except Exception:
                logger.exception("Failed to set up DBus monitoring")
                raise

    async def _setup_adapter(self) -> None:
        """Set up adapter interfaces and monitoring."""
        if not self._adapter_path:
            return

        try:
            # Get adapter interfaces
            adapter_introspect = await self._system_bus.introspect(BLUEZ_NAME, self._adapter_path)
            adapter_proxy = self._system_bus.get_proxy_object(BLUEZ_NAME, self._adapter_path, adapter_introspect)
            self._adapter_iface = adapter_proxy.get_interface("org.bluez.Adapter1")
            self._adapter_properties_iface = adapter_proxy.get_interface("org.freedesktop.DBus.Properties")

            # Subscribe to adapter property changes
            self._adapter_properties_iface.on_properties_changed(self._handle_adapter_properties_changed)  # type: ignore[attr-defined]

            # Discover existing devices
            await self._discover_devices()

            # Update all states
            await self._update()

        except dbus_fast.errors.DBusError as e:
            logger.error(f"Failed to setup adapter {self._adapter_path}: {e}")
            self._adapter_path = None
            self._adapter_iface = None
            self._adapter_properties_iface = None
            # Send unavailable states
            await self._update()

    async def _handle_interfaces_added(self, path: str, interfaces: dict[str, dict[str, Any]]) -> None:
        """Handle new interfaces being added (e.g., adapter appearing)."""
        if "org.bluez.Adapter1" in interfaces and not self._adapter_path:
            logger.info(f"Bluetooth adapter appeared: {path}")
            self._adapter_path = path
            await self._setup_adapter()
        elif self._adapter_path and path.startswith(self._adapter_path + "/dev_"):
            # New device appeared under our adapter
            mac = path.split("/dev_")[1].replace("_", ":").upper()
            if mac not in self._whitelisted_devices:
                return
            logger.debug(f"Whitelisted device appeared: {mac}")
            await self._setup_device_monitoring(path, mac)
            await self._update_device_state(mac)

    async def _handle_interfaces_removed(self, path: str, interfaces: list[str]) -> None:
        """Handle interfaces being removed (e.g., adapter disappearing)."""
        if path != self._adapter_path or "org.bluez.Adapter1" not in interfaces:
            return

        logger.warning(f"Bluetooth adapter removed: {path}")
        # Clean up adapter
        if self._adapter_properties_iface:
            self._adapter_properties_iface.off_properties_changed(self._handle_adapter_properties_changed)
        self._adapter_path = None
        self._adapter_iface = None
        self._adapter_properties_iface = None

        # Clean up all devices - use set intersection
        for mac in self._device_interfaces.keys() & self._device_properties_interfaces.keys():
            self._device_properties_interfaces[mac].off_properties_changed(self._handle_device_properties_changed)

        self._device_interfaces.clear()
        self._device_properties_interfaces.clear()
        self._battery_interfaces.clear()
        # Send unavailable states
        await self._update()

    async def _discover_devices(self) -> None:
        """Discover and set up monitoring for whitelisted devices."""
        if not self._adapter_path:
            return

        # List all devices under the adapter
        adapter_introspect = await self._system_bus.introspect(BLUEZ_NAME, self._adapter_path)

        for node in adapter_introspect.nodes:
            if node.name.startswith("dev_"):
                # Extract MAC address from device path (dev_AA_BB_CC_DD_EE_FF -> AA:BB:CC:DD:EE:FF)
                mac = node.name[4:].replace("_", ":").upper()

                if mac in self._whitelisted_devices:
                    device_path = f"{self._adapter_path}/{node.name}"
                    await self._setup_device_monitoring(device_path, mac)

    async def _setup_device_monitoring(self, device_path: str, mac: str) -> None:
        """Set up monitoring for a specific device."""
        try:
            device_introspect = await self._system_bus.introspect(BLUEZ_NAME, device_path)
            device_proxy = self._system_bus.get_proxy_object(BLUEZ_NAME, device_path, device_introspect)

            # Get device interface
            self._device_interfaces[mac] = device_proxy.get_interface("org.bluez.Device1")
            self._device_properties_interfaces[mac] = device_proxy.get_interface("org.freedesktop.DBus.Properties")

            # Subscribe to device property changes
            self._device_properties_interfaces[mac].on_properties_changed(
                lambda iface, changed, invalidated: asyncio.create_task(
                    self._handle_device_properties_changed(mac, iface, changed, invalidated)
                )
            )

            # Check if device has battery interface
            if "org.bluez.Battery1" in [iface.name for iface in device_introspect.interfaces]:
                self._battery_interfaces[mac] = device_proxy.get_interface("org.bluez.Battery1")

            logger.debug(f"Set up monitoring for device {mac}")

        except dbus_fast.errors.DBusError:
            logger.exception(f"Failed to set up monitoring for device {mac}")

    async def _handle_adapter_properties_changed(
        self, _interface: str, changed: dict[str, Any], _invalidated: list[str]
    ) -> None:
        """Handle properties changed signal from adapter."""
        # Only update if Powered property changed
        if "Powered" not in changed:
            return

        await self._update_adapter_state()
        # Also update device states when adapter power changes
        for mac in self._whitelisted_devices:
            await self._update_device_state(mac)

    async def _handle_device_properties_changed(
        self, mac: str, _interface: str, _changed, _invalidated: list[str]
    ) -> None:
        """Handle properties changed signal from device."""
        await self._update_device_state(mac)

    async def stop(self) -> None:
        """Stop monitoring and clean up resources."""
        assert self._update_listener is not None, "Module not started"
        self._update_listener = None

        if self._adapter_properties_iface:
            self._adapter_properties_iface.off_properties_changed(self._handle_adapter_properties_changed)

        for props_iface in self._device_properties_interfaces.values():
            props_iface.off_properties_changed(self._handle_device_properties_changed)

        self._adapter_properties_iface = None
        self._adapter_iface = None
        self._device_interfaces.clear()
        self._device_properties_interfaces.clear()
        self._battery_interfaces.clear()

    @asynccontextmanager
    async def context(self, update_listener) -> Any:
        """Provide an async context manager for the Bluetooth module."""
        try:
            await self.start(update_listener)
            yield self
        finally:
            await self.stop()

    async def _update(self) -> None:
        """Update all Bluetooth sensor states."""
        logger.debug("Updating Bluetooth state")

        # Update adapter state
        await self._update_adapter_state()

        # Always update device states - they'll be marked unavailable if no adapter
        for mac in self._whitelisted_devices:
            await self._update_device_state(mac)

    async def _update_adapter_state(self) -> None:
        """Update adapter enabled/disabled state."""
        if self._update_listener is None:
            return

        # If no adapter interface, send unavailable state
        if not self._adapter_iface:
            await self._update_listener(SensorUpdate(unique_id="bluetooth_enabled", state=None))
            return
        try:
            # Add timeout to prevent hanging on disconnected bus
            powered = await asyncio.wait_for(self._adapter_iface.get_powered(), timeout=2.0)
            update = SensorUpdate(
                unique_id="bluetooth_enabled",
                state=powered,
                icon="mdi:bluetooth" if powered else "mdi:bluetooth-off",
            )
            # Store adapter powered state for device updates
            self._adapter_powered = powered
        except (dbus_fast.errors.DBusError, asyncio.TimeoutError) as e:
            # Send unavailable state when adapter is unreachable
            logger.warning(f"Bluetooth adapter unavailable: {e}")
            update = SensorUpdate(unique_id="bluetooth_enabled", state=None)
            self._adapter_powered = False
        except Exception:
            # Log unexpected errors but still send unavailable state
            logger.exception("Unexpected error getting adapter state")
            update = SensorUpdate(unique_id="bluetooth_enabled", state=None)
            self._adapter_powered = False
        await self._update_listener(update)

    async def _update_device_state(self, mac: str) -> None:
        """Update state for a specific device."""
        device_name = f"bluetooth_device_{mac.replace(':', '_').lower()}"

        # Default states (device not found or error)
        connected = False
        rssi = None
        battery = None
        name = "Unknown"

        # If no adapter or adapter is powered off, everything is unavailable
        if not self._adapter_path or not self._adapter_powered:
            connected = None
            name = None
        elif device_iface := self._device_interfaces.get(mac):
            try:
                # Get device properties with timeouts
                try:
                    connected = await asyncio.wait_for(device_iface.get_connected(), timeout=2.0)
                except (Exception, asyncio.TimeoutError):
                    connected = False

                # RSSI is only available when device is discovered or connected
                try:
                    rssi = await asyncio.wait_for(device_iface.get_rssi(), timeout=1.0)
                except (Exception, asyncio.TimeoutError):
                    rssi = None

                # Get device name
                try:
                    alias = await asyncio.wait_for(device_iface.get_alias(), timeout=1.0)
                    name = alias
                except (Exception, asyncio.TimeoutError):
                    try:
                        name = await asyncio.wait_for(device_iface.get_name(), timeout=1.0)
                    except (Exception, asyncio.TimeoutError):
                        name = mac

                # Get battery level if available
                if mac in self._battery_interfaces:
                    try:
                        battery = await asyncio.wait_for(self._battery_interfaces[mac].get_percentage(), timeout=1.0)
                    except (Exception, asyncio.TimeoutError):
                        battery = None
            except (dbus_fast.errors.DBusError, asyncio.TimeoutError):
                logger.exception(f"Failed to get device state for {mac}")

        # Send updates
        updates = {
            f"{device_name}_connected": (
                connected,
                "mdi:bluetooth-connect" if connected else "mdi:bluetooth-off",
            ),
            f"{device_name}_rssi": (rssi, None),
            f"{device_name}_battery": (
                battery,
                self._get_battery_icon(battery) if battery is not None else "mdi:battery-bluetooth-variant",
            ),
            f"{device_name}_name": (name, None),
        }

        if self._update_listener is None:
            return
        await asyncio.gather(
            *[
                self._update_listener(SensorUpdate(unique_id=unique_id, state=state, icon=icon if icon else None))
                for unique_id, (state, icon) in updates.items()
            ]
        )

    @classmethod
    def _get_battery_icon(cls, percentage: int | None) -> str:
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

# mypy: ignore-errors
# ruff: noqa: F821
"""Mock BlueZ service for testing Bluetooth module.

This file uses dbus-fast string literal type annotations (like "s", "b", "n")
that are required for DBus interface generation. These appear as undefined
names to static type checkers, so we disable mypy checking for this file.
"""

import asyncio
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from dbus_fast import Message, MessageType, Variant
from dbus_fast.aio import MessageBus
from dbus_fast.service import PropertyAccess, ServiceInterface, dbus_property, method

logger = logging.getLogger(__name__)

BLUEZ_SERVICE = "org.bluez"
BLUEZ_PATH = "/org/bluez"
ADAPTER_PATH = "/org/bluez/hci0"


class BlueZDevice(ServiceInterface):
    """Mock BlueZ device implementation.

    This can implement multiple interfaces (Device1 and optionally Battery1).
    """

    def __init__(self, address: str, has_battery: bool = False):
        # We'll just use Device1 as the primary interface
        super().__init__("org.bluez.Device1")
        self._bus: MessageBus | None = None
        self._path: str = ""
        self._address = address
        self._name = f"Device {address}"
        self._alias = self._name
        self._connected = False
        self._paired = True
        self._bonded = True
        self._trusted = False
        self._blocked = False
        self._rssi: int | None = None
        self._battery_percentage: int | None = None
        self._has_battery = has_battery

    @dbus_property(access=PropertyAccess.READ)
    def Address(self) -> "s":  # type: ignore[misc] # noqa: N802
        return self._address

    @dbus_property(access=PropertyAccess.READ)
    def Name(self) -> "s":  # type: ignore[misc] # noqa: N802
        return self._name

    @dbus_property(access=PropertyAccess.READWRITE)
    def Alias(self) -> "s":  # type: ignore[misc] # noqa: N802
        return self._alias

    @Alias.setter  # type: ignore[misc]
    def Alias(self, value: "s") -> None:  # type: ignore[misc] # noqa: N802
        self._alias = value
        asyncio.create_task(self._emit_properties_changed({"Alias": Variant("s", value)}))

    @dbus_property(access=PropertyAccess.READ)
    def Connected(self) -> "b":  # type: ignore[misc] # noqa: N802
        return self._connected

    @dbus_property(access=PropertyAccess.READ)
    def Paired(self) -> "b":  # type: ignore[misc] # noqa: N802
        return self._paired

    @dbus_property(access=PropertyAccess.READ)
    def Bonded(self) -> "b":  # type: ignore[misc] # noqa: N802
        return self._bonded

    @dbus_property(access=PropertyAccess.READWRITE)
    def Trusted(self) -> "b":  # type: ignore[misc] # noqa: N802
        return self._trusted

    @Trusted.setter  # type: ignore[misc]
    def Trusted(self, value: "b") -> None:  # type: ignore[misc] # noqa: N802
        self._trusted = value

    @dbus_property(access=PropertyAccess.READWRITE)
    def Blocked(self) -> "b":  # type: ignore[misc] # noqa: N802
        return self._blocked

    @Blocked.setter  # type: ignore[misc]
    def Blocked(self, value: "b") -> None:  # type: ignore[misc] # noqa: N802
        self._blocked = value

    @dbus_property(access=PropertyAccess.READ)
    def RSSI(self) -> "n":  # type: ignore[misc] # noqa: N802
        # Note: In real BlueZ, RSSI property wouldn't exist if not available
        # For testing, we'll return a default value instead of raising
        return self._rssi if self._rssi is not None else -100

    @method()
    async def Connect(self) -> None:  # type: ignore[misc] # noqa: N802
        """Connect to the device."""
        self._connected = True
        await self._emit_properties_changed({"Connected": Variant("b", True)})

    @method()
    async def Disconnect(self) -> None:  # type: ignore[misc] # noqa: N802
        """Disconnect from the device."""
        self._connected = False
        await self._emit_properties_changed({"Connected": Variant("b", False)})

    async def update_state(
        self, connected: bool | None = None, rssi: int | None = None, name: str | None = None
    ) -> None:
        """Update device state and emit properties changed signal."""
        changed_props = {}

        if connected is not None and connected != self._connected:
            self._connected = connected
            changed_props["Connected"] = Variant("b", connected)

        if rssi is not None:
            old_rssi = self._rssi
            self._rssi = rssi
            # Only emit RSSI change if it was previously None or changed
            if old_rssi is None or old_rssi != rssi:
                changed_props["RSSI"] = Variant("n", rssi)

        if name is not None and name != self._name:
            self._name = name
            self._alias = name  # Update alias too
            changed_props["Name"] = Variant("s", name)
            changed_props["Alias"] = Variant("s", name)

        if changed_props:
            await self._emit_properties_changed(changed_props)

    async def _emit_properties_changed(self, changed_properties: dict[str, Variant]) -> None:
        """Emit PropertiesChanged signal."""
        if self._bus is not None:
            msg = Message(
                destination=None,  # Broadcast
                path=self._path,
                interface="org.freedesktop.DBus.Properties",
                member="PropertiesChanged",
                signature="sa{sv}as",
                body=[self.name, changed_properties, []],
                message_type=MessageType.SIGNAL,
            )
            await self._bus.send(msg)


class BlueZBattery(ServiceInterface):
    """Mock BlueZ battery interface."""

    def __init__(self):
        super().__init__("org.bluez.Battery1")
        self._percentage = 50

    @dbus_property(access=PropertyAccess.READ)
    def Percentage(self) -> "y":  # type: ignore[misc] # noqa: N802
        return self._percentage

    async def update_percentage(self, percentage: int) -> None:
        """Update battery percentage."""
        self._percentage = percentage
        # Note: In real BlueZ, battery changes are also notified via Device1 PropertiesChanged


class BlueZAdapter(ServiceInterface):
    """Mock BlueZ adapter implementation."""

    def __init__(self):
        super().__init__("org.bluez.Adapter1")
        self._bus: MessageBus | None = None
        self._path: str = ""
        self._powered = True
        self._discovering = False
        self._address = "00:11:22:33:44:55"
        self._name = "Mock Adapter"
        self._alias = self._name

    @dbus_property(access=PropertyAccess.READ)
    def Address(self) -> "s":  # type: ignore[misc] # noqa: N802
        return self._address

    @dbus_property(access=PropertyAccess.READ)
    def Name(self) -> "s":  # type: ignore[misc] # noqa: N802
        return self._name

    @dbus_property(access=PropertyAccess.READWRITE)
    def Alias(self) -> "s":  # type: ignore[misc] # noqa: N802
        return self._alias

    @Alias.setter  # type: ignore[misc]
    def Alias(self, value: "s") -> None:  # type: ignore[misc] # noqa: N802
        self._alias = value

    @dbus_property(access=PropertyAccess.READWRITE)
    def Powered(self) -> "b":  # type: ignore[misc] # noqa: N802
        return self._powered

    @Powered.setter  # type: ignore[misc]
    def Powered(self, value: "b") -> None:  # type: ignore[misc] # noqa: N802
        self._powered = value
        asyncio.create_task(self._emit_properties_changed({"Powered": Variant("b", value)}))

    @dbus_property(access=PropertyAccess.READ)
    def Discovering(self) -> "b":  # type: ignore[misc] # noqa: N802
        return self._discovering

    @method()
    async def StartDiscovery(self) -> None:  # type: ignore[misc] # noqa: N802
        """Start device discovery."""
        self._discovering = True
        await self._emit_properties_changed({"Discovering": Variant("b", True)})

    @method()
    async def StopDiscovery(self) -> None:  # type: ignore[misc] # noqa: N802
        """Stop device discovery."""
        self._discovering = False
        await self._emit_properties_changed({"Discovering": Variant("b", False)})

    async def _emit_properties_changed(self, changed_properties: dict[str, Variant]) -> None:
        """Emit PropertiesChanged signal."""
        if self._bus is not None:
            msg = Message(
                destination=None,  # Broadcast
                path=self._path,
                interface="org.freedesktop.DBus.Properties",
                member="PropertiesChanged",
                signature="sa{sv}as",
                body=[self.name, changed_properties, []],
                message_type=MessageType.SIGNAL,
            )
            await self._bus.send(msg)


class ObjectManager(ServiceInterface):
    """Mock DBus ObjectManager implementation."""

    def __init__(self):
        super().__init__("org.freedesktop.DBus.ObjectManager")
        self._objects: dict[str, dict[str, dict[str, Any]]] = {}
        self._bus: MessageBus | None = None

    def add_object(self, path: str, interfaces: dict[str, dict[str, Any]]) -> None:
        """Add an object to the manager."""
        self._objects[path] = interfaces
        if self._bus:
            asyncio.create_task(self._emit_interfaces_added(path, interfaces))

    def remove_object(self, path: str) -> None:
        """Remove an object from the manager."""
        if path not in self._objects:
            return
        interfaces = list(self._objects[path].keys())
        self._objects.pop(path)
        if self._bus:
            asyncio.create_task(self._emit_interfaces_removed(path, interfaces))

    @method()
    async def GetManagedObjects(self) -> "a{oa{sa{sv}}}":  # type: ignore[misc] # noqa: N802, F722
        """Return all managed objects."""
        return self._objects

    async def _emit_interfaces_added(self, path: str, interfaces: dict[str, dict[str, Any]]) -> None:
        """Emit InterfacesAdded signal."""
        if not self._bus:
            return
        await self._bus.send(
            Message(
                destination=None,
                path="/",
                interface="org.freedesktop.DBus.ObjectManager",
                member="InterfacesAdded",
                signature="oa{sa{sv}}",
                body=[path, interfaces],
                message_type=MessageType.SIGNAL,
            )
        )

    async def _emit_interfaces_removed(self, path: str, interfaces: list[str]) -> None:
        """Emit InterfacesRemoved signal."""
        if not self._bus:
            return
        await self._bus.send(
            Message(
                destination=None,
                path="/",
                interface="org.freedesktop.DBus.ObjectManager",
                member="InterfacesRemoved",
                signature="oas",
                body=[path, interfaces],
                message_type=MessageType.SIGNAL,
            )
        )


class MockBlueZDaemon:
    """Manages a mock BlueZ service on a private bus."""

    def __init__(self):
        self._temp_dir: tempfile.TemporaryDirectory | None = None
        self._dbus_process: subprocess.Popen | None = None
        self._bus_address: str | None = None
        self._bus: MessageBus | None = None
        self._adapter: BlueZAdapter | None = None
        self._devices: dict[str, BlueZDevice] = {}
        self._batteries: dict[str, BlueZBattery] = {}
        self._object_manager: ObjectManager | None = None

        # Create some default devices
        self._create_default_devices()

    def _create_default_devices(self) -> None:
        """Create default test devices."""
        # First device - with battery
        self._devices["AA:BB:CC:DD:EE:FF"] = BlueZDevice("AA:BB:CC:DD:EE:FF")
        self._batteries["AA:BB:CC:DD:EE:FF"] = BlueZBattery()

        # Second device - without battery
        self._devices["11:22:33:44:55:66"] = BlueZDevice("11:22:33:44:55:66")

    async def start(self) -> str:
        """Start the mock DBus daemon and BlueZ service."""
        # Create temporary directory for bus socket
        self._temp_dir = tempfile.TemporaryDirectory()
        socket_path = Path(self._temp_dir.name) / "bus"

        # Create DBus config
        config_path = Path(self._temp_dir.name) / "session.conf"
        config_content = f"""
<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
  <type>session</type>
  <listen>unix:path={socket_path}</listen>
  <policy context="default">
    <allow send_destination="*"/>
    <allow receive_sender="*"/>
    <allow own="*"/>
  </policy>
</busconfig>
"""
        config_path.write_text(config_content)

        # Start dbus-daemon
        self._dbus_process = subprocess.Popen(
            ["dbus-daemon", f"--config-file={config_path}", "--print-address"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Get bus address
        if self._dbus_process.stdout:
            self._bus_address = self._dbus_process.stdout.readline().decode().strip()

        if not self._bus_address:
            raise RuntimeError("Failed to start DBus daemon")

        # Connect to the bus
        self._bus = MessageBus(bus_address=self._bus_address)
        await self._bus.connect()

        # Create and export ObjectManager at root
        self._object_manager = ObjectManager()
        self._object_manager._bus = self._bus
        self._bus.export("/", self._object_manager)

        # Create and export adapter
        self._adapter = BlueZAdapter()
        self._adapter._bus = self._bus
        self._adapter._path = ADAPTER_PATH
        self._bus.export(ADAPTER_PATH, self._adapter)

        # Add adapter to ObjectManager
        adapter_interfaces = {
            "org.bluez.Adapter1": {
                "Address": Variant("s", self._adapter.Address),
                "Name": Variant("s", self._adapter.Name),
                "Alias": Variant("s", self._adapter.Alias),
                "Powered": Variant("b", self._adapter.Powered),
                "Discovering": Variant("b", self._adapter.Discovering),
            }
        }
        self._object_manager.add_object(ADAPTER_PATH, adapter_interfaces)

        # Export devices
        for address, device in self._devices.items():
            device_path = f"{ADAPTER_PATH}/dev_{address.replace(':', '_')}"
            device._bus = self._bus
            device._path = device_path
            self._bus.export(device_path, device)

            # Build device interfaces for ObjectManager
            device_interfaces = {
                "org.bluez.Device1": {
                    "Address": Variant("s", device.Address),
                    "Name": Variant("s", device.Name),
                    "Alias": Variant("s", device.Alias),
                    "Connected": Variant("b", device.Connected),
                    "Paired": Variant("b", device.Paired),
                    "Bonded": Variant("b", device.Bonded),
                    "Trusted": Variant("b", device.Trusted),
                    "Blocked": Variant("b", device.Blocked),
                    "RSSI": Variant("n", device.RSSI),
                }
            }

            # Export battery interface if available
            if address in self._batteries:
                self._bus.export(device_path, self._batteries[address])
                device_interfaces["org.bluez.Battery1"] = {
                    "Percentage": Variant("y", self._batteries[address].Percentage)
                }

            # Add device to ObjectManager
            self._object_manager.add_object(device_path, device_interfaces)

        # Request service name
        await self._bus.request_name(BLUEZ_SERVICE)

        logger.info(f"Mock BlueZ service started on {self._bus_address}")
        return self._bus_address

    async def stop(self) -> None:
        """Stop the mock service and clean up."""
        if self._bus:
            self._bus.disconnect()
            self._bus = None

        if self._dbus_process:
            self._dbus_process.terminate()
            self._dbus_process.wait(timeout=5)
            self._dbus_process = None

        if self._temp_dir:
            self._temp_dir.cleanup()
            self._temp_dir = None

    async def set_adapter_powered(self, powered: bool) -> None:
        """Set adapter powered state."""
        if self._adapter:
            self._adapter.Powered = powered

    async def set_device_connected(self, address: str, connected: bool, rssi: int | None = None) -> None:
        """Set device connection state."""
        if address in self._devices:
            await self._devices[address].update_state(connected=connected, rssi=rssi)

    async def add_adapter(self, path: str, address: str) -> None:
        """Add a new adapter dynamically."""
        if self._adapter:
            return  # Already have an adapter

        self._adapter = BlueZAdapter()
        self._adapter._bus = self._bus
        self._adapter._path = path
        self._adapter._address = address
        self._bus.export(path, self._adapter)

        # Add to ObjectManager
        adapter_interfaces = {
            "org.bluez.Adapter1": {
                "Address": Variant("s", self._adapter.Address),
                "Name": Variant("s", self._adapter.Name),
                "Alias": Variant("s", self._adapter.Alias),
                "Powered": Variant("b", self._adapter.Powered),
                "Discovering": Variant("b", self._adapter.Discovering),
            }
        }
        self._object_manager.add_object(path, adapter_interfaces)

    async def remove_adapter(self) -> None:
        """Remove the adapter."""
        if not self._adapter:
            return

        path = self._adapter._path
        self._bus.unexport(path)
        self._object_manager.remove_object(path)
        self._adapter = None

    async def add_device(
        self,
        adapter_path: str,
        address: str,
        alias: str | None = None,
        connected: bool = False,
        battery_percentage: int | None = None,
    ) -> str:
        """Add a new device dynamically."""
        device = BlueZDevice(address)
        if alias:
            device._alias = alias
            device._name = alias
        device._connected = connected

        device_path = f"{adapter_path}/dev_{address.replace(':', '_')}"
        device._bus = self._bus
        device._path = device_path
        self._bus.export(device_path, device)
        self._devices[address] = device

        # Build device interfaces
        device_interfaces = {
            "org.bluez.Device1": {
                "Address": Variant("s", device.Address),
                "Name": Variant("s", device.Name),
                "Alias": Variant("s", device.Alias),
                "Connected": Variant("b", device.Connected),
                "Paired": Variant("b", device.Paired),
                "Bonded": Variant("b", device.Bonded),
                "Trusted": Variant("b", device.Trusted),
                "Blocked": Variant("b", device.Blocked),
                "RSSI": Variant("n", device.RSSI),
            }
        }

        # Add battery if specified
        if battery_percentage is not None:
            battery = BlueZBattery()
            battery._percentage = battery_percentage
            self._batteries[address] = battery
            self._bus.export(device_path, battery)
            device_interfaces["org.bluez.Battery1"] = {"Percentage": Variant("y", battery.Percentage)}

        self._object_manager.add_object(device_path, device_interfaces)
        return device_path

    async def remove_device(self, device_path: str) -> None:
        """Remove a device."""
        # Find device by path
        address = None
        for addr, dev in self._devices.items():
            if dev._path == device_path:
                address = addr
                break

        if not address:
            return

        self._bus.unexport(device_path)
        self._object_manager.remove_object(device_path)
        del self._devices[address]
        self._batteries.pop(address, None)

    async def add_battery_to_device(self, device_path: str, percentage: int) -> None:
        """Add battery interface to existing device."""
        # Find device by path
        address = None
        for addr, dev in self._devices.items():
            if dev._path == device_path:
                address = addr
                break

        if not address or address in self._batteries:
            return

        battery = BlueZBattery()
        battery._percentage = percentage
        self._batteries[address] = battery
        self._bus.export(device_path, battery)

        # Emit InterfacesAdded for just the battery
        battery_interfaces = {"org.bluez.Battery1": {"Percentage": Variant("y", battery.Percentage)}}
        await self._object_manager._emit_interfaces_added(device_path, battery_interfaces)

    async def set_device_battery(self, address: str, percentage: int) -> None:
        """Set device battery level."""
        if address in self._batteries:
            await self._batteries[address].update_percentage(percentage)
            # Also emit device properties changed for battery
            if address in self._devices and self._devices[address]._bus:
                await self._devices[address]._bus.send(
                    Message(
                        destination=None,
                        path=self._devices[address]._path,
                        interface="org.freedesktop.DBus.Properties",
                        member="PropertiesChanged",
                        signature="sa{sv}as",
                        body=["org.bluez.Battery1", {"Percentage": Variant("y", percentage)}, []],
                        message_type=MessageType.SIGNAL,
                    )
                )

    async def set_device_name(self, address: str, name: str) -> None:
        """Set device name/alias."""
        if address in self._devices:
            await self._devices[address].update_state(name=name)

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()


async def main():
    """Run a simple test of the mock BlueZ service."""
    logging.basicConfig(level=logging.INFO)

    async with MockBlueZDaemon() as daemon:
        logger.info("Mock BlueZ daemon started")

        # Simulate device changes
        await asyncio.sleep(2)
        logger.info("Connecting first device")
        await daemon.set_device_connected("AA:BB:CC:DD:EE:FF", True, rssi=-65)

        await asyncio.sleep(2)
        logger.info("Setting battery level")
        await daemon.set_device_battery("AA:BB:CC:DD:EE:FF", 75)

        await asyncio.sleep(2)
        logger.info("Disabling adapter")
        await daemon.set_adapter_powered(False)

        await asyncio.sleep(2)
        logger.info("Stopping daemon")


if __name__ == "__main__":
    asyncio.run(main())

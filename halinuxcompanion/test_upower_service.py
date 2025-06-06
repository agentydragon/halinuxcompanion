# mypy: ignore-errors
"""Mock UPower service for testing battery module.

This file uses dbus-fast string literal type annotations (like "u", "d", "b")
that are required for DBus interface generation. These appear as undefined
names to static type checkers, so we disable mypy checking for this file.
"""

import asyncio
import logging
import subprocess
import tempfile
from pathlib import Path

from dbus_fast import Message, MessageType, Variant
from dbus_fast.aio import MessageBus
from dbus_fast.service import PropertyAccess, ServiceInterface, dbus_property, method

logger = logging.getLogger(__name__)


UPOWER_SERVICE = "org.freedesktop.UPower"
UPOWER_PATH = "/org/freedesktop/UPower"
DEVICE_PATH_PREFIX = "/org/freedesktop/UPower/devices"


class UPowerDevice(ServiceInterface):
    """Mock UPower device implementation."""

    def __init__(self, device_type: int = 2):  # 2 = Battery
        super().__init__("org.freedesktop.UPower.Device")
        self._type = device_type
        self._bus: MessageBus | None = None
        self._path: str = ""
        self._percentage = 50.0
        self._state = 2  # Discharging
        self._energy_rate = 10.0
        self._time_to_empty = 7200  # 2 hours
        self._time_to_full = 0
        self._is_present = True
        self._power_supply = True
        self._has_history = False
        self._has_statistics = False
        self._online = False
        self._energy = 25.0
        self._energy_empty = 0.0
        self._energy_full = 50.0
        self._energy_full_design = 50.0
        self._capacity = 100.0
        self._model = "Mock Battery"
        self._native_path = "/sys/devices/mock_battery"
        self._vendor = "Mock Vendor"
        self._serial = "12345"
        self._update_time = 0
        self._technology = 1  # Li-ion
        self._voltage = 12.0
        self._temperature = 25.0
        self._warning_level = 1  # None
        self._battery_level = 1  # None
        self._icon_name = "battery-good-symbolic"

    @dbus_property(access=PropertyAccess.READ)
    def Type(self) -> "u":  # type: ignore[misc] # noqa: N802
        return self._type

    @dbus_property(access=PropertyAccess.READ)
    def Percentage(self) -> "d":  # type: ignore[misc] # noqa: N802
        return self._percentage

    @dbus_property(access=PropertyAccess.READ)
    def State(self) -> "u":  # type: ignore[misc] # noqa: N802
        return self._state

    @dbus_property(access=PropertyAccess.READ)
    def EnergyRate(self) -> "d":  # type: ignore[misc] # noqa: N802
        return self._energy_rate

    @dbus_property(access=PropertyAccess.READ)
    def TimeToEmpty(self) -> "x":  # type: ignore[misc] # noqa: N802
        return self._time_to_empty

    @dbus_property(access=PropertyAccess.READ)
    def TimeToFull(self) -> "x":  # type: ignore[misc] # noqa: N802
        return self._time_to_full

    @dbus_property(access=PropertyAccess.READ)
    def IsPresent(self) -> "b":  # type: ignore[misc] # noqa: N802
        return self._is_present

    @dbus_property(access=PropertyAccess.READ)
    def PowerSupply(self) -> "b":  # type: ignore[misc] # noqa: N802
        return self._power_supply

    @dbus_property(access=PropertyAccess.READ)
    def HasHistory(self) -> "b":  # type: ignore[misc] # noqa: N802
        return self._has_history

    @dbus_property(access=PropertyAccess.READ)
    def HasStatistics(self) -> "b":  # type: ignore[misc] # noqa: N802
        return self._has_statistics

    @dbus_property(access=PropertyAccess.READ)
    def Online(self) -> "b":  # type: ignore[misc] # noqa: N802
        return self._online

    @dbus_property(access=PropertyAccess.READ)
    def Energy(self) -> "d":  # type: ignore[misc] # noqa: N802
        return self._energy

    @dbus_property(access=PropertyAccess.READ)
    def EnergyEmpty(self) -> "d":  # type: ignore[misc] # noqa: N802
        return self._energy_empty

    @dbus_property(access=PropertyAccess.READ)
    def EnergyFull(self) -> "d":  # type: ignore[misc] # noqa: N802
        return self._energy_full

    @dbus_property(access=PropertyAccess.READ)
    def EnergyFullDesign(self) -> "d":  # type: ignore[misc] # noqa: N802
        return self._energy_full_design

    @dbus_property(access=PropertyAccess.READ)
    def Capacity(self) -> "d":  # type: ignore[misc] # noqa: N802
        return self._capacity

    @dbus_property(access=PropertyAccess.READ)
    def Model(self) -> "s":  # type: ignore[misc] # noqa: N802
        return self._model

    @dbus_property(access=PropertyAccess.READ)
    def NativePath(self) -> "s":  # type: ignore[misc] # noqa: N802
        return self._native_path

    @dbus_property(access=PropertyAccess.READ)
    def Vendor(self) -> "s":  # type: ignore[misc] # noqa: N802
        return self._vendor

    @dbus_property(access=PropertyAccess.READ)
    def Serial(self) -> "s":  # type: ignore[misc] # noqa: N802
        return self._serial

    @dbus_property(access=PropertyAccess.READ)
    def UpdateTime(self) -> "t":  # type: ignore[misc] # noqa: N802
        return self._update_time

    @dbus_property(access=PropertyAccess.READ)
    def Technology(self) -> "u":  # type: ignore[misc] # noqa: N802
        return self._technology

    @dbus_property(access=PropertyAccess.READ)
    def Voltage(self) -> "d":  # type: ignore[misc] # noqa: N802
        return self._voltage

    @dbus_property(access=PropertyAccess.READ)
    def Temperature(self) -> "d":  # type: ignore[misc] # noqa: N802
        return self._temperature

    @dbus_property(access=PropertyAccess.READ)
    def WarningLevel(self) -> "u":  # type: ignore[misc] # noqa: N802
        return self._warning_level

    @dbus_property(access=PropertyAccess.READ)
    def BatteryLevel(self) -> "u":  # type: ignore[misc] # noqa: N802
        return self._battery_level

    @dbus_property(access=PropertyAccess.READ)
    def IconName(self) -> "s":  # type: ignore[misc] # noqa: N802
        return self._icon_name

    async def update_battery(self, percentage: float, state: int, energy_rate: float = 10.0) -> None:
        """Update battery state and emit properties changed signal."""
        old_percentage = self._percentage
        old_state = self._state
        old_energy_rate = self._energy_rate

        self._percentage = percentage
        self._state = state
        self._energy_rate = energy_rate

        # Update time estimates based on state
        if state == 1:  # Charging
            self._time_to_empty = 0
            self._time_to_full = int((100 - percentage) * 3600 / 20)  # Rough estimate
        elif state == 2:  # Discharging
            self._time_to_empty = int(percentage * 3600 / 20)  # Rough estimate
            self._time_to_full = 0
        else:
            self._time_to_empty = 0
            self._time_to_full = 0

        # Emit properties changed
        changed_props = {}
        if old_percentage != self._percentage:
            changed_props["Percentage"] = Variant("d", self._percentage)
        if old_state != self._state:
            changed_props["State"] = Variant("u", self._state)
        if old_energy_rate != self._energy_rate:
            changed_props["EnergyRate"] = Variant("d", self._energy_rate)
            changed_props["TimeToEmpty"] = Variant("x", self._time_to_empty)
            changed_props["TimeToFull"] = Variant("x", self._time_to_full)

        if changed_props:
            await self._emit_properties_changed(changed_props)

    async def _emit_properties_changed(self, changed_properties: dict[str, Variant]) -> None:
        """Emit PropertiesChanged signal."""
        # Get the bus from the interface
        if self._bus is not None:
            msg = Message(
                destination=None,  # Broadcast
                path=self._path,
                interface="org.freedesktop.DBus.Properties",
                member="PropertiesChanged",
                signature="sa{sv}as",
                body=[self.name, changed_properties, []],  # Interface name  # Invalidated properties
                message_type=MessageType.SIGNAL,
            )
            await self._bus.send(msg)


class UPowerService(ServiceInterface):
    """Mock UPower main service implementation."""

    def __init__(self):
        super().__init__(UPOWER_SERVICE)
        self._devices: dict[str, UPowerDevice] = {}
        self._display_device_path = f"{DEVICE_PATH_PREFIX}/DisplayDevice"

        # Create a battery device
        self._battery = UPowerDevice(device_type=2)
        self._devices[f"{DEVICE_PATH_PREFIX}/battery_BAT0"] = self._battery

        # Create display device (aggregate)
        self._display_device = UPowerDevice(device_type=2)
        self._devices[self._display_device_path] = self._display_device

    @method()
    async def EnumerateDevices(self) -> "ao":  # type: ignore[misc] # noqa: N802
        """Return list of device paths."""
        # Don't include DisplayDevice in enumeration
        return [path for path in self._devices if "DisplayDevice" not in path]

    @method()
    async def GetDisplayDevice(self) -> "o":  # type: ignore[misc] # noqa: N802
        """Return path to display device."""
        return self._display_device_path

    @dbus_property(access=PropertyAccess.READ)
    def DaemonVersion(self) -> "s":  # type: ignore[misc] # noqa: N802
        return "0.99.0-mock"

    @dbus_property(access=PropertyAccess.READ)
    def OnBattery(self) -> "b":  # type: ignore[misc] # noqa: N802
        return self._display_device._state == 2  # Discharging

    @dbus_property(access=PropertyAccess.READ)
    def LidIsClosed(self) -> "b":  # type: ignore[misc] # noqa: N802
        return False

    @dbus_property(access=PropertyAccess.READ)
    def LidIsPresent(self) -> "b":  # type: ignore[misc] # noqa: N802
        return True

    async def update_battery(self, percentage: float, state: int, energy_rate: float = 10.0) -> None:
        """Update battery state for all battery devices."""
        await self._battery.update_battery(percentage, state, energy_rate)
        await self._display_device.update_battery(percentage, state, energy_rate)


class MockUPowerDaemon:
    """Manages a mock UPower service on a private bus."""

    def __init__(self):
        self._temp_dir: tempfile.TemporaryDirectory | None = None
        self._dbus_process: subprocess.Popen | None = None
        self._bus_address: str | None = None
        self._bus: MessageBus | None = None
        self._service: UPowerService | None = None

    async def start(self) -> str:
        """Start the mock DBus daemon and UPower service."""
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

        # Create and export UPower service
        self._service = UPowerService()
        self._bus.export(UPOWER_PATH, self._service)

        # Export devices
        for path, device in self._service._devices.items():
            device._bus = self._bus
            device._path = path
            self._bus.export(path, device)

        # Request service name
        await self._bus.request_name(UPOWER_SERVICE)

        logger.info(f"Mock UPower service started on {self._bus_address}")
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

    async def update_battery(self, percentage: float, state: int, energy_rate: float = 10.0) -> None:
        """Update battery state."""
        if self._service:
            await self._service.update_battery(percentage, state, energy_rate)

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()


async def main():
    """Run a simple test of the mock UPower service."""
    logging.basicConfig(level=logging.INFO)

    async with MockUPowerDaemon() as daemon:
        logger.info("Mock UPower daemon started")

        # Simulate battery changes
        await asyncio.sleep(2)
        logger.info("Setting battery to 75% charging")
        await daemon.update_battery(75.0, 1)  # Charging

        await asyncio.sleep(2)
        logger.info("Setting battery to 90% discharging")
        await daemon.update_battery(90.0, 2)  # Discharging

        await asyncio.sleep(2)
        logger.info("Setting battery to 15% discharging")
        await daemon.update_battery(15.0, 2)  # Low battery

        await asyncio.sleep(2)
        logger.info("Stopping daemon")


if __name__ == "__main__":
    asyncio.run(main())

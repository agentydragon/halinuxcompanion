"""Bluetooth hardware class implementation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, TypeVar, overload

from dbus_next import BusType, Variant
from dbus_next.aio import MessageBus

from ..hardware_base import (
    DeviceClass,
    HardwareClass,
    HardwarePiece,
    HardwareSensor,
    PerPieceUpdateMixin,
    SensorType,
    StateClass,
)
from ..hardware_config import BluetoothConfig

logger = logging.getLogger(__name__)


@dataclass
class BluetoothData:
    """Bluetooth device data."""

    mac: str
    name: Optional[str]
    visible: bool
    connected: bool
    battery_percentage: Optional[int] = None  # percentage (0-100)
    # TODO: implement volume, playback state


T = TypeVar("T")


@overload
def expect_variant(v: Variant, py_type: type[T]) -> T: ...
@overload
def expect_variant(v: Variant, py_type: tuple[type[T], ...]) -> T: ...


# TODO: -> dbus utils
def expect_variant(v: Variant, py_type: type[T] | tuple[type[T], ...]) -> T:
    value = v.value
    if not isinstance(value, py_type):
        raise TypeError(f"Variant holds {type(value)} ≠ {py_type}")
    return value


class BluetoothPiece(HardwarePiece):
    """Represents a Bluetooth device."""

    def __init__(
        self,
        hardware_id: str,
        mac: str,
        battery_sensor: HardwareSensor,
        connected_sensor: HardwareSensor,
        visible_sensor: HardwareSensor,
    ):
        super().__init__(hardware_id)
        self.mac = mac
        self.name = None  # Will be discovered through Bluetooth.
        self.battery_sensor = battery_sensor
        self.connected_sensor = connected_sensor
        self.visible_sensor = visible_sensor  # TOOD: daaclass

    def _sensor_attributes(self) -> Dict[str, str]:
        """Return attributes for sensors."""
        attributes = {"mac": self.mac}
        if self.name:
            attributes["name"] = self.name
        return attributes

    async def update(self) -> None:
        """Update all sensors for this Bluetooth device."""
        for sensor in self.get_sensors():
            sensor.attributes = self._sensor_attributes()

        data = await self._fetch_sensor_data()
        for sensor, value in [  # type: ignore[assignment]
            (self.visible_sensor, data.visible),
            (self.connected_sensor, data.connected),
            (self.battery_sensor, data.battery_percentage),
        ]:
            sensor.state = value if data else None

    def get_sensors(self) -> List[HardwareSensor]:
        return [self.battery_sensor, self.connected_sensor, self.visible_sensor]

    async def _fetch_sensor_data(self) -> BluetoothData:
        """Fetch fresh sensor data for this Bluetooth device."""
        # Get device info via D-Bus
        bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        path, interfaces = await self._find_device(bus)
        if not path or not interfaces:
            return BluetoothData(
                visible=False,
                connected=False,
                name=self.name,
                mac=self.mac,
            )
        # Get device properties
        device_props = interfaces.get("org.bluez.Device1", {})

        # Update device name if available (using walrus operator)
        if name_prop := (device_props.get("Name") or device_props.get("Alias")):
            if name_prop.value != self.name:
                logger.info(
                    f"Updating device name for {self.mac} from {self.name} to '{name_prop.value}'"
                )
            self.name = name_prop.value

        # Connection status
        if not (connected := device_props.get("Connected")):
            logger.warning(f"Device {self.mac} does not have 'Connected' property")
            connected_bool = False
        else:
            connected_bool = connected.value
            assert isinstance(connected_bool, bool), (
                "Connected property must be a boolean"
            )

        battery_percentage = await self._read_battery(bus, path, interfaces)

        return BluetoothData(
            visible=True,
            connected=connected_bool,
            name=self.name,
            mac=self.mac,
            battery_percentage=battery_percentage,
        )

    async def _find_device(
        self, bus: MessageBus
    ) -> Tuple[Optional[str], Optional[Dict]]:
        """Find device by MAC address. Returns (path, interfaces) or (None, None)."""
        root = await bus.introspect("org.bluez", "/")
        om = bus.get_proxy_object("org.bluez", "/", root)
        mgr = om.get_interface("org.freedesktop.DBus.ObjectManager")

        # Bluez keys:
        #   /org/bluez
        #   /org/bluez/hci0
        #   /org/bluez/hci0/dev_A8_F5_E1_77_2C_59  <- device path
        # TODO: do this with direct query at the right path instead of this scanning
        # but robustly to bluetooth device name
        objs = await mgr.call_get_managed_objects()

        for path, ifaces in objs.items():
            if (
                (dev := ifaces.get("org.bluez.Device1"))
                and (addr := dev.get("Address"))
                and expect_variant(addr.value, str).upper() == self.mac.upper()
            ):
                return path, ifaces

        return None, None

    async def _read_battery(
        self, bus: MessageBus, path: str, interfaces: Dict
    ) -> Optional[int]:
        """Read battery level using the working pattern."""
        # Prefer the dedicated Battery1 interface if present
        if "org.bluez.Battery1" in interfaces:
            node = await bus.introspect("org.bluez", path)
            batt = bus.get_proxy_object("org.bluez", path, node).get_interface(
                "org.bluez.Battery1"
            )
            pct = await batt.get_percentage()
            logger.info(
                f"Battery level for {self.mac} is {pct}% (from org.bluez.Battery1)"
            )
            return pct

        # Fallback to BatteryPercentage property on Device1
        if (
            battery_pct := interfaces["org.bluez.Device1"].get("BatteryPercentage")
        ) is not None:
            return expect_variant(battery_pct, int)  # TODO: test this pah
        return None


class BluetoothHardwareClass(PerPieceUpdateMixin, HardwareClass):
    """Bluetooth hardware class."""

    config_field = "bluetooth"

    def __init__(self, config: BluetoothConfig):
        super().__init__(config)
        self.config = config
        self._hardware_pieces = []

        for device_mac in self.config.devices:
            # Create hardware ID from MAC address
            hardware_id = device_mac.replace(":", "")

            # Create piece for this device (even if not currently visible)
            piece = BluetoothPiece(
                hardware_id,
                device_mac,
                battery_sensor=HardwareSensor(
                    unique_id=f"bluetooth:{hardware_id}:battery_level",
                    name="Battery Level",
                    unit="%",
                    device_class=DeviceClass.BATTERY,
                    state_class=StateClass.MEASUREMENT,
                    icon="mdi:battery-bluetooth",
                ),
                connected_sensor=HardwareSensor(
                    unique_id=f"bluetooth:{hardware_id}:connected",
                    type=SensorType.BINARY_SENSOR,
                    name="Connected",
                    device_class="connectivity",  # <--
                    icon="mdi:bluetooth-connect",
                ),
                visible_sensor=HardwareSensor(
                    unique_id=f"bluetooth:{hardware_id}:visible",
                    type=SensorType.BINARY_SENSOR,
                    name="Visible",
                    icon="mdi:bluetooth-audio",
                ),
            )
            self._hardware_pieces.append(piece)

    async def discover_sensors(self) -> List[HardwareSensor]:
        """Create sensors for all configured Bluetooth devices."""
        if not self.config.enabled:
            return []

        # Create pieces for ALL configured devices, not just visible ones
        all_sensors = []
        for piece in self._hardware_pieces:
            all_sensors.extend(piece.get_sensors())
        return all_sensors

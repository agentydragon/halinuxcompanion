"""Bluetooth module implementation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TypeVar, overload

from dbus_next import BusType, Variant
from dbus_next.aio import MessageBus

from ...module_base import DeviceClass, Module, ModulePiece, PerPieceUpdateMixin, Sensor, SensorType, StateClass
from ...module_config import BluetoothConfig

logger = logging.getLogger(__name__)


@dataclass
class BluetoothData:
    """Bluetooth device data."""

    name: str | None
    visible: bool
    connected: bool
    battery_percentage: int | None = None  # percentage (0-100)
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
    return value  # type: ignore[no-any-return]


class BluetoothPiece(ModulePiece):
    """Represents a Bluetooth device."""

    def __init__(self, mac: str):
        super().__init__(mac)
        self.mac = mac

        def _sensor(sensor_id, **kwargs):
            # name will be set later
            return Sensor(unique_id=f"bluetooth:{mac}:{sensor_id}", **kwargs)

        self.battery_sensor = _sensor(
            "battery_level",
            unit_of_measurement="%",
            device_class=DeviceClass.BATTERY,
            state_class=StateClass.MEASUREMENT,
            icon="mdi:battery-bluetooth",
        )
        self.connected_sensor = _sensor(
            "connected",
            type=SensorType.BINARY_SENSOR,
            device_class=DeviceClass.CONNECTIVITY,
            icon="mdi:bluetooth-connect",
            state_class=None,  # Binary sensors don't have state_class
        )
        self.visible_sensor = _sensor(
            "visible",
            type=SensorType.BINARY_SENSOR,
            icon="mdi:bluetooth-audio",
            state_class=None,  # Binary sensors don't have state_class
        )

        self.name: str | None = None  # last known name

    def _apply_update(self, data: BluetoothData) -> None:
        if data.name and data.name != self.name:
            # Only update if name set and changed
            logger.info(f"Updating name for {self.mac} from {self.name} to '{data.name}'")
            self.name = data.name

        if not data.name and self.name:
            logger.debug(f"Name of {self.mac} lost, using last seen name '{self.name}'")

        for sensor, subname, value in [
            (self.visible_sensor, "Visible", data.visible),
            (self.connected_sensor, "Connected", data.connected),
            (self.battery_sensor, "Battery", data.battery_percentage),
        ]:
            sensor.attributes = {"mac": self.mac, "name": self.name}
            sensor.name = f"{self.name or self.mac} {subname}"
            sensor.state = value if data else None

    async def update(self) -> None:
        """Update all sensors for this Bluetooth device."""
        data = await self._fetch_sensor_data()
        self._apply_update(data)

    def get_sensors(self) -> list[Sensor]:
        return [self.battery_sensor, self.connected_sensor, self.visible_sensor]

    async def _fetch_sensor_data(self) -> BluetoothData:
        """Fetch fresh sensor data for this Bluetooth device."""
        # Get device info via D-Bus
        bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        # TODO: dedupe, use dbus.py
        node = await bus.introspect("org.bluez", "/")
        proxy = bus.get_proxy_object("org.bluez", "/", node)
        objs = await proxy.get_interface("org.freedesktop.DBus.ObjectManager").call_get_managed_objects()
        # Bluez keys:
        #   /org/bluez
        #   /org/bluez/hci0
        #   /org/bluez/hci0/dev_A8_F5_E1_77_2C_59  <- device path
        # TODO: do this with direct query at the right path instead of this scanning
        # but robustly to bluetooth device name
        for ifaces in objs.values():
            if (
                (dev := ifaces.get("org.bluez.Device1"))
                and (addr := dev.get("Address"))
                and expect_variant(addr, str).upper() == self.mac.upper()
            ):
                break
        else:
            return BluetoothData(visible=False, connected=False, name=None)

        if pct_variant := ifaces.get("org.bluez.Battery1", {}).get("Percentage"):
            pct = expect_variant(pct_variant, (int, type(None)))
            logger.info(f"Battery level for {self.mac} is {pct}% (from org.bluez.Battery1)")
        else:
            pct = None

        return BluetoothData(
            visible=True,
            connected=expect_variant(dev["Connected"], bool),
            name=expect_variant((dev.get("Name") or dev.get("Alias")), (str, type(None))),
            battery_percentage=pct,
        )


class BluetoothModule(PerPieceUpdateMixin, Module):
    """Bluetooth module."""

    def __init__(self, config: BluetoothConfig):
        super().__init__(config)
        self.config = config
        self._module_pieces = [BluetoothPiece(mac) for mac in self.config.devices]

    async def discover_sensors(self) -> list[Sensor]:
        """Create sensors for all configured Bluetooth devices."""
        if not self.config.enabled:
            return []

        # Create pieces for ALL configured devices, not just visible ones
        all_sensors = []
        for piece in self._module_pieces:
            all_sensors.extend(piece.get_sensors())
        return all_sensors

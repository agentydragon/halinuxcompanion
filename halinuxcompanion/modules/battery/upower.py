"""Battery data provider using UPower via D-Bus."""

import logging
from typing import Any

from dbus_fast import BusType, DBusError, Variant
from dbus_fast.aio import MessageBus

from .provider import BatteryData, BatteryDataProvider

logger = logging.getLogger(__name__)

# D-Bus constants
UPOWER_BUS = "org.freedesktop.UPower"
UPOWER_OBJECT_PATH = "/org/freedesktop/UPower"
UPOWER_INTERFACE = "org.freedesktop.UPower"
UPOWER_DEVICE_INTERFACE = "org.freedesktop.UPower.Device"
DBUS_PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"

# UPower state mappings
UPOWER_STATE_MAPPING = {
    1: "Charging",
    2: "Discharging",
    3: "Full",
    4: "Full",  # "Fully charged"
}


class UPowerBatteryProvider(BatteryDataProvider):
    """Battery data provider using UPower via D-Bus."""

    def __init__(self) -> None:
        self._dbus: MessageBus | None = None
        self._proxies: dict[str, Any] = {}  # Cache all proxies

    async def _ensure_dbus(self):
        """Ensure D-Bus connection is established."""
        if self._dbus is None:
            self._dbus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        return self._dbus

    async def _get_proxy(self, path: str):
        """Get cached proxy or create new one."""
        if path not in self._proxies:
            logger.info(f"Looking for proxy for {path}")
            dbus = await self._ensure_dbus()
            introspection = await dbus.introspect(UPOWER_BUS, path)
            self._proxies[path] = dbus.get_proxy_object(UPOWER_BUS, path, introspection)
        return self._proxies[path]

    async def discover_batteries(self) -> list[str]:
        """Discover available batteries via UPower."""
        try:
            upower = (await self._get_proxy(UPOWER_OBJECT_PATH)).get_interface(UPOWER_INTERFACE)
            devices = await upower.call_enumerate_devices()
        except DBusError:
            logger.exception("DBus error discovering batteries via UPower")
            return []
        return [path for path in devices if "battery_" in path or "BAT" in path]

    async def get_battery_data(self, battery_id: str) -> BatteryData | None:
        """Get battery data from UPower."""
        try:
            properties = (await self._get_proxy(battery_id)).get_interface(DBUS_PROPERTIES_INTERFACE)
            all_props = await properties.call_get_all(UPOWER_DEVICE_INTERFACE)
        except DBusError:
            logger.exception(f"DBus error getting battery data for {battery_id}")
            return None

        # Helper to extract value from Variant
        def get_value(key: str, default=None):
            variant = all_props.get(key)
            if isinstance(variant, Variant):
                return variant.value
            return default

        # Extract state
        upower_state = get_value("State", 0)
        state = UPOWER_STATE_MAPPING.get(upower_state, "Unknown")

        # Extract temperature and convert from Kelvin if present
        temp_kelvin = get_value("Temperature")

        # Get energy rate
        energy_rate = get_value("EnergyRate")

        # Extract battery data
        return BatteryData(
            battery_id=battery_id,
            percent=get_value("Percentage", 0),
            plugged=get_value("PowerSupply", False),
            state=state,
            time_to_empty=get_value("TimeToEmpty"),
            time_to_full=get_value("TimeToFull"),
            charge_rate=energy_rate if upower_state != 2 else None,
            discharge_rate=energy_rate if upower_state == 2 else None,
            energy=get_value("Energy"),
            energy_full=get_value("EnergyFull"),
            energy_full_design=get_value("EnergyFullDesign"),
            capacity=get_value("Capacity"),
            charge_cycles=get_value("ChargeCycles") if get_value("ChargeCycles", 0) > 0 else None,
            voltage=get_value("Voltage"),
            temperature=(temp_kelvin - 273.15 if temp_kelvin else None),
            # NOTE: not reporting: Technology, Model, Vendor, Serial, WarningLevel
        )

"""Battery data provider using UPower via D-Bus."""

import logging
from typing import Any, Dict, List, Optional

from dbus_fast import BusType, DBusError, Variant
from dbus_fast.aio import MessageBus

from .battery_provider import BatteryData, BatteryDataProvider

logger = logging.getLogger(__name__)

# D-Bus constants
UPOWER_BUS_NAME = "org.freedesktop.UPower"
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

    def __init__(self):
        self._dbus = None
        self._proxies: Dict[str, Any] = {}  # Cache all proxies

    async def _ensure_dbus(self):
        """Ensure D-Bus connection is established."""
        if self._dbus is None:
            self._dbus = await MessageBus(bus_type=BusType.SYSTEM).connect()

    async def _get_proxy(self, object_path: str):
        """Get cached proxy or create new one."""
        if object_path not in self._proxies:
            await self._ensure_dbus()
            introspection = await self._dbus.introspect(UPOWER_BUS_NAME, object_path)
            self._proxies[object_path] = self._dbus.get_proxy_object(UPOWER_BUS_NAME, object_path, introspection)
        return self._proxies[object_path]

    async def discover_batteries(self) -> List[str]:
        """Discover available batteries via UPower."""
        try:
            proxy = await self._get_proxy(UPOWER_OBJECT_PATH)
            upower = proxy.get_interface(UPOWER_INTERFACE)
            devices = await upower.call_enumerate_devices()
        except DBusError:
            logger.error("DBus error discovering batteries via UPower", exc_info=True)
            return []

        batteries = []
        for device_path in devices:
            if "/BAT" in device_path or "/battery_" in device_path:
                # Extract battery ID from path (e.g., "/org/freedesktop/UPower/devices/battery_BAT0" -> "BAT0")
                battery_id = device_path.split("_")[-1]
                batteries.append(battery_id)

        return batteries

    async def get_battery_data(self, battery_id: str) -> Optional[BatteryData]:
        """Get battery data from UPower."""
        # Construct device path
        device_path = f"/org/freedesktop/UPower/devices/battery_{battery_id}"

        try:
            # Get device properties
            device_proxy = await self._get_proxy(device_path)
            properties = device_proxy.get_interface(DBUS_PROPERTIES_INTERFACE)

            # Get all properties at once
            all_props = await properties.call_get_all(UPOWER_DEVICE_INTERFACE)
        except DBusError:
            logger.error(f"DBus error getting battery data for {battery_id}", exc_info=True)
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
        temperature = temp_kelvin - 273.15 if temp_kelvin else None

        # Get energy rate
        energy_rate = get_value("EnergyRate")

        # Extract battery data
        return BatteryData(
            battery_id=battery_id,
            name=f"Battery {battery_id}",
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
            temperature=temperature,
            technology=get_value("Technology"),
            model=get_value("Model"),
            vendor=get_value("Vendor"),
            serial=get_value("Serial"),
            warning_level=get_value("WarningLevel"),
        )
#!/usr/bin/env python3
# bt_batt.py  – print battery % of a paired/connected BT device
# usage:  ./bt_batt.py 78:2B:64:A1:0E:1E

import asyncio
import sys

from dbus_next import BusType
from dbus_next.aio import MessageBus


async def find_device_path(bus, mac):
    """Return BlueZ object-path for given MAC, or None."""
    om = bus.get_proxy_object("org.bluez", "/", None)
    mgr = om.get_interface("org.freedesktop.DBus.ObjectManager")
    objs = await mgr.call_get_managed_objects()
    mac = mac.upper()
    for path, ifaces in objs.items():
        dev = ifaces.get("org.bluez.Device1")
        if dev and dev.get("Address") == mac:
            return path
    return None


async def read_battery(bus, path):
    # Primary: org.bluez.Battery1
    try:
        node = await bus.introspect("org.bluez", path)
        if "org.bluez.Battery1" in node.interfaces:
            batt = bus.get_proxy_object("org.bluez", path, node).get_interface("org.bluez.Battery1")
            return await batt.get_percentage()
    except Exception:
        pass
    # Fallback: BatteryPercentage property on Device1
    dev = bus.get_proxy_object("org.bluez", path, None).get_interface("org.bluez.Device1")
    props = await dev.call_get_all()
    return props.get("BatteryPercentage")


async def main(mac):
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    path = await find_device_path(bus, mac)
    if not path:
        print("Device not found or not paired.")
        return
    pct = await read_battery(bus, path)
    print("Battery:", f"{pct}%" if pct is not None else "N/A")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: bt_batt.py <MAC>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))

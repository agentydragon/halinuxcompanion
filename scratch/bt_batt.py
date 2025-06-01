#!/usr/bin/env python3
## bt_batt.py  – print battery % of a paired/connected BT device
## usage:  ./bt_batt.py 78:2B:64:A1:0E:1E
#
# import asyncio
# import sys
#
# from dbus_next import BusType
# from dbus_next.aio import MessageBus
#
#
# async def get_batt(mac, adapter="hci0"):
#    path = f"/org/bluez/{adapter}/dev_{mac.replace(':', '_')}"
#    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
#    node = await bus.introspect("org.bluez", path)
#    obj = bus.get_proxy_object("org.bluez", path, node)
#
#    print(node.interfaces)
#
#    # 1) The proper Battery1 interface (new kernels / LE devices)
#    if "org.bluez.Battery1" in node.interfaces:
#        batt = obj.get_interface("org.bluez.Battery1")
#        return await batt.get_percentage()
#
#    # 2) Fallback: some patches expose BatteryPercentage on Device1
#    dev = obj.get_interface("org.bluez.Device1")
#    props = await dev.get_all()
#    return props.get("BatteryPercentage")
#
#
# if __name__ == "__main__":
#    if len(sys.argv) < 2:
#        print("Usage: bt_batt.py <MAC>")
#        sys.exit(1)
#    pct = asyncio.run(get_batt(sys.argv[1]))
#    print("Battery:", f"{pct}%" if pct is not None else "N/A")


#!/usr/bin/env python3
# bt_batt_auto.py – query BT battery by MAC on any adapter
# Usage: ./bt_batt_auto.py 78:2B:64:A1:0E:1E

import asyncio
import sys

from dbus_next import BusType
from dbus_next.aio import MessageBus


async def find_device(bus, target_mac):
    """Return (object_path, interfaces_dict) for the MAC, else (None, None)."""
    root = await bus.introspect("org.bluez", "/")
    om = bus.get_proxy_object("org.bluez", "/", root)
    mgr = om.get_interface("org.freedesktop.DBus.ObjectManager")

    objs = await mgr.call_get_managed_objects()
    tmac = target_mac.upper()
    for path, ifaces in objs.items():
        dev = ifaces.get("org.bluez.Device1")
        if dev and dev.get("Address", "").value.upper() == tmac:
            return path, ifaces
    return None, None


async def read_battery(bus, path, ifaces):
    # Prefer the dedicated interface if present
    if "org.bluez.Battery1" in ifaces:
        node = await bus.introspect("org.bluez", path)
        batt = bus.get_proxy_object("org.bluez", path, node).get_interface("org.bluez.Battery1")
        return await batt.get_percentage()
    # Fallback to property on Device1
    return ifaces["org.bluez.Device1"].get("BatteryPercentage")


async def main():
    if len(sys.argv) < 2:
        print("Usage: bt_batt_auto.py <MAC>")
        sys.exit(1)
    mac = sys.argv[1]

    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    path, ifaces = await find_device(bus, mac)
    if not path:
        print("Device not found (is it paired/connected?)")
        return

    pct = await read_battery(bus, path, ifaces)
    print("Battery:", f"{pct}%" if pct is not None else "N/A")


if __name__ == "__main__":
    asyncio.run(main())
